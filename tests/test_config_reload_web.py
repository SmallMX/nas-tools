import copy
import logging
import unittest
from collections import deque
from unittest.mock import Mock, patch
from uuid import uuid4

import log
from app import config_reload
from web import main as web_main
from web.action import WebAction
from web.tools.site_signin import SiteSigninWebService


class ConfigReloadEntryTest(unittest.TestCase):
    def test_save_before_runtime_initialization_only_persists_configuration(self):
        updated = {"app": {"user_agent": "updated"}}
        config = Mock()
        config.save_config.return_value = True
        with patch.object(config_reload, "_runtime_reloader", None), \
                patch.object(config_reload, "Config", return_value=config), \
                patch.object(config_reload, "ConfigReloader") as coordinator, \
                patch.object(config_reload, "apply_config_changes") as apply:
            self.assertTrue(config_reload.save_config_and_apply(updated))

        config.save_config.assert_called_once_with(updated)
        coordinator.assert_not_called()
        apply.assert_not_called()

    def test_initialized_runtime_uses_installed_coordinator_and_its_result(self):
        updated = {"app": {"user_agent": "updated"}}
        reloader = Mock()
        with patch.object(config_reload, "_runtime_reloader", reloader), \
                patch.object(config_reload, "Config") as config:
            for result in (True, False):
                with self.subTest(result=result):
                    reloader.save.reset_mock()
                    reloader.save.return_value = result
                    self.assertIs(result, config_reload.save_config_and_apply(updated))
                    reloader.save.assert_called_once_with(updated)
            config.assert_not_called()


class WebConfigSaveTest(unittest.TestCase):
    def setUp(self):
        self.original = {"app": {"user_agent": "initial"}}
        self.config = Mock()
        self.config.get_config.return_value = self.original
        for target, value in (
                ("web.action.Config", Mock(return_value=self.config)),
                ("web.action.DbHelper", Mock()),
                ("web.action.SiteSigninWebService", Mock())):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.action = WebAction()

    def test_validation_only_does_not_save_or_apply(self):
        with patch.object(config_reload, "save_config_and_apply") as save:
            response = self.action.action("update_config", {"app.user_agent": "updated", "test": True})

        self.assertEqual({"code": 0}, response)
        save.assert_not_called()
        self.config.save_config.assert_not_called()
        self.assertEqual({"app": {"user_agent": "initial"}}, self.original)

    def test_normal_save_uses_shared_entry_and_reports_application_failure(self):
        for succeeded in (True, False):
            with self.subTest(succeeded=succeeded):
                with patch.object(config_reload, "save_config_and_apply", return_value=succeeded) as save:
                    response = self.action.action("update_config", {"app.user_agent": "updated"})
                save.assert_called_once_with({"app": {"user_agent": "updated"}})
                if succeeded:
                    self.assertEqual({"code": 0}, response)
                else:
                    self.assertEqual({"code": 1, "msg": "配置保存或应用失败，请检查系统日志"}, response)
                self.config.save_config.assert_not_called()
                self.assertEqual({"app": {"user_agent": "initial"}}, self.original)


class SiteSigninConfigSaveTest(unittest.TestCase):
    def setUp(self):
        self.current = {"cron": "08:00", "concurrency": 5, "retry_keyword": "失败",
                        "notify": True, "history_days": 30}
        self.original = {"app": {"user_agent": "initial"}, "tools": {"site_signin": self.current}}
        self.config = Mock()
        self.config.get_config.return_value = self.original
        self.signin = Mock()
        for target, value in (
                ("web.tools.site_signin.Config", Mock(return_value=self.config)),
                ("web.tools.site_signin.SiteSignin", Mock(return_value=self.signin)),
                ("web.tools.site_signin.get_site_signin_config", Mock(return_value=self.current))):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = SiteSigninWebService()

    def test_tool_save_uses_shared_entry_without_extra_service_reload(self):
        expected = copy.deepcopy(self.original)
        expected["tools"]["site_signin"]["cron"] = "10:00"
        with patch("web.tools.site_signin.save_config_and_apply", return_value=True) as save:
            response = self.service.update_config({"cron": "10:00"})

        self.assertEqual({"code": 0, "msg": "工具设置已保存"}, response)
        save.assert_called_once_with(expected)
        self.signin.init_config.assert_not_called()
        self.config.save_config.assert_not_called()
        self.assertEqual("08:00", self.current["cron"])

    def test_tool_save_failure_preserves_error_contract_and_hides_exception_details(self):
        for failure in (False, OSError("token=must-not-be-logged")):
            with self.subTest(failure=type(failure).__name__):
                with patch("web.tools.site_signin.save_config_and_apply", side_effect=[failure]) as save, \
                        patch("web.tools.site_signin.log.error") as error_log:
                    response = self.service.update_config({"cron": "10:00"})
                self.assertEqual({"code": 1, "msg": "工具配置保存失败，请检查系统日志"}, response)
                save.assert_called_once()
                self.signin.init_config.assert_not_called()
                self.assertNotIn("must-not-be-logged", str(error_log.call_args_list))
                self.assertEqual("08:00", self.current["cron"])


