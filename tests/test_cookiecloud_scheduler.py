import unittest
from unittest.mock import patch

from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler import Scheduler
from app.scheduler_manager import SchedulerManager


class CookieCloudSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.saved = {
            "server": "https://cookiecloud.example.com", "key": "test-key",
            "password": "test-password", "interval": 30,
        }
        self.config = self._patch("app.scheduler.SystemConfig").return_value
        self.config.get_system_config.side_effect = lambda key: dict(self.saved)
        self._patch("app.scheduler.get_site_signin_config").return_value = {"cron": "08:00"}
        self._patch("app.scheduler.SiteSignin")
        self._patch("app.scheduler.MetaHelper")
        self._patch("app.scheduler.SiteUserInfo")
        self.logs = self._patch("app.scheduler.log")
        self.manager = SchedulerManager.__wrapped__(timezone="UTC")
        self.manager.create_group("system")
        self.addCleanup(self.manager.shutdown, wait=True)
        self._patch("app.scheduler.SchedulerManager").return_value = self.manager
        self.manager._scheduler.start(paused=True)
        self.service = Scheduler.__wrapped__()
        self._patch_object(self.manager.create_group("system"), "print_jobs")
        self.service.run_service()
        self.group = self.service.SCHEDULER
        self.other_jobs = {
            job.id: (job, job.next_run_time) for job in self.group.get_jobs()
            if job.id != "system:cookiecloud_sync"
        }

    def _patch(self, target):
        patcher = patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _patch_object(self, target, name, **kwargs):
        patcher = patch.object(target, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _job(self):
        return self.group.get_job("cookiecloud_sync")

    def _assert_other_jobs_unchanged(self):
        for job_id, (original, next_run_time) in self.other_jobs.items():
            current = self.group.get_job(job_id)
            self.assertIs(original, current)
            self.assertEqual(next_run_time, current.next_run_time)

    def test_start_restores_saved_period_and_concurrency_limits(self):
        job = self._job()
        self.assertIsInstance(job.trigger, IntervalTrigger)
        self.assertEqual(1800, job.trigger.interval.total_seconds())
        self.assertEqual(1, job.max_instances)
        self.assertTrue(job.coalesce)
        self.assertEqual(6, len(self.group.get_jobs()))

    def test_credentials_change_preserves_next_run_and_other_jobs(self):
        original = self._job()
        next_run = original.next_run_time
        self.saved.update(key="new-key", password="new-password")

        self.assertTrue(self.service.reload_cookiecloud_config())

        self.assertIs(original, self._job())
        self.assertEqual(next_run, self._job().next_run_time)
        self._assert_other_jobs_unchanged()

    def test_period_change_only_replaces_cookiecloud_job(self):
        old_callback = self._job().func
        self.saved["interval"] = 120
        self.assertTrue(self.service.reload_cookiecloud_config())
        self.assertEqual(7200, self._job().trigger.interval.total_seconds())
        self._assert_other_jobs_unchanged()
        with patch.object(self.service, "_run_cookiecloud_sync") as sync:
            old_callback()
            sync.assert_not_called()
            self._job().func()
            sync.assert_called_once_with()

    def test_zero_removes_task_and_cancels_already_queued_callback(self):
        old_callback = self._job().func
        self.saved["interval"] = 0
        self.assertTrue(self.service.reload_cookiecloud_config())
        self.assertIsNone(self._job())
        with patch.object(self.service, "_run_cookiecloud_sync") as sync:
            old_callback()
            sync.assert_not_called()
        self._assert_other_jobs_unchanged()

    def test_incomplete_credentials_disable_task_until_complete(self):
        for key in ("server", "key", "password"):
            with self.subTest(key=key):
                previous = self.saved.pop(key)
                self.assertTrue(self.service.reload_cookiecloud_config())
                self.assertIsNone(self._job())
                self.saved[key] = previous
                self.assertTrue(self.service.reload_cookiecloud_config())
                self.assertIsNotNone(self._job())
        self._assert_other_jobs_unchanged()

    def test_invalid_or_unreadable_config_disables_old_task_without_exposing_secrets(self):
        for value in (-1, 10081, 1.5, True, "test-password", None):
            with self.subTest(interval=value):
                self.saved["interval"] = value
                self.assertFalse(self.service.reload_cookiecloud_config())
                self.assertIsNone(self._job())
                self.saved["interval"] = 30
                self.assertTrue(self.service.reload_cookiecloud_config())
        self.config.get_system_config.side_effect = RuntimeError("test-password")
        self.assertFalse(self.service.reload_cookiecloud_config())
        self.assertIsNone(self._job())
        self.assertNotIn("test-password", str(self.logs.mock_calls))
        self._assert_other_jobs_unchanged()

    def test_legacy_configuration_without_interval_uses_three_hour_default(self):
        self.saved.pop("interval")
        self.assertTrue(self.service.reload_cookiecloud_config())
        self.assertEqual(10800, self._job().trigger.interval.total_seconds())
        self._assert_other_jobs_unchanged()

    def test_reload_before_start_does_not_start_a_scheduler(self):
        self.service.SCHEDULER = None
        with patch("app.scheduler.SchedulerManager") as manager:
            self.assertTrue(self.service.reload_cookiecloud_config())
        manager.assert_not_called()
        self.assertIsNone(self.service.SCHEDULER)

    def test_failed_replacement_can_retry_same_period_or_restore_old_period(self):
        for restored_interval in (60, 30):
            with self.subTest(restored_interval=restored_interval):
                self.saved["interval"] = 60
                with patch.object(self.group, "add_job", side_effect=RuntimeError("test-password")):
                    self.assertFalse(self.service.reload_cookiecloud_config())
                self.saved["interval"] = restored_interval
                self.assertTrue(self.service.reload_cookiecloud_config())
                self.assertEqual(restored_interval * 60, self._job().trigger.interval.total_seconds())
                self.saved["interval"] = 30
                self.assertTrue(self.service.reload_cookiecloud_config())
        self.assertNotIn("test-password", str(self.logs.mock_calls))
        self._assert_other_jobs_unchanged()

    def test_callback_uses_current_saved_configuration_and_safe_status_logs(self):
        with patch("web.actions.sites.SiteActions") as actions, patch("app.helper.DbHelper") as database:
            actions.return_value.cookiecloud_sync.return_value = {"code": 0, "msg": "test-password"}
            self.service._run_cookiecloud_sync()
            actions.assert_called_once_with(database.return_value)
            actions.return_value.cookiecloud_sync.assert_called_once_with({})
            self.logs.info.assert_called()

            actions.return_value.cookiecloud_sync.return_value = {"code": 1, "msg": "test-password"}
            self.service._run_cookiecloud_sync()
            self.logs.warn.assert_called()

            actions.return_value.cookiecloud_sync.side_effect = RuntimeError("test-password")
            self.service._run_cookiecloud_sync()
            self.logs.error.assert_called()
        self.assertNotIn("test-password", str(self.logs.mock_calls))

    def test_stop_cancels_old_callback_and_restart_restores_period(self):
        old_callback = self._job().func
        self.service.stop_service()
        with patch.object(self.service, "_run_cookiecloud_sync") as sync:
            old_callback()
            sync.assert_not_called()
        self.service.run_service()
        self.group = self.service.SCHEDULER
        self.assertEqual(1800, self._job().trigger.interval.total_seconds())


if __name__ == "__main__":
    unittest.main()
