import datetime
import math
import random
import traceback

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler

import log
from app.db import remove_db_session
from app.helper import MetaHelper
from app.sites import SiteUserInfo
from app.tools import SiteSignin
from app.tools.site_signin.config import get_site_signin_config
from app.utils import ExceptionUtils
from app.utils.commons import singleton
from config import METAINFO_SAVE_INTERVAL, REFRESH_PT_DATA_INTERVAL, \
    META_DELETE_UNKNOWN_INTERVAL, REFRESH_WALLPAPER_INTERVAL, Config
from web.backend.wallpaper import get_login_wallpaper


@singleton # 这里又用到了单例模式，保证全系统只有一个定时任务调度器
class Scheduler:
    """
    【大管家】定时任务调度类。
    作用：NAS-Tools 是一个后台长期运行的程序，很多活儿不能靠人手工点，需要定时自动干。
    这个类就负责统筹安排：几点签到、几点去扫描下载器、每隔几分钟刷一次流量数据。
    """
    SCHEDULER = None # 存放真正的 APScheduler 框架对象
    _site_signin_config = None

    def __init__(self):
        """初始化时读取一遍配置"""
        self.init_config()

    def init_config(self):
        # 从工具配置中读取站点自动签到设置
        self._site_signin_config = get_site_signin_config()

    def run_service(self):
        """
        核心启动方法：读取配置，把各个定时任务加入到计划表中，最后启动！
        初学者注意：在 Python 里要想实现定时任务，通常使用第三方库 `APScheduler`。
        """
        # 创建一个后台调度器 (BackgroundScheduler)
        # 给了它一个拥有 20 个工人的线程池 (ThreadPoolExecutor)，保证任务太多时也能并发行执行
        self.SCHEDULER = BackgroundScheduler(timezone=Config().get_timezone(),
                                             executors={
                                                 'default': ThreadPoolExecutor(20)
                                             })
        self.SCHEDULER.add_listener(
            lambda _event: remove_db_session(),
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
        )
        if not self.SCHEDULER:
            return
            
        # 如果用户配置了自动签到时间，才启动工具的定时任务
        if self._site_signin_config:
            # 1. 站点签到任务 (最复杂的逻辑，因为涉及到三种配置模式)
            signin_cron = str(self._site_signin_config.get('cron') or '').strip()
            if signin_cron:
                # 模式 A: 范围随机签到 (例如配置成 08:00-10:00)
                if '-' in signin_cron:
                    try:
                        time_range = signin_cron.split("-")
                        start_time_range_str = time_range[0]
                        end_time_range_str = time_range[1]
                        start_time_range_array = start_time_range_str.split(":")
                        end_time_range_array = end_time_range_str.split(":")
                        start_hour = int(start_time_range_array[0])
                        start_minute = int(start_time_range_array[1])
                        end_hour = int(end_time_range_array[0])
                        end_minute = int(end_time_range_array[1])
                        start_total = start_hour * 60 + start_minute
                        end_total = end_hour * 60 + end_minute
                        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23
                                and 0 <= start_minute <= 59 and 0 <= end_minute <= 59
                                and start_total <= end_total):
                            raise ValueError("签到时间范围无效")

                        def start_random_job():
                            """
                            内部函数：这招叫“套娃”。每天到了起始时间（比如8点），这个函数被执行。
                            它会在 8点 到 10点 之间随机生成一个分钟数，然后再安排一次【一次性延期任务】去执行真正签到。
                            """
                            task_time_count = random.randint(start_total, end_total)
                            self.start_data_site_signin_job(math.floor(task_time_count / 60), task_time_count % 60)

                        # 使用 "cron" (类似 Linux 的 crontab) 语法，每天指定的小时/分钟执行
                        self.SCHEDULER.add_job(start_random_job,
                                               "cron",
                                               hour=start_hour,
                                               minute=start_minute)
                        log.info("站点自动签到服务时间范围随机模式启动，起始时间于%s:%s" % (
                            str(start_hour).rjust(2, '0'), str(start_minute).rjust(2, '0')))
                    except Exception as e:
                        log.info("站点自动签到时间 时间范围随机模式 配置格式错误：%s %s" % (signin_cron, str(e)))
                        
                # 模式 B: 固定时间签到 (例如配置成 08:30)
                elif signin_cron.find(':') != -1:
                    try:
                        hour = int(signin_cron.split(":")[0])
                        minute = int(signin_cron.split(":")[1])
                        if not (0 <= hour <= 23 and 0 <= minute <= 59):
                            raise ValueError("签到时间无效")
                    except Exception as e:
                        log.info("站点自动签到时间 配置格式错误：%s" % str(e))
                        hour = minute = None
                    if hour is not None and minute is not None:
                        self.SCHEDULER.add_job(SiteSignin().signin,
                                               "cron",
                                               hour=hour,
                                               minute=minute)
                        log.info("站点自动签到服务启动")
                    
                # 模式 C: 间隔循环签到 (例如配置成 12，代表每12小时签到一次)
                else:
                    try:
                        hours = float(signin_cron)
                    except Exception as e:
                        log.info("站点自动签到时间 配置格式错误：%s" % str(e))
                        hours = 0
                    if hours:
                        # 注意这里参数是 "interval"（间隔模式），上面是 "cron"（定点模式）
                        self.SCHEDULER.add_job(SiteSignin().signin,
                                               "interval",
                                               hours=hours)
                        log.info("站点自动签到服务启动")

        # 2. 元数据定时保存任务
        # 把内存里的数据定时写进数据库
        self.SCHEDULER.add_job(MetaHelper().save_meta_data, 'interval', seconds=METAINFO_SAVE_INTERVAL)

        # 3. 站点数据（流量上传量、下载量）刷新任务
        # 注意：next_run_time 表示这个任务启动后 1 分钟马上执行第一次，之后再按照 interval (如6小时) 循环
        self.SCHEDULER.add_job(SiteUserInfo().refresh_pt_date_now,
                               'interval',
                               hours=REFRESH_PT_DATA_INTERVAL,
                               next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=1))

        # 4. 定时清除未识别的垃圾缓存
        self.SCHEDULER.add_job(MetaHelper().delete_unknown_meta, 'interval', hours=META_DELETE_UNKNOWN_INTERVAL)

        # 5. 定时去远端服务器拉取 NAS-Tools 登录页面的好看壁纸
        self.SCHEDULER.add_job(get_login_wallpaper,
                               'interval',
                               hours=REFRESH_WALLPAPER_INTERVAL,
                               next_run_time=datetime.datetime.now())

        # 在日志里把所有排好队的任务打出来看一眼
        self.SCHEDULER.print_jobs()

        # 最后：正式鸣枪起跑！调度器开始默默在后台按时间表干活。
        self.SCHEDULER.start()

    def stop_service(self):
        """
        停止定时服务：用于重启系统、修改配置后重新加载
        """
        try:
            if self.SCHEDULER:
                self.SCHEDULER.remove_all_jobs()
                self.SCHEDULER.shutdown()
                self.SCHEDULER = None
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
        self.SCHEDULER.add_job(SiteSignin().signin,
                               "date",
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
