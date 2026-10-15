"""共享后台调度引擎：独立任务组、执行池和工作线程资源清理。"""

from functools import wraps
from threading import Condition, RLock, local
from uuid import uuid4

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.util import undefined

import log
from app.db import remove_db_session
from app.utils.commons import get_singleton_instance, singleton
from config import Config


@singleton
class SchedulerManager:
    EXECUTOR_WORKERS = {"system": 20, "brush": 10, "remover": 10}

    def __init__(self, timezone=None, executor_workers=None):
        self._timezone = timezone
        self._workers = dict(self.EXECUTOR_WORKERS)
        if executor_workers:
            self._workers.update(executor_workers)
        self._scheduler = None
        self._groups = {}
        self._condition = Condition(RLock())
        self._current = local()
        self._closed = False

    @staticmethod
    def executor_alias(owner):
        # 使用 default 承载系统任务，避免 APScheduler 额外创建默认执行池。
        return "default" if owner == "system" else owner

    def create_group(self, owner):
        if owner not in self.EXECUTOR_WORKERS:
            raise ValueError("未知后台任务组")
        with self._condition:
            if self._closed:
                raise RuntimeError("后台调度管理器已关闭")
            group = self._groups.get(owner)
            if group is not None and not group._closed:
                return group
            if self._scheduler is None:
                self._scheduler = BackgroundScheduler(
                    timezone=self._timezone or Config().get_timezone(),
                    executors={
                        self.executor_alias(name): ThreadPoolExecutor(workers)
                        for name, workers in self._workers.items()
                    },
                    job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 1},
                )
            group = SchedulerGroup(self, owner)
            self._groups[owner] = group
            return group

    def shutdown(self, wait=False):
        """进程退出时统一关闭；业务任务组不能关闭其他组或重新启动此管理器。"""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            scheduler = self._scheduler
            self._scheduler = None
            for group in self._groups.values():
                group._closed = True
                group._active = False
                group._pending_run_times.clear()
        wait = wait and getattr(self._current, "group", None) is None
        self._close_engine(scheduler, wait)

    @staticmethod
    def _close_engine(scheduler, wait=False):
        # 不持管理器锁等待工作线程：任务 finally 仍需取得该锁报告完成。
        if scheduler is None:
            return
        try:
            scheduler.remove_all_jobs()
        finally:
            if scheduler.running:
                scheduler.shutdown(wait=wait)
            else:
                # 从未启动的执行池也由管理器统一释放。
                for executor in scheduler._executors.values():
                    executor.shutdown(wait=wait)


class SchedulerGroup:
    def __init__(self, manager, owner):
        self._manager = manager
        self.owner = owner
        self._prefix = f"{owner}:"
        self._active = False
        self._closed = False
        self._running_jobs = 0
        self._pending_run_times = {}

    @property
    def running(self):
        with self._manager._condition:
            return self._active and not self._closed

    def _job_id(self, job_id):
        job_id = str(job_id)
        return job_id if job_id.startswith(self._prefix) else self._prefix + job_id

    def _require_open(self):
        if self._closed or self._manager._closed:
            raise RuntimeError("后台任务组已停止")

    def _wrap_job(self, func):
        @wraps(func)
        def run(*args, **kwargs):
            manager = self._manager
            with manager._condition:
                # 闭包绑定本次任务组，重建同名组不会让旧队列里的任务复活。
                if self._closed or not self._active or manager._closed:
                    return None
                self._running_jobs += 1
            previous = getattr(manager._current, "group", None)
            manager._current.group = self
            try:
                return func(*args, **kwargs)
            finally:
                try:
                    remove_db_session()
                finally:
                    manager._current.group = previous
                    with manager._condition:
                        self._running_jobs -= 1
                        manager._condition.notify_all()
        return run

    def add_job(self, func, trigger=None, args=None, kwargs=None, id=None,
                replace_existing=False, **options):
        with self._manager._condition:
            self._require_open()
            job_id = self._job_id(id or uuid4().hex)
            next_run_time = options.get("next_run_time", undefined)
            if not self._active:
                # 引擎可能已在为其他组运行，本组注册完成前不得提前执行。
                options["next_run_time"] = None
            job = self._manager._scheduler.add_job(
                self._wrap_job(func), trigger, args=args, kwargs=kwargs,
                id=job_id, executor=self._manager.executor_alias(self.owner),
                replace_existing=replace_existing, **options,
            )
            scheduler = self._manager._scheduler
            if replace_existing and not scheduler.running:
                # APS 未启动时会暂存重复 ID；只保留最后一份，避免恢复运行时间时改到旧任务。
                while scheduler.get_job(job_id) is not job:
                    scheduler.remove_job(job_id)
            if not self._active:
                self._pending_run_times[job_id] = next_run_time
            return job

    def start(self):
        failed_engine = None
        try:
            with self._manager._condition:
                self._require_open()
                if self._active:
                    return
                scheduler = self._manager._scheduler
                for job_id, next_run_time in list(self._pending_run_times.items()):
                    if next_run_time is undefined:
                        scheduler.resume_job(job_id)
                    else:
                        scheduler.modify_job(job_id, next_run_time=next_run_time)
                self._active = True
                if not scheduler.running:
                    try:
                        scheduler.start()
                    except BaseException:
                        # 启动失败的执行池可能已部分初始化，不能再复用该引擎。
                        failed_engine = scheduler
                        self._manager._scheduler = None
                        for group in self._manager._groups.values():
                            group._closed = True
                            group._active = False
                            group._pending_run_times.clear()
                        self._manager._groups.clear()
                        raise
                self._pending_run_times.clear()
        except BaseException:
            try:
                if failed_engine is not None:
                    self._manager._close_engine(failed_engine)
                else:
                    self.shutdown(wait=False)
            except Exception as error:
                log.error("【Scheduler】清理启动失败的任务组失败：%s" % type(error).__name__)
            raise

    def get_job(self, job_id):
        with self._manager._condition:
            if self._closed:
                return None
            return self._manager._scheduler.get_job(self._job_id(job_id))

    def get_jobs(self):
        with self._manager._condition:
            if self._closed:
                return []
            return [job for job in self._manager._scheduler.get_jobs()
                    if job.id.startswith(self._prefix)]

    def remove_job(self, job_id):
        with self._manager._condition:
            if self._closed:
                raise JobLookupError(job_id)
            job_id = self._job_id(job_id)
            self._manager._scheduler.remove_job(job_id)
            self._pending_run_times.pop(job_id, None)

    def remove_all_jobs(self):
        with self._manager._condition:
            if self._closed:
                return
            for job in self.get_jobs():
                try:
                    self._manager._scheduler.remove_job(job.id)
                except JobLookupError:
                    pass
            self._pending_run_times.clear()

    def print_jobs(self):
        for job in self.get_jobs():
            print(job)

    def shutdown(self, wait=True):
        manager = self._manager
        with manager._condition:
            if not self._closed:
                self._active = False
                try:
                    self.remove_all_jobs()
                finally:
                    self._closed = True
            # 从本组任务中停止时不能等待其他同样请求停止的任务。
            if wait and getattr(manager._current, "group", None) is not self:
                manager._condition.wait_for(lambda: self._running_jobs == 0)


def shutdown_schedulers():
    """释放已存在的共享引擎，不因退出流程创建服务。"""
    manager = get_singleton_instance(SchedulerManager)
    if manager is not None:
        try:
            manager.shutdown(wait=False)
        except Exception as error:
            log.error("【Scheduler】关闭共享调度器失败：%s" % type(error).__name__)
