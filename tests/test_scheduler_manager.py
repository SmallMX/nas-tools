import unittest
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock, Thread, get_ident, local
from unittest.mock import patch

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_SUBMITTED
from sqlalchemy import text

from app.db import MainDb, remove_db_session
from app.db.main_db import _Session
from app.scheduler_manager import SchedulerManager


class SchedulerManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = SchedulerManager.__wrapped__(
            timezone="UTC", executor_workers={"system": 1, "brush": 2, "remover": 1})
        self.releases = []
        self.addCleanup(self._shutdown)

    def _shutdown(self):
        for event in self.releases:
            event.set()
        self.manager.shutdown(wait=True)

    def _release_event(self):
        event = Event()
        self.releases.append(event)
        return event

    @staticmethod
    def _add_now(group, func, job_id):
        return group.add_job(func=func, trigger="date", id=job_id,
                             run_date=datetime.now(timezone.utc), misfire_grace_time=10)

    def _wait(self, event, message):
        self.assertTrue(event.wait(timeout=3), message)

    def test_groups_share_engine_keep_job_ids_isolated_and_start_once(self):
        self.assertIsNone(self.manager._scheduler)
        system = self.manager.create_group("system")
        engine = self.manager._scheduler
        brush = self.manager.create_group("brush")
        self.assertIs(engine, self.manager._scheduler)
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        system_job = system.add_job(func=lambda: None, trigger="date", run_date=tomorrow, id="shared")
        brush_job = brush.add_job(func=lambda: None, trigger="date", run_date=tomorrow, id="shared")

        self.assertEqual("system:shared", system_job.id)
        self.assertEqual("brush:shared", brush_job.id)
        self.assertIs(system_job, system.get_job("shared"))
        self.assertIs(system_job, system.get_job("system:shared"))
        self.assertIsNone(system.get_job("brush:shared"))
        self.assertIsNone(system_job.next_run_time)
        self.assertIsNone(brush_job.next_run_time)
        self.assertFalse(system.running)
        with patch.object(engine, "start", wraps=engine.start) as start:
            system.start()
            system.start()
            brush.start()
            start.assert_called_once()
        self.assertEqual((1, True, 1), (system_job.max_instances, system_job.coalesce,
                                       system_job.misfire_grace_time))

        brush_next_run = brush_job.next_run_time
        system.shutdown(wait=False)
        system.shutdown(wait=False)
        self.assertEqual([], system.get_jobs())
        self.assertIs(brush_job, brush.get_job("shared"))
        self.assertEqual(brush_next_run, brush_job.next_run_time)
        self.assertTrue(brush.running)
        self.assertTrue(engine.running)

    def test_each_executor_enforces_its_capacity_without_blocking_other_owners(self):
        limits = {"system": 1, "brush": 2, "remover": 1}
        groups = {owner: self.manager.create_group(owner) for owner in limits}
        releases = {owner: self._release_event() for owner in limits}
        saturated = {owner: Event() for owner in limits}
        active = dict.fromkeys(limits, 0)
        peaks = dict.fromkeys(limits, 0)
        completed = []
        timed_out = []
        all_done = Event()
        lock = Lock()
        total_jobs = sum(limit + 1 for limit in limits.values())

        def work(owner):
            with lock:
                active[owner] += 1
                peaks[owner] = max(peaks[owner], active[owner])
                if active[owner] == limits[owner]:
                    saturated[owner].set()
            try:
                if not releases[owner].wait(timeout=5):
                    timed_out.append(owner)
            finally:
                with lock:
                    active[owner] -= 1
                    completed.append(owner)
                    if len(completed) == total_jobs:
                        all_done.set()

        for owner, group in groups.items():
            for index in range(limits[owner] + 1):
                self._add_now(group, lambda owner=owner: work(owner), f"task-{index}")
            group.start()
        for owner in limits:
            self._wait(saturated[owner], f"{owner} 应能独立使用自己的执行器")
        with lock:
            self.assertEqual(limits, active)
        for release in releases.values():
            release.set()
        self._wait(all_done, "所有排队任务应执行完成")

        self.assertEqual(limits, peaks)
        self.assertEqual([], timed_out)
        self.assertEqual(total_jobs, len(completed))

    def test_owner_shutdown_invalidates_queued_old_callbacks(self):
        group = self.manager.create_group("system")
        entered = Event()
        release = self._release_event()
        stale_ran = Event()
        fresh_ran = Event()
        submitted = Event()

        def block():
            entered.set()
            release.wait(timeout=5)

        self.manager._scheduler.add_listener(
            lambda event: submitted.set() if event.job_id == "system:queued" else None,
            EVENT_JOB_SUBMITTED)
        self._add_now(group, block, "blocker")
        group.start()
        self._wait(entered, "先占满本组执行器")
        self._add_now(group, stale_ran.set, "queued")
        self._wait(submitted, "旧任务必须已进入执行器队列")

        group.shutdown(wait=False)
        replacement = self.manager.create_group("system")
        self._add_now(replacement, fresh_ran.set, "fresh")
        replacement.start()
        release.set()
        self._wait(fresh_ran, "新分组的任务应能正常执行")

        self.assertFalse(stale_ran.is_set(), "已停止分组中尚未开始的回调不得执行")

    def test_owner_wait_true_waits_for_its_own_jobs_only(self):
        system = self.manager.create_group("system")
        brush = self.manager.create_group("brush")
        system_entered, brush_entered = Event(), Event()
        system_release, brush_release = self._release_event(), self._release_event()
        brush_finished = Event()
        stop_started, stopped = Event(), Event()

        def system_job():
            system_entered.set()
            system_release.wait(timeout=5)

        def brush_job():
            brush_entered.set()
            brush_release.wait(timeout=5)
            brush_finished.set()

        def stop_system():
            stop_started.set()
            system.shutdown(wait=True)
            stopped.set()

        self._add_now(system, system_job, "system-running")
        self._add_now(brush, brush_job, "brush-running")
        system.start()
        brush.start()
        self._wait(system_entered, "系统任务应已运行")
        self._wait(brush_entered, "刷流任务应已运行")
        waiter = Thread(target=stop_system, daemon=True)
        waiter.start()
        try:
            self._wait(stop_started, "停止操作应已开始")
            self.assertFalse(stopped.wait(timeout=0.05), "wait=True 必须等待本组在途任务")
            system_release.set()
            self._wait(stopped, "本组完成后不得继续等待其他组")
            self.assertFalse(brush_finished.is_set())
            self.assertTrue(brush.running)
            self.assertTrue(self.manager._scheduler.running)
        finally:
            system_release.set()
            brush_release.set()
            waiter.join(timeout=3)
        self.assertFalse(waiter.is_alive())

    def test_recreated_job_keeps_max_instances_one_while_old_job_is_running(self):
        group = self.manager.create_group("brush")
        first_entered, next_entered, rejected_overlap = Event(), Event(), Event()
        release = self._release_event()
        lock = Lock()
        active = 0
        peak = 0
        runs = 0

        def work():
            nonlocal active, peak, runs
            with lock:
                active += 1
                peak = max(peak, active)
                runs += 1
                first = runs == 1
            try:
                if first:
                    first_entered.set()
                    release.wait(timeout=5)
                else:
                    next_entered.set()
            finally:
                with lock:
                    active -= 1

        self.manager._scheduler.add_listener(
            lambda event: rejected_overlap.set() if event.job_id == "brush:repeat" else None,
            EVENT_JOB_MAX_INSTANCES)
        group.add_job(func=work, trigger="interval", seconds=0.02, id="repeat")
        group.start()
        self._wait(first_entered, "原任务应已开始")
        group.shutdown(wait=False)
        replacement = self.manager.create_group("brush")
        replacement.add_job(func=work, trigger="interval", seconds=0.02, id="repeat")
        replacement.start()
        self._wait(rejected_overlap, "旧任务仍在运行时新任务应遵守 max_instances=1")
        self.assertFalse(next_entered.is_set())

        release.set()
        self._wait(next_entered, "原任务完成后重建任务应能执行")
        replacement.shutdown(wait=True)
        self.assertEqual(1, peak)

    def test_global_shutdown_stops_shared_engine_and_is_idempotent(self):
        groups = [self.manager.create_group(owner) for owner in ("system", "brush", "remover")]
        for group in groups:
            group.start()
        engine = self.manager._scheduler
        self.assertTrue(engine.running)

        self.manager.shutdown(wait=True)
        self.manager.shutdown(wait=True)

        self.assertFalse(engine.running)
        self.assertTrue(all(not group.running for group in groups))

    def test_pending_replacement_uses_latest_job_and_preserves_explicit_pause(self):
        group = self.manager.create_group("system")
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        group.add_job(lambda: None, "interval", id="replaced", hours=1)
        replacement = group.add_job(lambda: None, "interval", id="replaced", hours=2,
                                    replace_existing=True)
        paused = group.add_job(lambda: None, "interval", id="paused", hours=1, next_run_time=None)
        scheduled = group.add_job(lambda: None, "interval", id="scheduled", hours=1,
                                  next_run_time=tomorrow)

        group.start()

        self.assertIs(replacement, group.get_job("replaced"))
        self.assertIsNotNone(replacement.next_run_time)
        self.assertEqual(timedelta(hours=2), replacement.trigger.interval)
        self.assertIsNone(paused.next_run_time)
        self.assertEqual(tomorrow, scheduled.next_run_time)

    def test_partial_group_start_failure_cleans_only_failed_group_and_can_retry(self):
        system = self.manager.create_group("system")
        system.start()
        brush = self.manager.create_group("brush")
        brush.add_job(lambda: None, "interval", id="first", hours=1)
        brush.add_job(lambda: None, "interval", id="second", hours=1)
        engine = self.manager._scheduler
        original_resume = engine.resume_job

        def resume(job_id):
            if job_id == "brush:second":
                raise RuntimeError("resume failed")
            return original_resume(job_id)

        with patch.object(engine, "resume_job", side_effect=resume):
            with self.assertRaisesRegex(RuntimeError, "resume failed"):
                brush.start()

        self.assertTrue(system.running)
        self.assertTrue(engine.running)
        self.assertEqual([], brush.get_jobs())
        replacement = self.manager.create_group("brush")
        replacement.add_job(lambda: None, "interval", id="first", hours=1)
        replacement.start()
        brush.shutdown(wait=False)
        self.assertIsNotNone(replacement.get_job("first"))
        with self.assertRaises(RuntimeError):
            brush.start()
        with self.assertRaises(RuntimeError):
            brush.add_job(lambda: None, "interval", hours=1)

    def test_engine_start_failure_releases_pools_and_allows_fresh_engine(self):
        group = self.manager.create_group("system")
        group.add_job(lambda: None, "interval", id="first", hours=1)
        engine = self.manager._scheduler
        error = RuntimeError("engine startup failed")
        with patch.object(engine, "start", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                group.start()

        self.assertIs(error, raised.exception)
        self.assertIsNone(self.manager._scheduler)
        self.assertTrue(all(executor._pool._shutdown for executor in engine._executors.values()))
        replacement = self.manager.create_group("system")
        replacement.add_job(lambda: None, "interval", id="first", hours=1)
        replacement.start()
        self.assertTrue(replacement.running)
        self.assertIsNot(engine, self.manager._scheduler)

    def test_tasks_can_stop_their_own_group_without_waiting_on_each_other(self):
        group = self.manager.create_group("brush")
        entered = Barrier(2)
        completed = Event()
        completions = []
        lock = Lock()

        def stop_own_group():
            entered.wait(timeout=3)
            group.shutdown(wait=True)
            with lock:
                completions.append(True)
                if len(completions) == 2:
                    completed.set()

        self._add_now(group, stop_own_group, "first")
        self._add_now(group, stop_own_group, "second")
        group.start()
        self._wait(completed, "本组任务同时停止时不能互相等待")
        self.assertFalse(group.running)

    def test_success_exception_and_fast_jobs_cleanup_session_in_their_worker_thread(self):
        thread_state = local()
        worker_threads = {}
        cleanups = []
        completed_ids = set()
        completed = Event()
        lock = Lock()
        groups = {owner: self.manager.create_group(owner) for owner in ("system", "brush", "remover")}
        kinds = {"system": "success", "brush": "exception", "remover": "fast"}

        def job(kind):
            thread_state.kind = kind
            worker_threads[kind] = get_ident()
            MainDb().session.execute(text("SELECT 1"))
            if kind == "exception":
                raise ValueError("expected test failure")

        def cleanup():
            thread_id = get_ident()
            had_session = _Session.registry.has()
            remove_db_session()
            with lock:
                cleanups.append((getattr(thread_state, "kind", None), thread_id,
                                 had_session, _Session.registry.has()))

        def job_completed(event):
            with lock:
                completed_ids.add(event.job_id)
                if len(completed_ids) == len(kinds):
                    completed.set()

        self.manager._scheduler.add_listener(job_completed, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        with patch("app.scheduler_manager.remove_db_session", side_effect=cleanup):
            for owner, group in groups.items():
                self._add_now(group, lambda kind=kinds[owner]: job(kind), kinds[owner])
                group.start()
            self._wait(completed, "成功、异常和快速任务均应结束")
            self.manager.shutdown(wait=True)

        self.assertEqual(3, len(cleanups))
        self.assertEqual(set(kinds.values()), {kind for kind, *_ in cleanups})
        for kind, thread_id, had_session, has_session_after in cleanups:
            self.assertEqual(worker_threads[kind], thread_id)
            self.assertNotEqual(get_ident(), thread_id)
            self.assertTrue(had_session)
            self.assertFalse(has_session_after)


if __name__ == "__main__":
    unittest.main()
