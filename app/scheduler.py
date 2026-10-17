import datetime
import math
import random
import traceback
from threading import RLock

from apscheduler.jobstores.base import JobLookupError

import log
from app.conf import SystemConfig
from app.helper import MetaHelper
from app.scheduler_manager import SchedulerManager
from app.sites import SiteUserInfo
from app.tools import SiteSignin
from app.tools.site_signin.config import get_site_signin_config
from app.utils import ExceptionUtils
from app.utils.commons import singleton
from config import METAINFO_SAVE_INTERVAL, REFRESH_PT_DATA_INTERVAL, \
    META_DELETE_UNKNOWN_INTERVAL, REFRESH_WALLPAPER_INTERVAL, COOKIECLOUD_SYNC_INTERVAL
from web.backend.wallpaper import get_login_wallpaper


@singleton # 这里又用到了单例模式，保证全系统只有一个定时任务调度器
class Scheduler:
    """
    【大管家】定时任务调度类。
    作用：NAS-Tools 是一个后台长期运行的程序，很多活儿不能靠人手工点，需要定时自动干。
    这个类就负责统筹安排：几点签到、几点去扫描下载器、每隔几分钟刷一次流量数据。
    """
    SCHEDULER = None # 共享调度器中的系统任务组
    _site_signin_config = None
    _site_signin_job_id = "site_signin"
    _site_signin_date_job_id = "site_signin_random"
    _site_signin_generation = 0
    _site_signin_dirty = False
    _cookiecloud_interval = None
    _cookiecloud_job_id = "cookiecloud_sync"
    _cookiecloud_generation = 0
    _cookiecloud_dirty = False
    _config_lock = RLock()

    def __init__(self):
        """初始化时读取一遍配置"""
        self.init_config()

    def init_config(self):
        # 从工具配置中读取站点自动签到设置
        with self._config_lock:
            self._site_signin_config = get_site_signin_config()

    @staticmethod
    def _signin_cron(config):
        return str((config or {}).get('cron') or '').strip()

    def reload_cookiecloud_config(self):
        """更新 CookieCloud 周期；凭据变化不重置下一次执行时间。"""
        with self._config_lock:
            valid = True
            try:
                config = SystemConfig().get_system_config("CookieCloud") or {}
                if not isinstance(config, dict):
                    raise ValueError("invalid config")
                value = config.get("interval", COOKIECLOUD_SYNC_INTERVAL)
                if isinstance(value, bool) or not isinstance(value, (int, str)):
                    raise ValueError("invalid interval")
                interval = int(value)
                if not 0 <= interval <= 10080:
                    raise ValueError("invalid interval")
                if not all(isinstance(config.get(key), str) and config[key].strip()
                           for key in ("server", "key", "password")):
                    interval = 0
            except Exception as error:
                # 无法确认当前计划时停用旧任务；不记录可能含凭据的配置或异常文本。
                log.warn("【CookieCloud】读取自动同步配置失败，将停用自动同步：%s" % type(error).__name__)
                interval = 0
                valid = False

            if not self.SCHEDULER:
                self._cookiecloud_interval = interval
                self._cookiecloud_dirty = False
                return valid
            try:
                job = self.SCHEDULER.get_job(self._cookiecloud_job_id)
                if (interval == self._cookiecloud_interval and not self._cookiecloud_dirty
                        and bool(job) == bool(interval)):
                    return valid
                self._cookiecloud_generation += 1
                self._cookiecloud_dirty = True
                if interval:
                    generation = self._cookiecloud_generation

                    def sync_cookiecloud():
                        with self._config_lock:
                            if generation != self._cookiecloud_generation or not self.SCHEDULER:
                                return
                        self._run_cookiecloud_sync()

                    self.SCHEDULER.add_job(
                        sync_cookiecloud, 'interval', id=self._cookiecloud_job_id,
                        replace_existing=True, minutes=interval, max_instances=1, coalesce=True
                    )
                elif job:
                    self.SCHEDULER.remove_job(self._cookiecloud_job_id)
                self._cookiecloud_interval = interval
                self._cookiecloud_dirty = False
                return valid
            except Exception as error:
                log.error("【CookieCloud】更新自动同步计划失败：%s" % type(error).__name__)
                return False

    @staticmethod
    def _run_cookiecloud_sync():
        """复用手动同步入口，执行时读取最新配置并由入口统一防止重叠。"""
        try:
            from app.helper import DbHelper
            from web.actions.sites import SiteActions

            result = SiteActions(DbHelper()).cookiecloud_sync({})
            if isinstance(result, dict) and result.get("code") == 0:
                log.info("【CookieCloud】定时同步完成")
            else:
                log.warn("【CookieCloud】定时同步未完成，请在站点维护页面手动同步查看结果")
        except Exception as error:
            log.error("【CookieCloud】定时同步执行失败：%s" % type(error).__name__)

    def reload_runtime_config(self):
        """只在执行周期变化时替换签到任务，保留其他任务的运行计划。"""
        with self._config_lock:
            config = get_site_signin_config()
            old_cron = self._signin_cron(self._site_signin_config)
            signin_cron = self._signin_cron(config)
            if signin_cron == old_cron and not self._site_signin_dirty:
                self._site_signin_config = config
                return True

            self._site_signin_generation += 1
            if not self.SCHEDULER:
                self._site_signin_config = config
                self._site_signin_dirty = False
                return True
            # 替换中途失败时，恢复旧配置也必须重建已移除的签到任务。
            self._site_signin_dirty = True
            for job_id in (self._site_signin_job_id, self._site_signin_date_job_id):
                try:
                    self.SCHEDULER.remove_job(job_id)
                except JobLookupError:
                    pass
            if not self._schedule_site_signin(signin_cron):
                return False
            self._site_signin_config = config
            self._site_signin_dirty = False
            return True

    def _schedule_site_signin(self, signin_cron):
        if not signin_cron:
            return True
        try:
            if '-' in signin_cron:
                start, end = signin_cron.split('-')
                start_hour, start_minute = self._parse_signin_time(start)
                end_hour, end_minute = self._parse_signin_time(end)
                start_total = start_hour * 60 + start_minute
                end_total = end_hour * 60 + end_minute
                if start_total > end_total:
                    raise ValueError("签到时间范围无效")
                generation = self._site_signin_generation

                def start_random_job():
                    with self._config_lock:
                        # 修改周期或停止服务后，已取出的旧回调不能再排入签到任务。
                        if generation != self._site_signin_generation or not self.SCHEDULER:
                            return
                        selected_minute = random.randint(start_total, end_total)
                        self.start_data_site_signin_job(*divmod(selected_minute, 60))

                self.SCHEDULER.add_job(start_random_job, 'cron',
                                       id=self._site_signin_job_id, replace_existing=True,
                                       hour=start_hour, minute=start_minute)
                log.info("站点自动签到服务时间范围随机模式启动，起始时间于%02d:%02d" % (
                    start_hour, start_minute))
            elif ':' in signin_cron:
                hour, minute = self._parse_signin_time(signin_cron)
                self.SCHEDULER.add_job(SiteSignin().signin, 'cron',
                                       id=self._site_signin_job_id, replace_existing=True,
                                       hour=hour, minute=minute)
                log.info("站点自动签到服务启动")
            else:
                hours = float(signin_cron)
                if not math.isfinite(hours) or hours <= 0:
                    raise ValueError("签到间隔必须大于 0 小时")
                self.SCHEDULER.add_job(SiteSignin().signin, 'interval',
                                       id=self._site_signin_job_id, replace_existing=True,
                                       hours=hours)
                log.info("站点自动签到服务启动")
        except (TypeError, ValueError) as error:
            log.info("站点自动签到时间配置格式错误：%s" % str(error))
            return False
        return True

    @staticmethod
    def _parse_signin_time(value):
        hour, minute = (int(part) for part in value.split(':'))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("签到时间无效")
        return hour, minute

    def run_service(self):
        """注册并启动系统任务组，重复启动不叠加任务或执行池。"""
        with self._config_lock:
            if self.SCHEDULER and self.SCHEDULER.running:
                return
            group = SchedulerManager().create_group("system")
            self.SCHEDULER = group
            try:
                self._site_signin_generation += 1
                self._site_signin_dirty = True
                self._site_signin_dirty = not self._schedule_site_signin(
                    self._signin_cron(self._site_signin_config)
                )
                self._cookiecloud_dirty = True
                self.reload_cookiecloud_config()
                group.add_job(MetaHelper().save_meta_data, 'interval',
                              id="meta_save", seconds=METAINFO_SAVE_INTERVAL)
                group.add_job(SiteUserInfo().refresh_pt_date_now, 'interval',
                              id="site_statistics", hours=REFRESH_PT_DATA_INTERVAL,
                              next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=1))
                group.add_job(MetaHelper().delete_unknown_meta, 'interval',
                              id="meta_cleanup", hours=META_DELETE_UNKNOWN_INTERVAL)
                group.add_job(get_login_wallpaper, 'interval',
                              id="wallpaper", hours=REFRESH_WALLPAPER_INTERVAL,
                              next_run_time=datetime.datetime.now())
                group.print_jobs()
                group.start()
            except BaseException:
                self.SCHEDULER = None
                self._site_signin_generation += 1
                self._cookiecloud_generation += 1
                try:
                    group.shutdown(wait=False)
                except Exception as error:
                    log.error("【Scheduler】清理启动失败的系统任务组失败：%s" % type(error).__name__)
                raise

    def stop_service(self):
        """
        停止定时服务：用于重启系统、修改配置后重新加载
        """
        try:
            with self._config_lock:
                scheduler = self.SCHEDULER
                self.SCHEDULER = None
                self._site_signin_generation += 1
                self._cookiecloud_generation += 1
            if scheduler:
                scheduler.shutdown(wait=True)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def start_data_site_signin_job(self, hour, minute):
        """
        这是一个辅助函数，配合前面提到的“随机签到模式”使用的。
        动态在今天具体的时、分、秒 插入一条“只跑一次的定时任务”(类型是 "date")
        """
        year = datetime.datetime.now().year
        month = datetime.datetime.now().month
        day = datetime.datetime.now().day
        # 随机数从1秒开始，不在整点签到，为了防止所有人都在 00 秒去轰炸别人网站导致被封
        second = random.randint(1, 59)
        log.info("站点自动签到时间 即将在%s-%s-%s,%s:%s:%s签到" % (
            str(year), str(month), str(day), str(hour), str(minute), str(second)))
            
        if hour < 0 or hour > 23:
            hour = -1
        if minute < 0 or minute > 59:
            minute = -1
        if hour < 0 or minute < 0:
            log.warn("站点自动签到时间 配置格式错误：不启动任务")
            return
            
        # 注意此处的类型是 "date"，它意味着：只在这个明确的时间点执行一次就销毁，不会循环。
        with self._config_lock:
            if self.SCHEDULER:
                self.SCHEDULER.add_job(SiteSignin().signin,
                                       "date",
                                       id=self._site_signin_date_job_id,
                                       replace_existing=True,
                                       run_date=datetime.datetime(year, month, day, hour, minute, second))


# ===== 对外提供快速调用的三个函数 =====

def run_scheduler():
    """启动定时服务"""
    try:
        Scheduler().run_service()
    except Exception as err:
        log.error("启动定时服务失败：%s - %s" % (str(err), traceback.format_exc()))

def stop_scheduler():
    """停止定时服务"""
    try:
        Scheduler().stop_service()
    except Exception as err:
        log.debug("停止定时服务失败：%s" % str(err))

def restart_scheduler():
    """重启定时服务"""
    stop_scheduler()
    run_scheduler()
