import ast
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock, RLock

import pytz

import log
from app.downloader.client import Qbittorrent, Transmission
from app.helper import DbHelper
from app.message import Message
from app.scheduler_manager import SchedulerManager
from app.utils.rss_parser import RssParser
from app.sites import Sites
from app.utils import StringUtils, Torrent, ExceptionUtils
from app.utils.commons import singleton
from app.utils.types import BrushDeleteType
from config import BRUSH_REMOVE_TORRENTS_INTERVAL, Config


# ===== 3. 核心业务：刷流（自动化下载与删种） =====
# 初学者注意：刷流（Brush）是 PT（Private Tracker）圈的行话，意思是自动下载免费的种子，挂机上传赚取积分或上传量，然后再自动删除。
# 这个类是整个刷流功能的大脑，负责定时去检查有没有新种子，以及检查有没有种子满足条件可以删除了。

@singleton # 单例模式，确保整个程序运行期间只有一个 BrushTask 实例在干活
class BrushTask(object):
    message = None
    sites = None
    dbhelper = None
    _scheduler = None
    _config_lock = RLock()
    _brush_tasks = []
    _active_checks = set()
    _active_checks_lock = Lock()
    _cleanup_lock = Lock()
    _downloader_infos = []
    _qb_client = "qbittorrent"
    _tr_client = "transmission"

    def __init__(self):
        self.init_config()

    def init_config(self):
        """
        初始化刷流配置。
        初学者注意：当系统启动，或者用户在网页上修改了刷流配置后，都会调用这个方法重新排班。
        """
        with self._config_lock:
            self.dbhelper = DbHelper()
            self.message = Message()
            self.sites = Sites()
            self.stop_service()
            # 读取下载器列表
            downloaders = self.dbhelper.get_user_downloaders()
            self._downloader_infos = []
            for downloader_info in downloaders:
                self._downloader_infos.append(
                    {
                        "id": downloader_info.id,
                        "name": downloader_info.name,
                        "type": downloader_info.type,
                        "host": downloader_info.host,
                        "port": downloader_info.port,
                        "username": downloader_info.username,
                        "password": downloader_info.password,
                        "save_dir": downloader_info.save_dir
                    }
                )
            self._brush_tasks = self.get_brushtask_info()
            scheduled_tasks = [
                task for task in self._brush_tasks
                if task.get("state") == "Y" and task.get("interval")
                and str(task.get("interval")).isdigit()
            ]
            if not scheduled_tasks:
                return

            group = SchedulerManager().create_group("brush")
            self._scheduler = group
            try:
                for task in scheduled_tasks:
                    group.add_job(func=self.check_task_rss,
                                  args=[task.get("id")],
                                  id=f"rss:{task.get('id')}",
                                  trigger='interval',
                                  seconds=int(task.get("interval")) * 60)
                # 至少有一个自动刷流任务时，才定期检查刷流种子的清理条件。
                group.add_job(func=self.remove_tasks_torrents,
                              id="remove_torrents",
                              trigger='interval',
                              seconds=BRUSH_REMOVE_TORRENTS_INTERVAL)
                group.print_jobs()
                group.start()
                log.info("刷流服务启动")
            except BaseException:
                self._scheduler = None
                try:
                    group.shutdown(wait=False)
                except Exception as error:
                    ExceptionUtils.exception_traceback(error)
                raise

    def stop_service(self):
        """幂等停止刷流任务组，不等待正在运行的任务。"""
        with self._config_lock:
            scheduler = self._scheduler
            self._scheduler = None
            if not scheduler:
                return
            try:
                scheduler.shutdown(wait=False)
            except Exception as error:
                ExceptionUtils.exception_traceback(error)

    @staticmethod
    def __parse_rule(rule):
        if not rule:
            return {}
        if isinstance(rule, dict):
            return rule
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed_rule = parser(rule)
                if isinstance(parsed_rule, dict):
                    return parsed_rule
            except (TypeError, ValueError, SyntaxError):
                continue
        raise ValueError("规则内容不是有效字典")

    def get_brushtask_info(self, taskid=None):
        """
        读取刷流任务列表
        """
        brushtasks = self.dbhelper.get_brushtasks()
        _brush_tasks = []
        for task in brushtasks:
            try:
                rss_rule = self.__parse_rule(task.rss_rule)
                remove_rule = self.__parse_rule(task.remove_rule)
            except ValueError as err:
                log.error("【Brush】刷流任务 %s 规则解析失败，已跳过：%s" % (task.name, str(err)))
                continue
            site_info = self.sites.get_sites(siteid=task.site) or {}
            if site_info:
                site_url = StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl"))
            else:
                site_url = ""
            downloader_info = self.get_downloader_info(task.downloader)
            _brush_tasks.append({
                "id": task.id,
                "name": task.name,
                "site": site_info.get("name"),
                "site_id": task.site,
                "interval": task.inteval,
                "state": task.state,
                "downloader": task.downloader,
                "downloader_name": downloader_info.get("name"),
                "free": task.freeleech,
                "rss_rule": rss_rule,
                "remove_rule": remove_rule,
                "seed_size": task.seed_size,
                "rss_url": site_info.get("rssurl"),
                "cookie": site_info.get("cookie"),
                "sendmessage": task.sendmessage,
                "forceupload": task.forceupload,
                "ua": site_info.get("ua"),
                "download_count": task.download_count,
                "remove_count": task.remove_count,
                "download_size": StringUtils.str_filesize(task.download_size),
                "upload_size": StringUtils.str_filesize(task.upload_size),
                "lst_mod_date": task.lst_mod_date,
                "site_url": site_url
            })
        if taskid:
            for task in _brush_tasks:
                if task.get("id") == int(taskid):
                    return task
            return {}
        else:
            return _brush_tasks

    def check_task_rss(self, taskid):
        """
        【核心方法 1】检查RSS并添加下载，由定时服务定期调用。
        初学者注意：这个方法就像一个采购员。拿着清单（RSS地址），看看有没有符合条件（免费、体积合适、做种人数少）的新鲜货（种子），有就买（扔给下载器）。
        :param taskid: 刷流任务的ID
        """
        if not taskid:
            return
        task_key = str(taskid)
        with self._active_checks_lock:
            if task_key in self._active_checks:
                return
            self._active_checks.add(task_key)
        try:
            self._check_task_feed(taskid)
        finally:
            with self._active_checks_lock:
                self._active_checks.discard(task_key)

    def _check_task_feed(self, taskid):
        taskinfo = self.get_brushtask_info(taskid)
        if not taskinfo:
            return
        # 任务属性
        seed_size = taskinfo.get("seed_size")
        task_name = taskinfo.get("name")
        site_id = taskinfo.get("site_id")
        rss_url = taskinfo.get("rss_url")
        rss_rule = taskinfo.get("rss_rule")
        cookie = taskinfo.get("cookie")
        rss_free = taskinfo.get("free")
        ua = taskinfo.get("ua")
        # 查询站点信息
        site_info = self.sites.get_sites(siteid=site_id)
        if not site_info:
            log.error("【Brush】刷流任务 %s 的站点已不存在，无法刷流！" % task_name)
            return
        site_name = site_info.get("name")
        site_proxy = site_info.get("proxy")

        if not rss_url:
            log.error("【Brush】站点 %s 未配置RSS订阅地址，无法刷流！" % site_name)
            return
        if rss_free and not cookie:
            log.warn("【Brush】站点 %s 未配置Cookie，无法开启促销刷流" % site_name)
            return
        # 下载器参数
        downloader_cfg = self.get_downloader_info(taskinfo.get("downloader"))
        if not downloader_cfg:
            log.error("【Brush】任务 %s 下载器不存在，无法刷流！" % task_name)
            return

        log.info("【Brush】开始站点 %s 的刷流任务：%s..." % (site_name, task_name))
        # 检查是否达到保种体积
        if not self.__is_allow_new_torrent(taskid=taskid,
                                           taskname=task_name,
                                           seedsize=seed_size,
                                           downloadercfg=downloader_cfg,
                                           dlcount=rss_rule.get("dlcount")):
            return

        rss_result = RssParser.parse_rssxml(rss_url)
        if len(rss_result) == 0:
            log.warn("【Brush】%s RSS未下载到数据" % site_name)
            return
        else:
            log.info("【Brush】%s RSS获取数据：%s" % (site_name, len(rss_result)))

        # 同时下载数
        max_dlcount = rss_rule.get("dlcount")
        success_count = 0
        new_torrent_count = 0
        if max_dlcount:
            downloading_count = self.__get_downloading_count(downloader_cfg)
            if downloading_count is None or downloading_count >= int(max_dlcount):
                return
            new_torrent_count = int(max_dlcount) - int(downloading_count)

        for res in rss_result:
            try:
                # 种子名
                torrent_name = res.get('title')
                # 种子链接
                enclosure = res.get('enclosure')
                # 种子页面
                page_url = res.get('link')
                # 种子大小
                size = res.get('size')
                # 发布时间
                pubdate = res.get('pubdate')

                if not enclosure or self.dbhelper.is_brushtask_torrent_exists(taskid, enclosure):
                    log.debug("【Brush】%s 已处理过" % torrent_name)
                    continue

                # 检查种子是否符合选种规则
                if not self.__check_rss_rule(rss_rule=rss_rule,
                                             title=torrent_name,
                                             torrent_url=page_url,
                                             torrent_size=size,
                                             pubdate=pubdate,
                                             cookie=cookie,
                                             ua=ua,
                                             proxy=site_proxy):
                    continue
                # 开始下载
                log.debug("【Brush】%s 符合条件，开始下载..." % torrent_name)
                if self.__download_torrent(downloadercfg=downloader_cfg,
                                           title=torrent_name,
                                           enclosure=enclosure,
                                           size=size,
                                           taskid=taskid,
                                           sendmessage=True if taskinfo.get("sendmessage") == 'Y' else False,
                                           forceupload=True if taskinfo.get("forceupload") == 'Y' else False,
                                           upspeed=rss_rule.get("upspeed"),
                                           downspeed=rss_rule.get("downspeed"),
                                           taskname=task_name,
                                           site_info=site_info):
                    # 计数
                    success_count += 1
                    # 添加种子后不能超过最大下载数量
                    if max_dlcount and success_count >= new_torrent_count:
                        break

                    # 再判断一次
                    if not self.__is_allow_new_torrent(taskid=taskid,
                                                       taskname=task_name,
                                                       seedsize=seed_size,
                                                       dlcount=rss_rule.get("dlcount"),
                                                       downloadercfg=downloader_cfg):
                        break
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                continue
        log.info("【Brush】任务 %s 本次添加了 %s 个下载" % (task_name, success_count))

    def remove_tasks_torrents(self):
        """
        【核心方法 2】打扫战场：检查所有任务下载完成的种子，按条件进行删除，并更新任务数据。
        由定时服务调用。
        初学者注意：这里会去联系 qBittorrent 或 Transmission，查询当前所有种子的状态（比如已经上传了多少，做种多久了）。
        如果发现“指标达标”了，就会指挥下载器把这个种子连同文件一起删掉，释放硬盘空间。
        """

        with self._cleanup_lock:
            for task in self._brush_tasks:
                if task.get("state") != "Y":
                    continue
                try:
                    self._clean_task_torrents(task)
                except Exception as error:
                    ExceptionUtils.exception_traceback(error)

    def _clean_task_torrents(self, task):
        task_id = task["id"]
        records = self.dbhelper.get_brushtask_torrents(task_id)
        if not records:
            return
        # 数字种子 ID 只在原下载器内有意义。无归属的旧记录保留，禁止猜测。
        by_downloader = defaultdict(list)
        for record in records:
            by_downloader[record.downloader].append(record)
        upload = download = removed = 0
        complete = True
        for owner, items in by_downloader.items():
            config = self.get_downloader_info(owner) if owner else None
            if not config:
                complete = False
                log.warn(f"【Brush】{task['name']} 的原下载器不可用，保留 {len(items)} 条跟踪记录")
                continue
            try:
                result = self._clean_downloader_torrents(task, config, items)
            except Exception as error:
                ExceptionUtils.exception_traceback(error)
                result = None
            if result is None:
                complete = False
                continue
            active_up, active_down, deleted = result
            upload += active_up
            download += active_down
            removed += deleted
        self.dbhelper.add_brushtask_upload_count(brush_id=task_id,
                                                 upload_size=upload if complete else None,
                                                 download_size=download if complete else None,
                                                 remove_count=removed)

    def _clean_downloader_torrents(self, task, config, records):
        by_id = defaultdict(list)
        for record in records:
            by_id[str(record.download_id)].append(record)
        ids = list(by_id)
        is_qb = config["type"] == self._qb_client
        client = Qbittorrent(config=config) if is_qb else Transmission(config=config)
        torrents, failed = client.get_torrents(ids=ids)
        if failed:
            log.warn(f"【Brush】{task['name']} 无法查询原下载器，保留跟踪记录")
            return None
        # 对老的 Transmission 数字 ID 另核对文件名、体积。新记录直接使用 info hash。
        seen = set()
        candidates = {}
        total_up = total_down = 0
        for torrent in torrents:
            if is_qb:
                torrent_id = torrent.hash
                tracked = by_id.get(torrent_id, [])
                seen.add(torrent_id)
            else:
                torrent_id = torrent.info_hash
                numeric_id = str(torrent.id)
                seen.update((numeric_id, torrent_id))
                tracked = list(by_id.get(torrent_id, []))
                for record in by_id.get(numeric_id, []):
                    if record.torrent_name == torrent.name and str(record.torrent_size) == str(torrent.total_size):
                        tracked.append(record)
                    else:
                        log.warn(f"【Brush】{task['name']} 的历史种子 {numeric_id} 身份无法确认，已跳过")
            if not tracked:
                continue
            if is_qb:
                uploaded = torrent.get("uploaded") or 0
                downloaded = torrent.get("downloaded") or 0
                age = max(1, int(time.time()) - torrent.added_on)
                last_active = torrent.get("last_activity")
                inactive = int(time.time()) - last_active if last_active else None
                finished = torrent.get("progress", 0) >= 1
                seed_time = torrent.get("seeding_time")
                ratio = torrent.get("ratio")
            else:
                uploaded = torrent.uploaded_ever
                downloaded = torrent.downloaded_ever
                age = max(1, int(time.time() - torrent.added_date.timestamp()))
                inactive = None
                finished = torrent.percent_done >= 1
                seed_time = torrent.get("secondsSeeding")
                ratio = torrent.ratio
            total_up += uploaded
            total_down += downloaded
            if is_qb:
                # 不对校验、排队和手动暂停的未完成种子应用下载超时。
                if not finished and torrent.state not in ("downloading", "forcedDL", "stalledDL", "metaDL"):
                    continue
            elif torrent.status not in ("downloading", "download pending", "seeding", "seed pending", "stopped"):
                continue
            need_delete, reason = self.__check_remove_rule(
                remove_rule=task.get("remove_rule"), seeding_time=seed_time if finished else None,
                ratio=ratio if finished else None, uploaded=uploaded if finished else None,
                dltime=None if finished else age, avg_upspeed=uploaded // age, iatime=inactive)
            if need_delete:
                candidates[torrent_id] = (tracked, uploaded, downloaded, reason, torrent.name)

        removed = 0
        for missing in set(by_id).difference(seen):
            for record in by_id[missing]:
                if self.dbhelper.delete_brushtask_torrent(record.id):
                    removed += 1
        if candidates and client.delete_torrents(delete_file=True, ids=list(candidates)):
            updates = []
            for tracked, uploaded, downloaded, _, _ in candidates.values():
                # 多条历史记录指向同一种子时，流量和删除数只计一次。
                for index, record in enumerate(tracked):
                    updates.append((record.id, f"{uploaded},{downloaded}" if index == 0 else "0,0"))
            if self.dbhelper.update_brushtask_torrent_state(updates):
                removed += len(candidates)
                total_up -= sum(item[1] for item in candidates.values())
                total_down -= sum(item[2] for item in candidates.values())
            else:
                log.error(f"【Brush】{task['name']} 删除成功，但数据库状态更新失败")
            if task.get("sendmessage") == "Y":
                for _, _, _, reason, name in candidates.values():
                    self.message.send_brushtask_remove_message(
                        title=f"【刷流任务 {task['name']} 删除做种】",
                        text=f"删除原因：{reason.value}\n种子名称：{name}")
        return total_up, total_down, removed

    def __is_allow_new_torrent(self, taskid, taskname, downloadercfg, seedsize, dlcount):
        """
        检查是否还能添加新的下载
        """
        if not taskid:
            return False
        # 判断大小
        total_size = self.dbhelper.get_brushtask_totalsize(taskid)
        if seedsize:
            if float(seedsize) * 1024 ** 3 <= int(total_size):
                log.warn("【Brush】刷流任务 %s 当前保种体积 %sGB，不再新增下载"
                         % (taskname, round(int(total_size) / 1024 / 1024 / 1024, 1)))
                return False
        # 检查正在下载的任务数
        if dlcount:
            downloading_count = self.__get_downloading_count(downloadercfg)
            if downloading_count is None:
                log.error("【Brush】任务 %s 下载器 %s 无法连接" % (taskname, downloadercfg.get("name")))
                return False
            if int(downloading_count) >= int(dlcount):
                log.warn("【Brush】下载器 %s 正在下载任务数：%s，超过设定上限，暂不添加下载" % (
                    downloadercfg.get("name"), downloading_count))
                return False
        return True

    def get_downloader_info(self, dlid=None):
        """
        获取下载器的参数
        """
        if dlid:
            for downloader in self._downloader_infos:
                if downloader.get('id') == int(dlid):
                    if downloader.get('type') == self._qb_client:
                        return {
                            "id": downloader.get("id"),
                            "name": downloader.get("name"),
                            "type": downloader.get("type"),
                            "save_dir": downloader.get("save_dir"),
                            "qbhost": downloader.get("host"),
                            "qbport": downloader.get("port"),
                            "qbusername": downloader.get("username"),
                            "qbpassword": downloader.get("password")
                        }
                    elif downloader.get('type') == self._tr_client:
                        return {
                            "id": downloader.get("id"),
                            "name": downloader.get("name"),
                            "type": downloader.get("type"),
                            "save_dir": downloader.get("save_dir"),
                            "trhost": downloader.get("host"),
                            "trport": downloader.get("port"),
                            "trusername": downloader.get("username"),
                            "trpassword": downloader.get("password")
                        }
                    return downloader
            return {}
        else:
            return self._downloader_infos

    def __get_downloading_count(self, downloadercfg):
        """
        查询当前正在下载的任务数
        """
        if not downloadercfg:
            return 0
        if downloadercfg.get("type") == self._qb_client:
            downloader = Qbittorrent(config=downloadercfg)
            if not downloader.qbc:
                return None
            dlitems, failed = downloader.get_torrents(status="downloading")
        else:
            downloader = Transmission(config=downloadercfg)
            if not downloader.trc:
                return None
            dlitems, failed = downloader.get_torrents(status=["downloading", "download_pending"])
        return None if failed else len(dlitems)

    def __download_torrent(self,
                           downloadercfg,
                           title,
                           enclosure,
                           size,
                           taskid,
                           sendmessage,
                           forceupload,
                           upspeed,
                           downspeed,
                           taskname,
                           site_info):
        """
        添加下载任务，更新任务数据
        :param downloadercfg: 下载器的所有参数
        :param title: 种子名称
        :param enclosure: 种子地址
        :param size: 种子大小
        :param taskid: 任务ID
        :param sendmessage: 是否需要消息推送
        :param forceupload: 是否需要将添加的刷流任务设置为强制做种(仅针对qBittorrent)
        :param upspeed: 上传限速
        :param downspeed: 下载限速
        :param taskname: 任务名称
        :param site_info: 站点信息
        """
        if not downloadercfg or not enclosure:
            return False
        # 下载任务ID
        download_id = None
        # 下载种子文件
        _, content, _, _, retmsg = Torrent().get_torrent_info(
            url=enclosure,
            cookie=site_info.get("cookie"),
            ua=site_info.get("ua"),
            proxy=site_info.get("proxy"),
            apikey=site_info.get("apikey"),
            source_url=site_info.get("strict_url"))
        if content:
            # 添加下载
            if downloadercfg.get("type") == self._qb_client:
                # 初始化下载器
                downloader = Qbittorrent(config=downloadercfg)
                if not downloader.qbc:
                    log.error("【Brush】任务 %s 下载器 %s 无法连接" % (taskname, downloadercfg.get("name")))
                    return False
                torrent_tag = "NT" + StringUtils.generate_random_str(5)
                ret = downloader.add_torrent(content=content,
                                             tag=torrent_tag,
                                             download_dir=downloadercfg.get("save_dir"),
                                             upload_limit=upspeed,
                                             download_limit=downspeed)
                if ret:
                    # QB添加下载后需要时间，重试5次每次等待5秒
                    download_id = downloader.get_torrent_id_by_tag(torrent_tag)
                    if download_id:
                        # 开始下载
                        downloader.start_torrents(download_id)
                        # 强制做种
                        if forceupload:
                            downloader.torrents_set_force_start(download_id)
            else:
                # 初始化下载器
                downloader = Transmission(config=downloadercfg, reject_duplicates=True)
                if not downloader.trc:
                    log.error("【Brush】任务 %s 下载器 %s 无法连接" % (taskname, downloadercfg.get("name")))
                    return False
                ret = downloader.add_torrent(content=content,
                                             download_dir=downloadercfg.get("save_dir"),
                                             upload_limit=upspeed,
                                             download_limit=downspeed
                                             )
                if ret:
                    download_id = ret.info_hash
        if not download_id:
            # 下载失败
            log.warn(f"【Brush】{taskname} 添加下载任务出错：{title}，"
                     f"错误原因：{retmsg or '下载器添加任务失败'}，"
                     f"种子链接：{StringUtils.redact_url(enclosure)}")
            return False
        else:
            # 下载成功
            log.info("【Brush】成功添加下载：%s" % title)
            if sendmessage:
                msg_title = "【刷流任务 {} 新增下载】".format(taskname)
                msg_text = "种子名称：{}\n种子大小：{}".format(title, StringUtils.str_filesize(size))
                self.message.send_brushtask_added_message(title=msg_title, text=msg_text)
        # 插入种子数据
        if self.dbhelper.insert_brushtask_torrent(brush_id=taskid,
                                                  title=title,
                                                  enclosure=enclosure,
                                                  downloader=downloadercfg.get("id"),
                                                  download_id=download_id,
                                                  size=size):
            # 更新下载次数
            self.dbhelper.add_brushtask_download_count(brush_id=taskid)
        else:
            log.info("【Brush】%s 已下载过" % title)

        return True

    def __check_rss_rule(self,
                         rss_rule,
                         title,
                         torrent_url,
                         torrent_size,
                         pubdate,
                         cookie,
                         ua,
                         proxy):
        """
        检查种子是否符合刷流过滤条件
        :param rss_rule: 过滤条件字典
        :param title: 种子名称
        :param torrent_url: 种子页面地址
        :param torrent_size: 种子大小
        :param pubdate: 发布时间
        :param cookie: Cookie
        :param ua: User-Agent
        :return: 是否命中
        """
        if not rss_rule:
            return True
        # 检查种子大小
        try:
            if rss_rule.get("size"):
                rule_sizes = rss_rule.get("size").split("#")
                if rule_sizes[0]:
                    if len(rule_sizes) > 1 and rule_sizes[1]:
                        min_max_size = rule_sizes[1].split(',')
                        min_size = min_max_size[0]
                        if len(min_max_size) > 1:
                            max_size = min_max_size[1]
                        else:
                            max_size = 0
                        if rule_sizes[0] == "gt" and float(torrent_size) < float(min_size) * 1024 ** 3:
                            return False
                        if rule_sizes[0] == "lt" and float(torrent_size) > float(min_size) * 1024 ** 3:
                            return False
                        if rule_sizes[0] == "bw" and not float(min_size) * 1024 ** 3 < float(torrent_size) < float(
                                max_size) * 1024 ** 3:
                            return False

            # 检查包含规则
            if rss_rule.get("include"):
                if not re.search(r"%s" % rss_rule.get("include"), title):
                    return False

            # 检查排除规则
            if rss_rule.get("exclude"):
                if re.search(r"%s" % rss_rule.get("exclude"), title):
                    return False

            torrent_attr = self.sites.check_torrent_attr(torrent_url=torrent_url,
                                                         cookie=cookie,
                                                         ua=ua,
                                                         proxy=proxy)
            torrent_peer_count = torrent_attr.get("peer_count")
            log.debug("【Brush】%s 解析详情, %s" % (title, torrent_attr))

            # 检查免费状态
            if rss_rule.get("free") == "FREE":
                if not torrent_attr.get("free"):
                    log.debug("【Brush】不是一个FREE资源，跳过")
                    return False
            elif rss_rule.get("free") == "2XFREE":
                if not torrent_attr.get("2xfree"):
                    log.debug("【Brush】不是一个2XFREE资源，跳过")
                    return False

            # 检查HR状态
            if rss_rule.get("hr"):
                if torrent_attr.get("hr"):
                    log.debug("【Brush】这是一个H&R资源，跳过")
                    return False

            # 检查做种人数
            if rss_rule.get("peercount"):
                peercount_str = rss_rule.get("peercount")
                peer_counts = peercount_str.split("#", 1)
                if len(peer_counts) >= 2 and peer_counts[1]:
                    min_max_count = peer_counts[1].split(',')
                    min_count = int(min_max_count[0])
                    if len(min_max_count) > 1:
                        max_count = int(min_max_count[1])
                    else:
                        max_count = sys.maxsize
                    if peer_counts[0] == "gt" and torrent_peer_count <= min_count:
                        log.debug("【Brush】%s `判断做种数, 判断条件: peer_count:%d %s threshold:%d" % (
                            title, torrent_peer_count, peer_counts[0], min_count))
                        return False
                    if peer_counts[0] == "lt" and torrent_peer_count >= min_count:
                        log.debug("【Brush】%s `判断做种数, 判断条件: peer_count:%d %s threshold:%d" % (
                            title, torrent_peer_count, peer_counts[0], min_count))
                        return False
                    if peer_counts[0] == "bw" and not (min_count <= torrent_peer_count <= max_count):
                        log.debug("【Brush】%s `判断做种数, 判断条件: left:%d %s peer_count:%d %s right:%d" % (
                            title, min_count, peer_counts[0], torrent_peer_count, peer_counts[0], max_count))
                        return False

            # 检查发布时间
            if rss_rule.get("pubdate") and pubdate:
                rule_pubdates = rss_rule.get("pubdate").split("#")
                if len(rule_pubdates) >= 2 and rule_pubdates[1]:
                    localtz = pytz.timezone(Config().get_timezone())
                    localnowtime = datetime.now().astimezone(localtz)
                    localpubdate = pubdate.astimezone(localtz)
                    log.debug('【Brush】发布时间：%s，当前时间：%s' % (localpubdate.isoformat(), localnowtime.isoformat()))
                    if (localnowtime - localpubdate).total_seconds() / 3600 > float(rule_pubdates[1]):
                        log.debug("【Brush】发布时间不符合条件。")
                        return False

        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            log.error("【Brush】%s 选种规则校验失败，已跳过该资源：%s" % (title, str(err)))
            return False

        return True

    @staticmethod
    def __check_remove_rule(remove_rule, seeding_time=None, ratio=None, uploaded=None, dltime=None, avg_upspeed=None, iatime=None):
        """
        检查是否符合删种规则
        :param remove_rule: 删种规则
        :param seeding_time: 做种时间
        :param ratio: 分享率
        :param uploaded: 上传量
        :param dltime: 下载耗时
        :param avg_upspeed: 上传平均速度
        :param iatime: 未活动时间
        """
        if not remove_rule:
            return False, BrushDeleteType.NOTDELETE
        try:
            if remove_rule.get("time") and seeding_time:
                rule_times = remove_rule.get("time").split("#")
                if rule_times[0]:
                    if len(rule_times) > 1 and rule_times[1]:
                        if float(seeding_time) > float(rule_times[1]) * 3600:
                            return True, BrushDeleteType.SEEDTIME
            if remove_rule.get("ratio") and ratio:
                rule_ratios = remove_rule.get("ratio").split("#")
                if rule_ratios[0]:
                    if len(rule_ratios) > 1 and rule_ratios[1]:
                        if float(ratio) > float(rule_ratios[1]):
                            return True, BrushDeleteType.RATIO
            if remove_rule.get("uploadsize") and uploaded:
                rule_uploadsizes = remove_rule.get("uploadsize").split("#")
                if rule_uploadsizes[0]:
                    if len(rule_uploadsizes) > 1 and rule_uploadsizes[1]:
                        if float(uploaded) > float(rule_uploadsizes[1]) * 1024 ** 3:
                            return True, BrushDeleteType.UPLOADSIZE
            if remove_rule.get("dltime") and dltime:
                rule_times = remove_rule.get("dltime").split("#")
                if rule_times[0]:
                    if len(rule_times) > 1 and rule_times[1]:
                        if float(dltime) > float(rule_times[1]) * 3600:
                            return True, BrushDeleteType.DLTIME
            if remove_rule.get("avg_upspeed") and avg_upspeed:
                rule_avg_upspeeds = remove_rule.get("avg_upspeed").split("#")
                if rule_avg_upspeeds[0]:
                    if len(rule_avg_upspeeds) > 1 and rule_avg_upspeeds[1]:
                        if float(avg_upspeed) < float(rule_avg_upspeeds[1]) * 1024:
                            return True, BrushDeleteType.AVGUPSPEED
            if remove_rule.get("iatime") and iatime:
                rule_times = remove_rule.get("iatime").split("#")
                if rule_times[0]:
                    if len(rule_times) > 1 and rule_times[1]:
                        if float(iatime) > float(rule_times[1]) * 3600:
                            return True, BrushDeleteType.IATIME
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
        return False, BrushDeleteType.NOTDELETE
