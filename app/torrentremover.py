import json
from threading import Lock

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler

import log
from app.conf import ModuleConf
from app.db import remove_db_session
from app.db.models import TorrentRemoveTask
from app.downloader import Downloader
from app.helper import DbHelper
from app.message import Message
from app.utils import ExceptionUtils
from app.utils.commons import singleton
from config import Config

lock = Lock()


@singleton
class TorrentRemover(object):
    message = None
    downloader = None
    dbhelper = None

    _scheduler = None
    _remove_tasks = {}

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.message = Message()
        self.downloader = Downloader()
        self.dbhelper = DbHelper()
        # 移出现有任务
        self.stop_service()
        # 读取任务任务列表
        removetasks = self.dbhelper.get_torrent_remove_tasks()
        self._remove_tasks = {}
        for task in removetasks:
            config = task.config
            self._remove_tasks[str(task.id)] = {
                "id": task.id,
                "name": task.name,
                "downloader": task.downloader,
                "onlynastool": task.onlynastool,
                "samedata": task.samedata,
                "action": task.action,
                "config": json.loads(config) if config else {},
                "interval": task.interval,
                "enabled": task.enabled,
            }
        if not self._remove_tasks:
            return
        # 启动删种任务
        self._scheduler = BackgroundScheduler(timezone=Config().get_timezone())
        self._scheduler.add_listener(self.__remove_job_db_session,
                                     EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        remove_flag = False
        for task in self._remove_tasks.values():
            if task.get("enabled") and task.get("interval") and task.get("config"):
                remove_flag = True
                self._scheduler.add_job(func=self.auto_remove_torrents,
                                        args=[task.get("id")],
                                        trigger='interval',
                                        seconds=int(task.get("interval")) * 60)
        if remove_flag:
            self._scheduler.print_jobs()
            self._scheduler.start()
            log.info("自动删种服务启动")

    def stop_service(self):
        """幂等停止自动删种调度器，不等待正在运行的任务。"""
        scheduler = self._scheduler
        self._scheduler = None
        if not scheduler:
            return
        try:
            scheduler.remove_all_jobs()
            if scheduler.running:
                scheduler.shutdown(wait=False)
        except Exception as error:
            ExceptionUtils.exception_traceback(error)

    @staticmethod
    def __remove_job_db_session(_event):
        remove_db_session()

    def get_torrent_remove_tasks(self, taskid=None):
        """
        获取删种任务详细信息
        """
        if taskid:
            task = self._remove_tasks.get(str(taskid))
            return task if task else {}
        return self._remove_tasks

    def auto_remove_torrents(self, taskids=None):
        """
        处理自动删种任务，由定时服务调用
        :param taskids: 自动删种任务的ID
        """
        # 获取自动删种任务
        tasks = []
        # 如果没有指定任务ID，则处理所有启用任务
        if not taskids:
            for task in self._remove_tasks.values():
                if task.get("enabled") and task.get("interval") and task.get("config"):
                    tasks.append(task)
        # 如果指定任务id，则处理指定任务无论是否启用
        elif isinstance(taskids, list):
            for taskid in taskids:
                task = self._remove_tasks.get(str(taskid))
                if task:
                    tasks.append(task)
        else:
            task = self._remove_tasks.get(str(taskids))
            tasks = [task] if task else []
        if not tasks:
            return
        for task in tasks:
            try:
                lock.acquire()
                # 获取需删除种子列表
                downloader_type = ModuleConf.TORRENTREMOVER_DICT.get(task.get("downloader")).get("downloader_type")
                task.get("config")["samedata"] = task.get("samedata")
                task.get("config")["onlynastool"] = task.get("onlynastool")
                torrents = self.downloader.get_remove_torrents(
                    downloader=downloader_type,
                    config=task.get("config")
                )
                log.info(f"【TorrentRemover】自动删种任务：{task.get('name')} 获取符合处理条件种子数 {len(torrents)}")
                title = f"自动删种任务：{task.get('name')}"
                action = task.get("action")
                success_items = []
                failed_count = 0
                for torrent in torrents:
                    torrent_id = torrent.get("id")
                    name = torrent.get("name")
                    site = torrent.get("site")
                    size = round((torrent.get("size") or 0) / 1024 / 1024 / 1024, 3)
                    text_item = f"{name} 来自站点：{site} 大小：{size} GB"
                    if action == 1:
                        success = self.downloader.stop_torrents(downloader=downloader_type, ids=[torrent_id])
                        action_text = "暂停种子"
                    elif action in [2, 3]:
                        success = self.downloader.delete_torrents(downloader=downloader_type,
                                                                  delete_file=action == 3,
                                                                  ids=[torrent_id])
                        action_text = "删除种子及文件" if action == 3 else "删除种子"
                    else:
                        success = False
                        action_text = "处理种子"
                    if success:
                        success_items.append(text_item)
                        log.info(f"【TorrentRemover】{action_text}成功：{text_item}")
                    else:
                        failed_count += 1
                        log.error(f"【TorrentRemover】{action_text}失败：{name}，id={torrent_id}")

                if action == 1:
                    summary = f"共暂停{len(success_items)}个种子"
                elif action == 3:
                    summary = f"共删除{len(success_items)}个种子（及文件）"
                else:
                    summary = f"共删除{len(success_items)}个种子"
                if failed_count:
                    log.warn(f"【TorrentRemover】自动删种任务：{task.get('name')} 处理失败 {failed_count} 个")
                if success_items and title:
                    text = f"{summary}\n" + "\n".join(success_items)
                    self.message.send_brushtask_remove_message(title=title, text=text)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【TorrentRemover】自动删种任务：{task.get('name')}异常：{str(e)}")
            finally:
                lock.release()

    def update_torrent_remove_task(self, data):
        """
        更新自动删种任务
        """
        tid = data.get("tid")
        name = data.get("name")
        if not name:
            return False, "名称参数不合法"
        action = data.get("action")
        if not str(action).isdigit() or int(action) not in [1, 2, 3]:
            return False, "动作参数不合法"
        else:
            action = int(action)
        interval = data.get("interval")
        if not str(interval).isdigit():
            return False, "运行间隔参数不合法"
        else:
            interval = int(interval)
        enabled = data.get("enabled")
        if not str(enabled).isdigit() or int(enabled) not in [0, 1]:
            return False, "状态参数不合法"
        else:
            enabled = int(enabled)
        samedata = data.get("samedata")
        if not str(samedata).isdigit() or int(samedata) not in [0, 1]:
            return False, "处理辅种参数不合法"
        else:
            samedata = int(samedata)
        onlynastool = data.get("onlynastool")
        if not str(onlynastool).isdigit() or int(onlynastool) not in [0, 1]:
            return False, "仅处理NASTOOL添加种子参数不合法"
        else:
            onlynastool = int(onlynastool)
        ratio = data.get("ratio") or 0
        if not str(ratio).replace(".", "").isdigit():
            return False, "分享率参数不合法"
        else:
            ratio = round(float(ratio), 2)
        seeding_time = data.get("seeding_time") or 0
        if not str(seeding_time).isdigit():
            return False, "做种时间参数不合法"
        else:
            seeding_time = int(seeding_time)
        upload_avs = data.get("upload_avs") or 0
        if not str(upload_avs).isdigit():
            return False, "平均上传速度参数不合法"
        else:
            upload_avs = int(upload_avs)
        size = data.get("size")
        size = str(size).split("-") if size else []
        if size and (len(size) != 2 or not str(size[0]).isdigit() or not str(size[-1]).isdigit()):
            return False, "种子大小参数不合法"
        else:
            size = [int(size[0]), int(size[-1])] if size else []
        tags = data.get("tags")
        tags = tags.split(";") if tags else []
        tags = [tag for tag in tags if tag]
        savepath_key = data.get("savepath_key")
        tracker_key = data.get("tracker_key")
        downloader = data.get("downloader")
        if downloader not in ModuleConf.TORRENTREMOVER_DICT.keys():
            return False, "下载器参数不合法"
        if downloader == "Qb":
            qb_state = data.get("qb_state")
            qb_state = qb_state.split(";") if qb_state else []
            qb_state = [state for state in qb_state if state]
            if qb_state:
                for qb_state_item in qb_state:
                    if qb_state_item not in ModuleConf.TORRENTREMOVER_DICT.get("Qb").get("torrent_state").keys():
                        return False, "种子状态参数不合法"
            qb_category = data.get("qb_category")
            qb_category = qb_category.split(";") if qb_category else []
            qb_category = [category for category in qb_category if category]
            tr_state = []
            tr_error_key = ""
        else:
            qb_state = []
            qb_category = []
            tr_state = data.get("tr_state")
            tr_state = tr_state.split(";") if tr_state else []
            tr_state = [state for state in tr_state if state]
            if tr_state:
                for tr_state_item in tr_state:
                    if tr_state_item not in ModuleConf.TORRENTREMOVER_DICT.get("Tr").get("torrent_state").keys():
                        return False, "种子状态参数不合法"
            tr_error_key = data.get("tr_error_key")
        config = {
            "ratio": ratio,
            "seeding_time": seeding_time,
            "upload_avs": upload_avs,
            "size": size,
            "tags": tags,
            "savepath_key": savepath_key,
            "tracker_key": tracker_key,
            "qb_state": qb_state,
            "qb_category": qb_category,
            "tr_state": tr_state,
            "tr_error_key": tr_error_key,
        }
        if not self.__persist_torrent_remove_task(tid=tid,
                                                  name=name,
                                                  action=action,
                                                  interval=interval,
                                                  enabled=enabled,
                                                  samedata=samedata,
                                                  onlynastool=onlynastool,
                                                  downloader=downloader,
                                                  config=config):
            return False, "自动删种任务保存失败"
        return True, "更新成功"

    def __persist_torrent_remove_task(self,
                                      tid,
                                      name,
                                      action,
                                      interval,
                                      enabled,
                                      samedata,
                                      onlynastool,
                                      downloader,
                                      config):
        values = {
            "name": name,
            "action": int(action),
            "interval": int(interval),
            "enabled": int(enabled),
            "samedata": int(samedata),
            "onlynastool": int(onlynastool),
            "downloader": downloader,
            "config": json.dumps(config),
        }
        db = self.dbhelper._db
        try:
            if tid:
                updated = db.query(TorrentRemoveTask).filter(TorrentRemoveTask.id == int(tid)).update(values)
                if updated != 1:
                    db.rollback()
                    return False
            else:
                db.insert(TorrentRemoveTask(**values))
            db.commit()
            return True
        except Exception as err:
            db.rollback()
            ExceptionUtils.exception_traceback(err)
            log.error("【TorrentRemover】保存自动删种任务失败：%s" % str(err))
            return False

    def delete_torrent_remove_task(self, taskid=None):
        """
        删除自动删种任务
        """
        if not taskid:
            return False
        else:
            self.dbhelper.delete_torrent_remove_task(tid=taskid)
            return True

    def get_remove_torrents(self, taskid):
        """
        获取满足自动删种任务的种子
        """
        task = self._remove_tasks.get(str(taskid))
        if not task:
            return False, []
        else:
            task.get("config")["samedata"] = task.get("samedata")
            task.get("config")["onlynastool"] = task.get("onlynastool")
            torrents = self.downloader.get_remove_torrents(
                downloader=ModuleConf.TORRENTREMOVER_DICT.get(task.get("downloader")).get("downloader_type"),
                config=task.get("config")
            )
            return True, torrents
