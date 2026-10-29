import copy
import inspect
import json
import unittest
from unittest.mock import Mock, patch

from app.utils import TokenCache
from app.utils.types import SearchType
from config import Config
from web import action as action_module
from web.action import WebAction
from web.actions import validation
from web.actions.download import DownloadActions
from web.actions.search import SearchActions
from web.actions.sites import SiteActions
from web.actions.system import SystemActions, get_restart_target_pid
from web.main import App
from web.security import generate_access_token


# 支持的动作名称快照，按所属领域排列，不从实现生成。
DOMAIN_COMMANDS = {
    "_search": """search media_info name_test get_recommend get_streaming_filters get_search_result search_media_infos
        get_tvseason_list get_categories clear_tmdb_cache delete_tmdb_cache modify_tmdb_cache
        media_detail media_similar media_recommendations media_person person_medias""".split(),
    "_downloads": """sch download download_link download_torrent pt_start pt_stop pt_remove pt_info
        test_connection add_downloader delete_downloader get_downloader get_downloaded get_downloading
        get_download_setting update_download_setting delete_download_setting get_download_dirs
        update_torrent_remove_task get_torrent_remove_task delete_torrent_remove_task
        get_remove_torrents auto_remove_torrents""".split(),
    "_sites": """update_site get_site get_brush_site_capabilities del_site get_site_favicon
        get_site_activity get_site_history get_site_seeding_info check_site_attr list_site_resources
        test_site get_sites get_indexers update_sites_cookie_ua set_site_captcha_code
        get_site_user_statistics cookiecloud_sync cookiecloud_save add_brushtask del_brushtask brushtask_detail
        run_brushtask list_brushtask_torrents""".split(),
    "_system": """logging restart logout update_config refresh_message net_test
        refresh_process update_message_client delete_message_client check_message_client
        get_message_client test_message_client set_system_config send_custom_message save_user_script""".split(),
}
TOOL_COMMANDS = {"tool_site_signin_status": "status", "tool_site_signin_run": "run",
                 "tool_site_signin_config_update": "update_config"}
PUBLIC_DELEGATES = {"get_recommend": "_search", "get_downloaded": "_downloads",
                    "get_search_result": "_search"}
STATIC_ALIASES = {
    "restart_server": SystemActions,
    "set_config_value": SystemActions,
    "get_system_message": SystemActions,
    "mediainfo_dict": SearchActions,
    "parse_brush_rule_string": SiteActions,
    "search_media_infos": SearchActions,
    "get_downloading": DownloadActions,
    "get_site_user_statistics": SiteActions,
    "send_custom_message": SystemActions,
    "media_detail": SearchActions,
}


