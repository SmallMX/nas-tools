from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import log
from app.utils.exception_utils import ExceptionUtils
from app.utils.commons import singleton


@singleton
class ThreadHelper:
    _thread_num = 50
    executor = None
    _executor_lock = Lock()

    def __init__(self):
        self.init_config()

    def init_config(self):
        """确保配置热加载或此前关闭后有可用的执行器。"""
        with self._executor_lock:
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=self._thread_num)

    def start_thread(self, func, kwargs):
        with self._executor_lock:
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=self._thread_num)
            future = self.executor.submit(func, *kwargs)

        def log_failure(completed):
            try:
                completed.result()
            except Exception as error:
                ExceptionUtils.exception_traceback(error)
                log.error("【Thread】后台任务 %s 执行失败：%s" % (
                    getattr(func, "__name__", str(func)), error
                ))
            finally:
                from app.db import remove_db_session
                remove_db_session()

        future.add_done_callback(log_failure)
        return future

    def shutdown(self):
        """幂等关闭公共线程池，并取消尚未开始的后台任务。"""
        with self._executor_lock:
            executor = self.executor
            self.executor = None
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)
