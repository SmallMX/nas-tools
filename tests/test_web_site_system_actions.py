import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from flask import Flask

from web.action import WebAction


class WebSiteSystemActionsTest(unittest.TestCase):
    def setUp(self):
        self.database = self._patch("web.action.DbHelper").return_value
        self._patch("web.action.SiteSigninWebService")
        self.sites = self._patch("web.actions.sites.Sites").return_value
        self.brush = self._patch("web.actions.sites.BrushTask").return_value
        self.message = self._patch("web.actions.system.Message").return_value
        self.action = WebAction()

    def _patch(self, target):
        patcher = patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_site_list_masks_credentials_without_mutating_sources_and_keeps_basic_mode(self):
        sites = [{"id": 1, "name": "Configured", "cookie": "private-cookie", "apikey": "private-key"},
                 {"id": 2, "name": "Empty", "cookie": "", "apikey": None}]
        original = copy.deepcopy(sites)
        self.sites.get_sites.return_value = sites

        result = self.action.action("get_sites", {"rss": 1, "statistic": True})

        self.assertEqual({"code": 0, "sites": [
            {"id": 1, "name": "Configured", "cookie": "******", "apikey": "******"}, original[1],
        ]}, result)
        self.assertEqual(original, sites)
        self.sites.get_sites.assert_called_once_with(rss=True, brush=False, signin=False, statistic=True)
        self.sites.get_site_dict.return_value = {1: "Configured"}
        result = self.action.action("get_sites", {"basic": True, "brush": True})
        self.assertEqual({"code": 0, "sites": {1: "Configured"}}, result)
        self.sites.get_site_dict.assert_called_once_with(rss=False, brush=True, signin=False, statistic=False)

    def test_capability_actions_share_flags_without_leaking_site_details_to_brush(self):
        saved_site = {"id": 7, "cookie": "private-cookie", "apikey": "private-key",
                      "rssurl": "https://tracker.example/rss?passkey=private"}
        self.sites.get_sites.return_value = saved_site
        self.sites.get_grapsite_conf.return_value = {"FREE": 1, "2XFREE": "", "HR": "Y"}
        flags = {"site_free": True, "site_2xfree": False, "site_hr": True}

        detail = self.action.action("get_site", {"id": 7})
        capabilities = self.action.action("get_brush_site_capabilities", {"id": 7})
        checked = self.action.action("check_site_attr", {"url": saved_site["rssurl"]})

        self.assertEqual({"code": 0, "site": saved_site, **flags}, detail)
        self.assertEqual({"code": 0, **flags}, capabilities)
        self.assertEqual(capabilities, checked)
        self.assertNotIn("private", json.dumps(capabilities))
        self.sites.get_sites.reset_mock()
        empty = self.action.action("get_brush_site_capabilities", None)
        self.assertEqual({"code": 0, "site_free": False, "site_2xfree": False, "site_hr": False}, empty)
        self.sites.get_sites.assert_not_called()

    def test_site_edit_preserves_masked_cookie_renames_history_then_refreshes_services(self):
        self.database.get_site_by_name.return_value = []
        self.database.get_site_by_id.return_value = [SimpleNamespace(id=7, name="Old", cookie="private-cookie")]
        self.database.update_config_site.return_value = True
        events = Mock()
        for method, name in ((self.database.update_config_site, "save"),
                             (self.database.update_site_user_statistics_site_name, "rename_users"),
                             (self.database.update_site_seed_info_site_name, "rename_seeds"),
                             (self.database.update_site_statistics_site_name, "rename_statistics"),
                             (self.sites.init_config, "sites_reload"), (self.brush.init_config, "brush_reload")):
            events.attach_mock(method, name)

        result = self.action.action("update_site", {
            "site_id": 7, "site_name": "Renamed", "site_cookie": "******",
            "site_rssurl": "https://tracker.example/rss", "site_signurl": "https://tracker.example/",
            "site_note": {"message": "Y", "rule": "retired"},
        })

        self.assertEqual({"code": True}, result)
        saved = self.database.update_config_site.call_args.kwargs
        self.assertEqual("private-cookie", saved["cookie"])
        self.assertEqual({"message": "Y"}, json.loads(saved["note"]))
        self.assertEqual(["save", "rename_users", "rename_seeds", "rename_statistics", "sites_reload", "brush_reload"],
                         [event[0] for event in events.mock_calls])
        for rename in (self.database.update_site_user_statistics_site_name,
                       self.database.update_site_seed_info_site_name, self.database.update_site_statistics_site_name):
            rename.assert_called_once_with("Renamed", "Old")

    def test_site_delete_keeps_history_cleanup_and_both_service_refreshes(self):
        self.database.delete_config_site.return_value = True
        events = Mock()
        events.attach_mock(self.database.delete_config_site, "delete")
        events.attach_mock(self.database.delete_site_signin_history, "history")
        events.attach_mock(self.sites.init_config, "sites_reload")
        events.attach_mock(self.brush.init_config, "brush_reload")

        result = self.action.action("del_site", {"id": 7})

        self.assertEqual({"code": True}, result)
        self.assertEqual([call.delete(7), call.history(7), call.sites_reload(), call.brush_reload()], events.mock_calls)

    def test_cookiecloud_rejects_unsafe_url_before_saving_or_fetching(self):
        with patch("web.actions.sites.SystemConfig") as config, \
                patch("web.actions.sites.CookieCloudHelper") as cloud:
            result = self.action.action("cookiecloud_sync", {
                "server": "file:///tmp/private", "key": "private-key", "password": "private-password"})

        self.assertEqual(1, result["code"])
        config.assert_not_called()
        cloud.assert_not_called()
        self.database.update_site_cookie_ua.assert_not_called()
        self.sites.init_config.assert_not_called()

    def test_message_details_are_masked_without_changing_stored_credentials(self):
        detail = {"id": 7, "name": "Telegram", "config": {"token": "private-token", "chat_id": "123"}}
        original = copy.deepcopy(detail)
        self.message.get_message_client_info.return_value = detail

        result = self.action.action("get_message_client", {"cid": 7})

        self.assertEqual("******", result["detail"]["config"]["token"])
        self.assertEqual("123", result["detail"]["config"]["chat_id"])
        self.assertEqual(original, detail)
        self.message.get_message_client_info.return_value = None
        self.assertEqual({"code": 1, "msg": "消息渠道不存在", "detail": {}},
                         self.action.action("get_message_client", {"cid": 7}))

    def test_message_save_and_connection_test_preserve_existing_passwords_consistently(self):
        existing = {"config": {"token": "private-token", "chat_id": "old-chat"}}
        self.message.get_message_client_info.return_value = existing
        self.message.get_status.return_value = True
        self.database.insert_message_client.return_value = True
        for command in ("update_message_client", "test_message_client"):
            for password in (None, "", "******"):
                with self.subTest(command=command, password=password):
                    self.message.reset_mock()
                    self.database.reset_mock()
                    config = {"token": password, "chat_id": "new-chat"}
                    payload = {"cid": 7, "name": "Telegram", "type": "telegram", "config": config,
                               "switchs": [], "interactive": 0, "enabled": 1}
                    result = self.action.action(command, payload)
                    expected = {"token": "private-token", "chat_id": "new-chat"}
                    self.assertEqual({"code": 0}, result)
                    self.assertEqual(password, config["token"])
                    self.assertEqual("private-token", existing["config"]["token"])
                    if command == "update_message_client":
                        saved = self.database.insert_message_client.call_args.kwargs
                        self.assertEqual(expected, json.loads(saved["config"]))
                        self.assertEqual(7, saved["cid"])
                        self.message.init_config.assert_called_once_with()
                        self.message.get_status.assert_not_called()
                    else:
                        self.message.get_status.assert_called_once_with(ctype="telegram", config=expected)
                        self.database.insert_message_client.assert_not_called()
                        self.message.init_config.assert_not_called()

    def test_message_storage_failure_keeps_api_error_and_does_not_reload_service(self):
        self.message.get_message_client_info.return_value = {"config": {"token": "private-token", "chat_id": "123"}}
        self.database.insert_message_client.return_value = False

        response = self.action.api_action("update_message_client", {
            "cid": 7, "name": "Telegram", "type": "telegram",
            "config": json.dumps({"token": "******", "chat_id": "123"}), "switchs": [],
        })

        self.assertEqual({"code": 1, "success": False, "message": "消息渠道保存失败", "data": {}}, response)
        self.database.insert_message_client.assert_called_once()
        self.message.init_config.assert_not_called()

    def test_message_config_validation_stops_both_storage_and_connection_test(self):
        for command in ("update_message_client", "test_message_client"):
            with self.subTest(command=command):
                response = self.action.action(command, {
                    "type": "telegram", "config": {"token": "private-token", "chat_id": ""}, "switchs": []})
                self.assertEqual(1, response["code"])
        self.database.insert_message_client.assert_not_called()
        self.message.get_status.assert_not_called()
        self.message.init_config.assert_not_called()

    def test_message_lookup_errors_are_not_reclassified_as_invalid_input(self):
        error = ValueError("stored client cannot be loaded")
        self.message.get_message_client_info.side_effect = error
        for command in ("update_message_client", "test_message_client"):
            with self.subTest(command=command), self.assertRaises(ValueError) as raised:
                self.action.action(command, {"cid": 7, "type": "telegram", "switchs": []})
            self.assertIs(error, raised.exception)
        self.database.insert_message_client.assert_not_called()
        self.message.get_status.assert_not_called()

    def test_site_cookie_progress_keeps_extra_permission_check(self):
        app = Flask("web-action-progress-test")
        with app.test_request_context(), \
                patch("web.actions.system.request_has_system_settings", return_value=False), \
                patch("web.actions.system.ProgressHelper") as progress:
            response = self.action.action("refresh_process", {"type": "sitecookie"})

        self.assertEqual({"code": 403, "value": 0, "text": "权限不足"}, response)
        progress.assert_not_called()


if __name__ == "__main__":
    unittest.main()