class WebActionDispatchTest(unittest.TestCase):
    def setUp(self):
        database = patch("web.action.DbHelper")
        signin = patch("web.action.SiteSigninWebService")
        self.database = database.start().return_value
        self.signin = signin.start().return_value
        self.addCleanup(database.stop)
        self.addCleanup(signin.stop)
        self.action = WebAction()

    def test_active_commands_are_complete_and_bound_to_their_domains(self):
        commands = [command for names in DOMAIN_COMMANDS.values() for command in names]
        commands.extend(TOOL_COMMANDS)
        self.assertEqual(81, len(commands))
        self.assertEqual(len(commands), len(set(commands)))
        self.assertEqual(set(commands), set(self.action._actions))
        for attribute, names in DOMAIN_COMMANDS.items():
            domain = getattr(self.action, attribute)
            self.assertIs(self.database, domain.dbhelper)
            for command in names:
                with self.subTest(command=command):
                    owner = self.action if command in PUBLIC_DELEGATES else domain
                    self.assertEqual(getattr(owner, command), self.action._actions[command])
        for command, method in TOOL_COMMANDS.items():
            self.assertIs(getattr(self.signin, method), self.action._actions[command])
        self.assertIs(self.action._downloads, self.action._search.downloads)

    def test_public_method_signatures_and_static_calling_conventions_are_preserved(self):
        signatures = {
            "action": (("self", "cmd", "data"), {"data": None}),
            "api_action": (("self", "cmd", "data"), {"data": None}),
            "restart_server": ((), {}),
            "handle_message_job": (("msg", "in_from", "user_id", "user_name"),
                                   {"in_from": SearchType.OT, "user_id": None, "user_name": None}),
            "set_config_value": (("cfg", "cfg_key", "cfg_value"), {}),
            "get_system_message": (("lst_time",), {}),
            "mediainfo_dict": (("media_info",), {}),
            "get_recommend": (("self", "data"), {}),
            "get_downloaded": (("self", "data"), {}),
            "parse_brush_rule_string": (("rules",), {}),
            "get_search_result": (("self", "data"), {"data": None}),
            "search_media_infos": (("data",), {}),
            "get_downloading": (("data",), {"data": None}),
            "get_site_user_statistics": (("data",), {}),
            "send_custom_message": (("data",), {}),
            "media_detail": (("data",), {}),
        }
        public_methods = {name for name, value in vars(WebAction).items()
                          if not name.startswith("_") and callable(getattr(WebAction, name))}
        self.assertEqual(set(signatures), public_methods)
        for name, (names, defaults) in signatures.items():
            with self.subTest(method=name):
                parameters = inspect.signature(getattr(WebAction, name)).parameters
                self.assertEqual(names, tuple(parameters))
                self.assertEqual(defaults, {key: parameter.default for key, parameter in parameters.items()
                                            if parameter.default is not inspect.Parameter.empty})
                self.assertTrue(all(parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
                                    for parameter in parameters.values()))
                self.assertEqual(name in STATIC_ALIASES or name == "handle_message_job",
                                 isinstance(inspect.getattr_static(WebAction, name), staticmethod))
        self.assertIs(dict, inspect.signature(WebAction.parse_brush_rule_string).parameters["rules"].annotation)

    def test_public_instance_methods_delegate_to_shared_domain_instances(self):
        payload = {"page": 3}
        result = {"code": 0, "result": ["domain-result"]}
        for method, attribute in PUBLIC_DELEGATES.items():
            with self.subTest(method=method):
                with patch.object(getattr(self.action, attribute), method, return_value=result) as handler:
                    self.assertIs(result, getattr(self.action, method)(payload))
                    handler.assert_called_once_with(payload)
        for method in ("get_search_result",):
            with patch.object(getattr(self.action, PUBLIC_DELEGATES[method]), method) as handler:
                getattr(self.action, method)()
                handler.assert_called_once_with(None)

    def test_static_aliases_and_module_helpers_keep_original_import_paths(self):
        for name, domain in STATIC_ALIASES.items():
            with self.subTest(method=name):
                self.assertIs(getattr(domain, name), getattr(WebAction, name))
        helpers = ("get_allowed_file_roots", "is_valid_btih_magnet", "parse_brush_rule",
                   "prepare_message_client_config", "prepare_site_note", "resolve_allowed_file_path",
                   "validate_configured_site_url", "validate_site_config_url")
        for name in helpers:
            self.assertIs(getattr(validation, name), getattr(action_module, name))
        self.assertIs(get_restart_target_pid, action_module.get_restart_target_pid)

    def test_action_preserves_payload_result_and_handler_exception(self):
        payload = {"id": 7}
        result = {"retcode": 1, "retmsg": "failed"}
        handler = Mock(return_value=result)
        self.action._actions = {"known": handler}
        self.assertIs(result, self.action.action("known", payload))
        handler.assert_called_once_with(payload)
        self.assertEqual({"code": -1, "msg": "非授权访问！"}, self.action.action("unknown", payload))
        error = RuntimeError("domain failed")
        handler.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self.action.action("known", payload)
        self.assertIs(error, raised.exception)

    def test_api_response_keeps_legacy_keys_precedence_and_payload_shape(self):
        cases = (
            ({"code": 0, "msg": "done", "result": [1]}, 0, True, "done", {"result": [1]}),
            ({"retcode": 1, "retmsg": "failed", "item": 7}, 1, False, "failed", {"item": 7}),
            ({"code": "0", "msg": None, "retcode": 2, "retmsg": "ignored"}, "0", True, None, {}),
            ({"code": 2, "msg": "primary", "retcode": 0, "retmsg": "fallback", "data": []},
             2, False, "primary", {"data": []}),
            ({"code": None, "value": 1}, None, True, "", {"value": 1}),
            ({"result": [1]}, 0, True, "", {"result": [1]}),
        )
        for original, code, success, message, data in cases:
            with self.subTest(original=original):
                response = copy.deepcopy(original)
                self.action._actions = {"known": Mock(return_value=response)}
                self.assertEqual({"code": code, "success": success, "message": message, "data": data},
                                 self.action.api_action("known"))
        for response in (None, {}, [], False):
            self.action._actions = {"known": Mock(return_value=response)}
            self.assertEqual({"code": -1, "success": False, "message": "服务异常，未获取到返回结果"},
                             self.action.api_action("known"))