class WebSecurityReloadTest(unittest.TestCase):
    def test_security_reload_updates_existing_app_and_cookie_settings(self):
        app = web_main.App
        config = Mock()
        with patch.dict(app.config), patch.object(web_main, "Config", return_value=config):
            for secure, expected in (("on", True), (False, False)):
                with self.subTest(secure=secure):
                    secret = f"test-secret-{expected}"
                    config.get_config.return_value = {"flask_secret_key": secret, "session_cookie_secure": secure}
                    web_main.configure_security()
                    self.assertIs(app, web_main.App)
                    self.assertEqual(secret, app.secret_key)
                    for prefix in ("SESSION_COOKIE", "REMEMBER_COOKIE"):
                        self.assertIs(expected, app.config[f"{prefix}_SECURE"])
                        self.assertTrue(app.config[f"{prefix}_HTTPONLY"])
                        self.assertEqual("Lax", app.config[f"{prefix}_SAMESITE"])

    def test_missing_secret_is_rejected_without_partial_config_changes(self):
        config = Mock()
        app = web_main.App
        with patch.dict(app.config, SECRET_KEY="preserved-secret", SESSION_COOKIE_SECURE=True,
                        REMEMBER_COOKIE_SECURE=True), patch.object(web_main, "Config", return_value=config):
            previous = app.config.copy()
            for secret in (None, ""):
                with self.subTest(secret=secret):
                    config.get_config.return_value = {"flask_secret_key": secret, "session_cookie_secure": False}
                    with self.assertRaises(RuntimeError):
                        web_main.configure_security()
                    self.assertIs(app, web_main.App)
                    self.assertEqual(previous, app.config)


class LoggerConfigReloadTest(unittest.TestCase):
    def test_reload_reuses_logger_preserves_queue_and_only_replaces_owned_handlers(self):
        name = f"nastool-config-reload-test-{uuid4().hex}"
        logger = logging.getLogger(name)
        logger.propagate = False
        external_handler = logging.NullHandler()
        logger.addHandler(external_handler)

        def cleanup_logger():
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()
            logging.Logger.manager.loggerDict.pop(name, None)

        self.addCleanup(cleanup_logger)
        config = Mock()
        config.get_config.return_value = {"logtype": "console", "loglevel": "info"}
        entries = [{"level": "INFO", "source": "test", "text": "existing log"}]
        queue = deque(entries, maxlen=200)
        with patch.object(log.Logger, "_Logger__instance", {}), \
                patch.object(log, "Config", return_value=config), \
                patch.object(log, "LOG_QUEUE", queue), patch.object(log, "LOG_INDEX", 23), \
                patch.object(external_handler, "close", wraps=external_handler.close) as close_external:
            instance = log.Logger.get_instance(name)
            for level, expected_level in (("debug", logging.DEBUG), ("error", logging.ERROR), ("info", logging.INFO)):
                with self.subTest(level=level):
                    old_handler = next(handler for handler in logger.handlers if handler is not external_handler)
                    config.get_config.return_value = {"logtype": "console", "loglevel": level}
                    with patch.object(old_handler, "close", wraps=old_handler.close) as close_old:
                        log.Logger.reload_config()
                        close_old.assert_called_once_with()
                    self.assertIs(instance, log.Logger.get_instance(name))
                    self.assertIs(logger, instance.logger)
                    self.assertEqual(expected_level, logger.level)
                    self.assertEqual(2, len(logger.handlers))
                    self.assertIn(external_handler, logger.handlers)
                    self.assertNotIn(old_handler, logger.handlers)
                    self.assertIs(queue, log.LOG_QUEUE)
                    self.assertEqual(entries, list(log.LOG_QUEUE))
                    self.assertEqual(23, log.LOG_INDEX)
            close_external.assert_not_called()


if __name__ == "__main__":
    unittest.main()
