import unittest
from datetime import datetime, timezone
from threading import Event
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.message import Message
from app.message.client.telegram import Telegram
from app.scheduler import Scheduler
from app.scheduler_manager import SchedulerManager
from app.utils.http_utils import RequestUtils
from app.utils.types import SearchType


class SchedulerRuntimeConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = self._patch("app.scheduler.get_site_signin_config")
        self.config.return_value = {"cron": "08:00", "notify": True}
        self._patch("app.scheduler.SystemConfig").return_value.get_system_config.return_value = {}
        self._patch("app.scheduler.SiteSignin")
        self._patch("app.scheduler.MetaHelper")
        self._patch("app.scheduler.SiteUserInfo")
        self._patch("app.scheduler.log")
        manager = SchedulerManager.__wrapped__(timezone="UTC")
        group = manager.create_group("system")
        self.addCleanup(manager.shutdown, wait=True)
        self._patch("app.scheduler.SchedulerManager").return_value = manager
        # 使用真实 APScheduler 的 job/trigger 操作，暂停引擎以禁止业务任务执行。
        manager._scheduler.start(paused=True)
        self._patch_object(group, "print_jobs")
        self.shutdown = self._patch_object(manager._scheduler, "shutdown")
        scheduler_class = Scheduler.__closure__[0].cell_contents
        self.service = scheduler_class()
        self.service.run_service()
        self.scheduler = self.service.SCHEDULER
        signin_id = self.scheduler.get_job(self.service._site_signin_job_id).id
        self.other_jobs = {
            job.id: (job, getattr(job, "next_run_time", None))
            for job in self.scheduler.get_jobs()
            if job.id != signin_id
        }

    def _patch(self, target):
        patcher = patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _patch_object(self, target, name):
        patcher = patch.object(target, name)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _reload(self, cron, **settings):
        self.config.return_value = {"cron": cron, **settings}
        return self.service.reload_runtime_config()

    def _assert_other_jobs_unchanged(self):
        self.assertEqual(4, len(self.other_jobs))
        for job_id, (original, next_run_time) in self.other_jobs.items():
            current = self.scheduler.get_job(job_id)
            self.assertIs(original, current)
            self.assertEqual(next_run_time, getattr(current, "next_run_time", None))
        self.assertIs(self.scheduler, self.service.SCHEDULER)
        self.shutdown.assert_not_called()

    def test_non_schedule_changes_leave_all_jobs_untouched(self):
        jobs = self.scheduler.get_jobs()
        with patch.object(self.scheduler, "add_job") as add, \
                patch.object(self.scheduler, "remove_job") as remove:
            self._reload(" 08:00 ", concurrency=2, notify=False,
                         history_days=90, retry_keyword="超时")

        add.assert_not_called()
        remove.assert_not_called()
        self.assertEqual(jobs, self.scheduler.get_jobs())
        self._assert_other_jobs_unchanged()

    def test_schedule_modes_replace_only_signin_jobs_and_cancel_old_random_callback(self):
        main_id = self.service._site_signin_job_id
        date_id = self.service._site_signin_date_job_id
        self.assertIsInstance(self.scheduler.get_job(main_id).trigger, CronTrigger)

        self._reload("08:00-09:00")
        range_job = self.scheduler.get_job(main_id)
        self.assertIsInstance(range_job.trigger, CronTrigger)
        old_callback = range_job.func
        with patch("app.scheduler.random.randint", side_effect=[510, 25]):
            old_callback()
        date_job = self.scheduler.get_job(date_id)
        self.assertIsInstance(date_job.trigger, DateTrigger)
        self.assertEqual((8, 30, 25), (
            date_job.trigger.run_date.hour, date_job.trigger.run_date.minute,
            date_job.trigger.run_date.second,
        ))
        self._assert_other_jobs_unchanged()

        self._reload("12")
        interval_job = self.scheduler.get_job(main_id)
        self.assertIsInstance(interval_job.trigger, IntervalTrigger)
        self.assertEqual(12 * 3600, interval_job.trigger.interval.total_seconds())
        self.assertIsNone(self.scheduler.get_job(date_id))
        with patch.object(self.scheduler, "add_job") as add:
            old_callback()
        add.assert_not_called()
        self._assert_other_jobs_unchanged()

        self._reload("10:15")
        self.assertIsInstance(self.scheduler.get_job(main_id).trigger, CronTrigger)
        self._reload("")
        self.assertIsNone(self.scheduler.get_job(main_id))
        self.assertIsNone(self.scheduler.get_job(date_id))
        self._assert_other_jobs_unchanged()

    def test_reload_before_start_only_updates_configuration(self):
        self.service.SCHEDULER = None
        with patch("app.scheduler.SchedulerManager") as create:
            self._reload("23.5")

        create.assert_not_called()
        self.assertIsNone(self.service.SCHEDULER)
        self.assertEqual("23.5", self.service._site_signin_config["cron"])

    def test_invalid_interval_does_not_disturb_other_jobs(self):
        for cron in ("nan", "-1", "0", "25:00", "09:00-08:00"):
            with self.subTest(cron=cron):
                self.assertFalse(self._reload(cron))
                self.assertIsNone(self.scheduler.get_job(self.service._site_signin_job_id))
                self._assert_other_jobs_unchanged()

    def test_failed_schedule_replacement_retries_the_same_configuration(self):
        with patch.object(self.scheduler, "add_job", side_effect=RuntimeError("scheduler failed")):
            with self.assertRaisesRegex(RuntimeError, "scheduler failed"):
                self._reload("12")

        self.assertIsNone(self.scheduler.get_job(self.service._site_signin_job_id))
        self._assert_other_jobs_unchanged()
        self.assertTrue(self._reload("12"))

        job = self.scheduler.get_job(self.service._site_signin_job_id)
        self.assertIsInstance(job.trigger, IntervalTrigger)
        self.assertEqual(12 * 3600, job.trigger.interval.total_seconds())
        self._assert_other_jobs_unchanged()

    def test_restoring_old_cron_after_failed_replacement_recreates_missing_job(self):
        with patch.object(self.scheduler, "add_job", side_effect=RuntimeError("scheduler failed")):
            with self.assertRaisesRegex(RuntimeError, "scheduler failed"):
                self._reload("12")

        self.assertIsNone(self.scheduler.get_job(self.service._site_signin_job_id))
        self.assertTrue(self._reload("08:00"))

        job = self.scheduler.get_job(self.service._site_signin_job_id)
        self.assertIsInstance(job.trigger, CronTrigger)
        next_run = job.trigger.get_next_fire_time(None, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual((8, 0), (next_run.hour, next_run.minute))
        with patch.object(self.scheduler, "add_job") as add:
            self.assertTrue(self._reload("08:00"))
        add.assert_not_called()
        self._assert_other_jobs_unchanged()


class MessageRuntimeConfigTest(unittest.TestCase):
    def test_runtime_reload_keeps_database_clients_and_uses_updated_links(self):
        message_class = Message.__closure__[0].cell_contents
        service = message_class.__new__(message_class)
        service.dbhelper = Mock()
        service.messagecenter = Mock()
        client = Mock()
        client.send_msg.return_value = (True, "")
        active_clients = [{"name": "telegram", "client": client}]
        interactive_clients = {SearchType.TG: active_clients[0]}
        client_configs = {"1": {"name": "telegram"}}
        service._active_clients = active_clients
        service._active_interactive_clients = interactive_clients
        service._client_configs = client_configs

        with patch("app.message.message.Config") as config, \
                patch("app.message.message.DbHelper") as database, \
                patch("app.message.message.MessageCenter") as center, \
                patch.object(service, "stop_service") as stop:
            config.return_value.get_domain.return_value = "https://new.example"
            self.assertTrue(service.reload_runtime_config())
            self.assertTrue(service.send_channel_msg(
                SearchType.TG, "下载完成", url="downloaded"
            ))

        database.assert_not_called()
        center.assert_not_called()
        service.dbhelper.get_message_client.assert_not_called()
        stop.assert_not_called()
        client.stop_service.assert_not_called()
        client.reload_runtime_config.assert_called_once_with()
        self.assertIs(active_clients, service._active_clients)
        self.assertIs(interactive_clients, service._active_interactive_clients)
        self.assertIs(client_configs, service._client_configs)
        self.assertEqual("https://new.example?next=downloaded", client.send_msg.call_args.kwargs["url"])

    def test_client_failure_is_reported_without_skipping_other_clients(self):
        message_class = Message.__closure__[0].cell_contents
        for failure in (False, RuntimeError("client reload failed")):
            with self.subTest(failure=failure):
                service = message_class.__new__(message_class)
                first, second = Mock(), Mock()
                first.reload_runtime_config.return_value = failure
                if isinstance(failure, Exception):
                    first.reload_runtime_config.side_effect = failure
                second.reload_runtime_config.return_value = True
                service._active_clients = [
                    {"name": "first", "client": first},
                    {"name": "second", "client": second},
                ]
                with patch("app.message.message.Config"), patch("app.message.message.log"):
                    self.assertFalse(service.reload_runtime_config())
                    first.reload_runtime_config.assert_called_once_with()
                    second.reload_runtime_config.assert_called_once_with()
                    first.stop_service.assert_not_called()
                    second.stop_service.assert_not_called()

                    first.reload_runtime_config.side_effect = None
                    first.reload_runtime_config.return_value = True
                    self.assertTrue(service.reload_runtime_config())


class TelegramRuntimeConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = Mock()
        self.config.get_domain.return_value = "https://old.example/"
        self.config.get_config.return_value = {"telegram_webhook_secret": "old-secret"}
        self.config.get_proxies.return_value = None
        self.config.get_ua.return_value = "Old Agent"
        self._patch("app.message.client.telegram.Config").return_value = self.config
        self._patch("app.message.client.telegram.log")
        self.thread_helper = self._patch("app.message.client.telegram.ThreadHelper")
        self.request = self._patch("app.message.client.telegram.RequestUtils")
        self.request.return_value.get_res.return_value.json.return_value = {"ok": True}
        self.get_webhook = self._patch_object(Telegram, "_Telegram__get_bot_webhook")
        self.get_webhook.return_value = 1
        self.delete_webhook = self._patch_object(Telegram, "_Telegram__del_bot_webhook")

    def _patch(self, target):
        patcher = patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _patch_object(self, target, name):
        patcher = patch.object(target, name)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _client(self, webhook=True, interactive=False):
        client = Telegram({
            "token": "token", "chat_id": "chat", "webhook": webhook,
            "interactive": interactive,
        })
        self.get_webhook.reset_mock()
        self.delete_webhook.reset_mock()
        self.thread_helper.reset_mock()
        self.request.reset_mock()
        return client

    def _registration_values(self):
        self.request.return_value.get_res.assert_called_once()
        url = self.request.return_value.get_res.call_args.args[0]
        self.assertIn("/setWebhook?", url)
        return parse_qs(urlparse(url).query)

    def test_unrelated_configuration_changes_do_not_register_or_restart_clients(self):
        client = self._client()
        self.config.get_ua.return_value = "New Agent"
        self.config.get_proxies.return_value = {"https": "http://proxy.example:8080"}

        client.reload_runtime_config()

        self.get_webhook.assert_not_called()
        self.delete_webhook.assert_not_called()
        self.request.assert_not_called()
        self.thread_helper.assert_not_called()

    def test_domain_change_updates_existing_webhook_client(self):
        client = self._client()
        self.config.get_domain.return_value = "https://new.example/"
        self.get_webhook.return_value = 2

        client.reload_runtime_config()

        values = self._registration_values()
        self.assertEqual(["https://new.example/telegram"], values["url"])
        self.assertEqual(["old-secret"], values["secret_token"])
        self.delete_webhook.assert_called_once_with()
        self.thread_helper.assert_not_called()

    def test_secret_rotation_registers_even_when_webhook_url_is_unchanged(self):
        client = self._client()
        self.config.get_config.return_value = {"telegram_webhook_secret": "new-secret"}

        client.reload_runtime_config()

        values = self._registration_values()
        self.assertEqual(["https://old.example/telegram"], values["url"])
        self.assertEqual(["new-secret"], values["secret_token"])
        self.delete_webhook.assert_not_called()
        self.thread_helper.assert_not_called()
        self.request.reset_mock()
        self.get_webhook.reset_mock()
        client.reload_runtime_config()
        self.request.assert_not_called()
        self.get_webhook.assert_not_called()

    def test_failed_secret_rotation_retries_the_same_configuration(self):
        client = self._client()
        self.config.get_config.return_value = {"telegram_webhook_secret": "new-secret"}
        failed = Mock()
        failed.json.return_value = {"ok": False, "description": "temporary failure"}
        succeeded = Mock()
        succeeded.json.return_value = {"ok": True}
        self.request.return_value.get_res.side_effect = [failed, succeeded]

        self.assertFalse(client.reload_runtime_config())
        self.assertEqual("old-secret", client._webhook_secret)
        self.assertTrue(client.reload_runtime_config())

        self.assertEqual("new-secret", client._webhook_secret)
        calls = self.request.return_value.get_res.call_args_list
        self.assertEqual(2, len(calls))
        for call in calls:
            self.assertEqual(["new-secret"], parse_qs(urlparse(call.args[0]).query)["secret_token"])
        self.delete_webhook.assert_not_called()
        self.thread_helper.assert_not_called()

    def test_registration_exception_restores_runtime_values_for_retry(self):
        client = self._client()
        previous = (client._domain, client._webhook_url, client._webhook_secret)
        self.config.get_domain.return_value = "https://new.example"
        self.config.get_config.return_value = {"telegram_webhook_secret": "new-secret"}
        self.get_webhook.return_value = 2
        succeeded = Mock()
        succeeded.json.return_value = {"ok": True}
        self.request.return_value.get_res.side_effect = [RuntimeError("request failed"), succeeded]

        self.assertFalse(client.reload_runtime_config())
        self.assertEqual(previous, (client._domain, client._webhook_url, client._webhook_secret))
        self.assertTrue(client.reload_runtime_config())

        self.assertEqual(("https://new.example", "https://new.example/telegram", "new-secret"),
                         (client._domain, client._webhook_url, client._webhook_secret))
        self.assertEqual(2, self.request.return_value.get_res.call_count)
        self.thread_helper.assert_not_called()

    def test_restoring_old_webhook_after_failed_replacement_registers_it_again(self):
        client = self._client()
        self.config.get_domain.return_value = "https://new.example"
        self.get_webhook.return_value = 2
        failed = Mock()
        failed.json.return_value = {"ok": False, "description": "temporary failure"}
        succeeded = Mock()
        succeeded.json.return_value = {"ok": True}
        self.request.return_value.get_res.side_effect = [failed, succeeded]

        self.assertFalse(client.reload_runtime_config())
        self.delete_webhook.assert_called_once_with()
        self.assertEqual("https://old.example/telegram", client._webhook_url)

        self.config.get_domain.return_value = "https://old.example/"
        # 即使远端报告相同 URL，也不能忽略失败调用可能造成的密钥不一致。
        self.get_webhook.return_value = 1
        self.assertTrue(client.reload_runtime_config())

        calls = self.request.return_value.get_res.call_args_list
        self.assertEqual(2, len(calls))
        self.assertEqual(["https://new.example/telegram"],
                         parse_qs(urlparse(calls[0].args[0]).query)["url"])
        self.assertEqual(["https://old.example/telegram"],
                         parse_qs(urlparse(calls[1].args[0]).query)["url"])
        self.request.reset_mock()
        self.get_webhook.reset_mock()
        self.assertTrue(client.reload_runtime_config())
        self.request.assert_not_called()
        self.get_webhook.assert_not_called()
        self.thread_helper.assert_not_called()

    def test_registration_reports_matching_url_and_missing_or_unreachable_configuration(self):
        client = self._client()
        self.assertTrue(client._Telegram__set_bot_webhook())
        self.get_webhook.return_value = 0
        self.assertFalse(client._Telegram__set_bot_webhook())
        client._webhook_secret = ""
        self.assertFalse(client._Telegram__set_bot_webhook())
        client._webhook_url = None
        self.assertFalse(client._Telegram__set_bot_webhook())
        self.request.assert_not_called()

    def test_invalid_webhook_runtime_values_do_not_register(self):
        client = self._client()
        self.config.get_domain.return_value = ""
        self.assertFalse(client.reload_runtime_config())
        self.config.get_domain.return_value = "https://new.example"
        self.config.get_config.return_value = {"telegram_webhook_secret": ""}
        self.assertFalse(client.reload_runtime_config())

        self.get_webhook.assert_not_called()
        self.request.assert_not_called()
        self.thread_helper.assert_not_called()

    def test_polling_keeps_its_event_and_sends_with_latest_proxy_and_user_agent(self):
        client = self._client(webhook=False, interactive=True)
        event = client._message_proxy_event
        self.assertIsInstance(event, Event)
        self.config.get_domain.return_value = "https://new.example"
        self.config.get_config.return_value = {"telegram_webhook_secret": "new-secret"}
        self.config.get_ua.return_value = "New Agent"
        proxies = {"https": "http://proxy.example:8080"}
        self.config.get_proxies.return_value = proxies

        client.reload_runtime_config()

        self.assertIs(event, client._message_proxy_event)
        self.assertFalse(event.is_set())
        self.assertTrue(client._enabled)
        self.assertEqual("new-secret", client._webhook_secret)
        self.assertEqual("https://new.example", client._domain)
        self.get_webhook.assert_not_called()
        self.delete_webhook.assert_not_called()
        self.thread_helper.assert_not_called()
        with patch("app.message.client.telegram.RequestUtils", RequestUtils), \
                patch("app.utils.http_utils.Config", return_value=self.config), \
                patch("app.utils.http_utils.requests.get") as get:
            get.return_value.json.return_value = {"ok": True}
            self.assertEqual((True, ""), client.send_msg("test"))

        self.assertEqual(proxies, get.call_args.kwargs["proxies"])
        self.assertEqual("New Agent", get.call_args.kwargs["headers"]["User-Agent"])


if __name__ == "__main__":
    unittest.main()