class WebActionAuthenticationBoundaryTest(unittest.TestCase):
    def setUp(self):
        self._patch_dict(App.config, {"TESTING": True})
        self.client = App.test_client()
        self.database = self._patch("web.action.DbHelper")
        self.signin = self._patch("web.action.SiteSigninWebService")
        self.admin_username = Config().get_config("app")["login_user"]
        self.token = generate_access_token(self.admin_username)
        TokenCache.set(self.token, self.token)
        self.addCleanup(TokenCache.delete, self.token)

    def _patch(self, target):
        patcher = patch(target)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def _patch_dict(self, target, values):
        patcher = patch.dict(target, values)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_request(self, handler, path, payload, allowed, headers=None):
        handler.reset_mock()
        self.database.reset_mock()
        self.signin.reset_mock()
        response = self.client.post(path, data=payload, headers=headers)
        self.assertEqual(200 if allowed else 401, response.status_code)
        self.assertEqual(0 if allowed else 401, response.get_json()["code"])
        if allowed:
            handler.assert_called_once()
            self.database.assert_called_once_with()
        else:
            handler.assert_not_called()
            self.database.assert_not_called()
            self.signin.assert_not_called()

    def test_ui_actions_accept_admin_and_reject_legacy_or_missing_session(self):
        cases = (
            (DownloadActions, "update_download_setting"),
            (SiteActions, "list_site_resources"),
            (SiteActions, "get_brush_site_capabilities"),
            (SiteActions, "set_site_captcha_code"),
            (SystemActions, "update_config"),
            (SearchActions, "media_info"),
        )
        for domain, command in cases:
            with patch.object(domain, command, autospec=True,
                              side_effect=lambda *args, **kwargs: {"code": 0, "result": "handled"}) as handler:
                for user_id in ("0", "1", None):
                    with self.subTest(command=command, user_id=user_id):
                        with self.client.session_transaction() as session:
                            session.clear()
                            if user_id is not None:
                                session["_user_id"] = user_id
                                session["_fresh"] = True
                        self._assert_request(handler, "/do", {"cmd": command, "data": json.dumps({"id": 7})},
                                             user_id == "0")

    def test_api_actions_accept_admin_and_reject_legacy_or_missing_token(self):
        legacy_token = generate_access_token("retired-user")
        TokenCache.set(legacy_token, legacy_token)
        self.addCleanup(TokenCache.delete, legacy_token)
        cases = (
            (DownloadActions, "update_download_setting", "/api/v1/download/config/update",
             {"sid": "7", "name": "example"}),
            (SiteActions, "brushtask_detail", "/api/v1/brushtask/info", {"id": "7"}),
            (SearchActions, "media_info", "/api/v1/media/info", {"type": "MOV", "id": "7"}),
            (SystemActions, "net_test", "/api/v1/service/network/test", {"url": "https://example.com"}),
            (SiteActions, "test_site", "/api/v1/site/test", {"id": 7}),
        )
        for domain, command, path, data in cases:
            with patch.object(domain, command, autospec=True,
                              side_effect=lambda *args, **kwargs: {"code": 0, "result": "handled"}) as handler:
                for token in (self.token, legacy_token, None):
                    with self.subTest(path=path, admin=token == self.token):
                        headers = {"Authorization": f"Bearer {token}"} if token else None
                        self._assert_request(handler, path, data, token == self.token, headers=headers)


if __name__ == "__main__":
    unittest.main()
