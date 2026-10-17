import unittest
import io
import json
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from app.utils import TokenCache
from app.utils import StringUtils
from web.security import (
    desensitize_config_dict,
    generate_access_token,
    request_is_admin,
    sanitize_message_client,
)
from web.action import (
    WebAction,
    get_restart_target_pid,
    is_valid_btih_magnet,
    parse_brush_rule,
    prepare_message_client_config,
    prepare_site_note,
    resolve_allowed_file_path,
    validate_configured_site_url,
    validate_site_config_url,
)
from web.actions.download import DownloadActions
from web.actions.system import SystemActions
from web.main import App
from web.routes.system_files import create_sqlite_backup
from web.security import sanitize_brush_task, sanitize_downloader
from app.db.main_db import RETIRED_DATABASE_TABLES
from app.helper import DictHelper

class SecurityTest(unittest.TestCase):
    def setUp(self):
        App.config['TESTING'] = True
        self.client = App.test_client()

    def test_admin_check_fails_closed_without_request_context(self):
        self.assertFalse(request_is_admin())


    def test_library_dashboard_routes_removed(self):
        routes = {rule.rule for rule in App.url_map.iter_rules()}
        self.assertNotIn("/index", routes)
        self.assertNotIn("/library", routes)
        self.assertNotIn("/api/v1/library/space", routes)
        self.assertNotIn("/api/v1/organization/history/statistics", routes)

    @patch('builtins.eval')
    def test_rce_whitelist_eval_never_called(self, mock_eval):
        action_instance = WebAction()
        # Test malicious command injection
        res = action_instance.api_action(cmd='test_connection', data={"command": "import os; os.system('whoami')"})
        self.assertEqual(res.get("code"), 1)
        # Test basic eval expression bypass attempt
        res2 = action_instance.api_action(cmd='test_connection', data={"command": "1+1"})
        self.assertEqual(res2.get("code"), 1)
        # Assert builtins.eval was NEVER called!
        mock_eval.assert_not_called()

    def test_desensitize_config(self):
        cfg = {
            "app": {
                "login_password": "mysecretpassword",
                "rmt_tmdbkey": "mysecretkey",
                "fanart_api_key": "fanart-secret",
                "douban_api_key": "douban-key",
                "douban_api_secret": "douban-secret",
            },
            "security": {
                "api_key": "somekey",
                "flask_secret_key": "flask-secret",
                "telegram_webhook_secret": "telegram-secret",
            }
        }
        masked = desensitize_config_dict(cfg)
        self.assertEqual(masked["app"]["login_password"], "******")
        self.assertEqual(masked["app"]["rmt_tmdbkey"], "******")
        self.assertEqual(masked["app"]["fanart_api_key"], "******")
        self.assertEqual(masked["app"]["douban_api_key"], "******")
        self.assertEqual(masked["app"]["douban_api_secret"], "******")
        self.assertEqual(masked["security"]["api_key"], "******")
        self.assertEqual(masked["security"]["flask_secret_key"], "******")
        self.assertEqual(masked["security"]["telegram_webhook_secret"], "******")
        self.assertEqual(cfg["security"]["flask_secret_key"], "flask-secret")

    def test_retired_speed_limit_storage_cannot_be_recreated(self):
        response = WebAction().api_action(
            cmd="set_system_config",
            data={"key": "SpeedLimit", "value": {"qb_upload": 1}},
        )

        self.assertEqual(1, response["code"])
        self.assertEqual("", DictHelper().get("SystemConfig", "SpeedLimit"))

    def test_retired_downloader_types_cannot_be_recreated(self):
        custom_response = WebAction().api_action(
            cmd="add_downloader",
            data={"type": "pikpak", "name": "retired", "test": False},
        )
        preset_response = WebAction().api_action(
            cmd="update_download_setting",
            data={"name": "retired", "downloader": "PikPak"},
        )

        self.assertEqual(1, custom_response["code"])
        self.assertEqual(1, preset_response["code"])

    def test_retired_message_switches_cannot_be_recreated(self):
        response = WebAction().api_action(
            cmd="update_message_client",
            data={
                "name": "telegram",
                "type": "telegram",
                "config": {"token": "token", "chat_id": "chat"},
                "switchs": ["rss_added", {}],
                "interactive": 0,
                "enabled": 0,
            },
        )

        self.assertEqual(1, response["code"])

    def test_retired_site_note_fields_cannot_be_recreated(self):
        prepared_dict = json.loads(prepare_site_note({
            "message": "Y",
            "rule": "retired",
            "subtitle": "Y",
        }))
        prepared_string = json.loads(prepare_site_note(
            '{"message":"Y","rule":"retired","subtitle":"Y"}'
        ))

        self.assertEqual({"message": "Y"}, prepared_dict)
        self.assertEqual({"message": "Y"}, prepared_string)
        with self.assertRaises(ValueError):
            prepare_site_note("not-json")
        response = WebAction().api_action(
            cmd="update_site",
            data={"site_name": "invalid-note", "site_note": "not-json"},
        )
        self.assertEqual(400, response["code"])

    def test_retired_yaml_config_paths_cannot_be_recreated(self):
        config = {
            "app": {"login_user": "admin"},
            "media": {"category": "default-category"},
            "pt": {"pt_client": "qbittorrent"},
            "qbittorrent": {"qbhost": "old"},
            "security": {"api_key": "old"},
        }

        for key, value in (
            ("jackett.host", "http://retired"),
            ("Jackett.host", "http://retired"),
            ("pt.rmt_mode", "link"),
            ("PT.rmt_mode", "link"),
            ("media.movie_path", "/retired"),
            ("pt.pt_client", "client115"),
        ):
            with self.assertRaises(ValueError):
                WebAction.set_config_value(config, key, value)
        with self.assertRaises(ValueError):
            WebAction.set_config_value(config, "pt", {"rmt_mode": "link"})
        with self.assertRaises(ValueError):
            WebAction.set_config_value(config, "PT", {"RMT_MODE": "link"})

        WebAction.set_config_value(config, "pt", {
            "pt_client": "qbittorrent",
            "search_auto": True,
            "RMT_MODE": "link",
        })
        WebAction.set_config_value(config, "app", {
            "login_user": "updated",
            "init_files": ["retired.sql"],
        })
        WebAction.set_config_value(config, "qbittorrent", {
            "qbhost": "updated",
            "force_upload": True,
        })
        WebAction.set_config_value(config, "media", {
            "category": "updated-category",
            "movie_path": "/retired",
        })
        WebAction.set_config_value(config, "douban", {
            "cookie": "preserved",
            "auto_rss": True,
        })
        WebAction.set_config_value(
            config,
            "security",
            {
                "api_key": "updated",
                "media_server_webhook_allow_ip": "retired",
                "synology_webhook_allow_ip": "retired",
            },
        )

        self.assertNotIn("jackett", config)
        self.assertNotIn("rmt_mode", config["pt"])
        self.assertEqual({"category": "updated-category"}, config["media"])
        self.assertEqual({"cookie": "preserved"}, config["douban"])
        self.assertEqual("qbittorrent", config["pt"]["pt_client"])
        self.assertTrue(config["pt"]["search_auto"])
        self.assertEqual("updated", config["app"]["login_user"])
        self.assertNotIn("init_files", config["app"])
        self.assertEqual("updated", config["qbittorrent"]["qbhost"])
        self.assertNotIn("force_upload", config["qbittorrent"])
        self.assertEqual("updated", config["security"]["api_key"])
        self.assertNotIn(
            "media_server_webhook_allow_ip",
            config.get("security", {}),
        )
        self.assertNotIn("synology_webhook_allow_ip", config.get("security", {}))
        response = WebAction().api_action(
            cmd="update_config",
            data={"pt.rmt_mode": "link"},
        )
        self.assertEqual(1, response["code"])

    def test_optional_service_urls_require_explicit_http_addresses(self):
        config = {"app": {}, "laboratory": {}}

        WebAction.set_config_value(
            config, "app.ocr_server", " https://ocr.example.com/ "
        )
        WebAction.set_config_value(
            config, "laboratory.tmdb_proxy", "https://tmdb.example.com/"
        )

        self.assertEqual("https://ocr.example.com", config["app"]["ocr_server"])
        self.assertEqual("https://tmdb.example.com", config["laboratory"]["tmdb_proxy"])

        with self.assertRaises(ValueError):
            WebAction.set_config_value(config, "app.ocr_server", "file:///tmp/ocr")

        response = WebAction().api_action(
            cmd="cookiecloud_sync",
            data={"server": "file:///tmp/cookies", "key": "key", "password": "password"},
        )
        self.assertEqual(1, response["code"])
        self.assertIn("HTTP(S)", response["message"])

    def test_user_management_action_is_removed(self):
        response = WebAction().api_action(
            cmd="user_manager",
            data={
                "oper": "add",
                "name": "legacy-user",
                "password": "password",
                "pris": ["资源搜索", "订阅管理"],
            },
        )

        self.assertEqual(-1, response["code"])

    @patch("web.backend.user.User.get_user")
    def test_api_login_does_not_return_long_lived_api_key(self, get_user):
        user = MagicMock(id=0, username="admin")
        user.verify_password.return_value = True
        get_user.return_value = user

        response = self.client.post(
            "/api/v1/user/login",
            data={"username": "admin", "password": "safe-password"},
        )

        self.assertEqual(200, response.status_code)
        self.assertNotIn("apikey", response.json["data"])
        TokenCache.delete(response.json["data"]["token"])

    @patch('flask_login.utils._get_user')
    def test_admin_tool_index_lists_all_tools(self, mock_current_user):
        mock_current_user.return_value = MagicMock(id=0, username="admin", is_authenticated=True)
        response = self.client.get("/tools")
        self.assertEqual(200, response.status_code)
        self.assertIn('data-tool-page="tools/site-signin"', response.get_data(as_text=True))

    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_site_signin_tool_uses_tool_route_only(self, mock_get_user, mock_current_user):
        user = MagicMock(id=0, username="admin")
        user.is_authenticated = True
        mock_get_user.return_value = user
        mock_current_user.return_value = user

        routes = {rule.rule for rule in App.url_map.iter_rules()}
        self.assertIn("/tools/site-signin", routes)
        self.assertNotIn("/site_signin", routes)
        response = self.client.get("/tools/site-signin")
        self.assertEqual(200, response.status_code)
        self.assertIn("站点自动签到", response.get_data(as_text=True))

    @patch('web.actions.download.ThreadHelper')
    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_generic_service_runner_does_not_expose_site_signin_tool(
            self, mock_get_user, mock_current_user, thread_helper):
        user = MagicMock(id=0, username="admin")
        user.is_authenticated = True
        mock_get_user.return_value = user
        mock_current_user.return_value = user

        response = self.client.post(
            "/do",
            data={"cmd": "sch", "data": json.dumps({"item": "ptsignin"})},
        )

        self.assertEqual(1, response.json.get("code"))
        self.assertIn("不支持", response.json.get("msg"))
        thread_helper.return_value.start_thread.assert_not_called()

    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_admin_check_uses_api_identity_before_session(
            self, mock_get_user, mock_current_user):
        from flask import g

        session_user = MagicMock(id=0, username="session")
        session_user.is_authenticated = True
        api_user = None
        mock_current_user.return_value = session_user
        mock_get_user.side_effect = lambda username: {
            "session": session_user,
            "token": api_user,
        }.get(username)

        with App.test_request_context("/api/v1/service/run"):
            g.api_username = "token"
            self.assertFalse(request_is_admin())
            del g.api_username
            self.assertTrue(request_is_admin())

    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_upload_path_traversal_blocking(self, mock_get_user, mock_current_user):
        # Admin user
        user_mock = MagicMock(id=0, username="admin")
        user_mock.is_authenticated = True
        mock_get_user.return_value = user_mock
        mock_current_user.return_value = user_mock

        # Try directory traversal upload (which will be filtered or block path)
        import io
        data = {
            'file': (io.BytesIO(b"test"), '../../evil.py')
        }
        response = self.client.post("/upload", data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json.get("code"), 1)
        self.assertIn("不支持的文件类型", response.json.get("msg"))

    def test_unauthenticated_action_uses_json_401_contract(self):
        response = self.client.post(
            "/do",
            data={"cmd": "search", "data": "{}"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json.get("code"), 401)
        self.assertFalse(response.json.get("success"))

    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_malformed_action_json_returns_400_contract(self, mock_get_user, mock_current_user):
        user = MagicMock(id=0, username="admin")
        user.is_authenticated = True
        mock_get_user.return_value = user
        mock_current_user.return_value = user

        response = self.client.post("/do", data={"cmd": "update_config", "data": "{"})

        self.assertEqual(400, response.status_code)
        self.assertEqual(400, response.json["code"])
        self.assertFalse(response.json["success"])

    def test_security_headers_are_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertIn("frame-ancestors", response.headers.get("Content-Security-Policy", ""))

    def test_sensitive_query_parameters_are_redacted_from_urls(self):
        redacted = StringUtils.redact_url(
            "https://user:password@tracker.example:8443/download/file.torrent?passkey=secret#token"
        )
        self.assertEqual("https://tracker.example:8443/download/file.torrent", redacted)
        self.assertEqual("magnet:<redacted>", StringUtils.redact_url("magnet:?xt=urn:btih:secret"))

    @patch("web.actions.system.RequestUtils")
    def test_network_test_rejects_non_whitelisted_targets(self, request_utils):
        result = SystemActions.net_test("127.0.0.1")

        self.assertFalse(result["res"])
        self.assertIn("不支持", result["msg"])
        request_utils.assert_not_called()

    def test_allowed_file_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "media"
            root.mkdir()
            inside = root / "inside.mkv"
            outside = Path(temp_dir) / "outside.txt"
            inside.write_text("inside", encoding="utf-8")
            outside.write_text("outside", encoding="utf-8")

            self.assertEqual(
                resolve_allowed_file_path(str(inside), roots=(root.resolve(),)),
                inside.resolve(),
            )
            with self.assertRaises(ValueError):
                resolve_allowed_file_path(str(outside), roots=(root.resolve(),))
            with self.assertRaises(ValueError):
                resolve_allowed_file_path(str(root / ".." / "outside.txt"), roots=(root.resolve(),))

    def test_sqlite_backup_keeps_schema_and_clears_transient_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.db"
            destination = Path(temp_dir) / "destination.db"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE schema_version (version TEXT NOT NULL)")
                connection.execute("INSERT INTO schema_version VALUES ('1')")
                connection.execute("CREATE TABLE download_history (id INTEGER PRIMARY KEY, title TEXT)")
                connection.execute("INSERT INTO download_history(title) VALUES ('transient')")
                connection.execute("CREATE TABLE TRANSFER_HISTORY (id INTEGER PRIMARY KEY, title TEXT)")
                connection.execute("INSERT INTO TRANSFER_HISTORY(title) VALUES ('retired')")
                connection.execute(
                    "CREATE TABLE CONFIG_USERS (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
                    "password TEXT NOT NULL, pris TEXT NOT NULL)"
                )
                legacy_user = ("legacy-user", "legacy-password-hash", "search,download")
                connection.execute(
                    "INSERT INTO CONFIG_USERS(name, password, pris) VALUES (?, ?, ?)",
                    legacy_user,
                )
                connection.execute(
                    "CREATE TABLE system_dict (id INTEGER PRIMARY KEY, type TEXT, key TEXT, value TEXT)"
                )
                connection.execute(
                    'INSERT INTO system_dict(type, "key", value) VALUES (?, ?, ?)',
                    ("SystemConfig", "SpeedLimit", "retired"),
                )
                retained_setting = ("SystemConfig", "DefaultDownloader", "downloader-1")
                connection.execute(
                    'INSERT INTO system_dict(type, "key", value) VALUES (?, ?, ?)',
                    retained_setting,
                )
                connection.commit()

            create_sqlite_backup(source, destination)

            with sqlite3.connect(destination) as connection:
                self.assertEqual(connection.execute(
                    "SELECT version FROM schema_version").fetchone()[0], "1")
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM download_history").fetchone()[0], 0)
                existing_tables = {
                    str(row[0]).lower()
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                self.assertTrue(RETIRED_DATABASE_TABLES.isdisjoint(existing_tables))
                self.assertNotIn("config_users", existing_tables)
                self.assertEqual(connection.execute(
                    'SELECT COUNT(*) FROM system_dict WHERE type = ? AND "key" = ?',
                    ("SystemConfig", "SpeedLimit"),
                ).fetchone()[0], 0)
                self.assertEqual(connection.execute(
                    'SELECT type, "key", value FROM system_dict'
                ).fetchall(), [retained_setting])
                self.assertEqual(connection.execute(
                    "PRAGMA integrity_check").fetchone()[0], "ok")

            with sqlite3.connect(source) as connection:
                self.assertEqual(connection.execute(
                    "SELECT name, password, pris FROM CONFIG_USERS"
                ).fetchall(), [legacy_user])
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM download_history"
                ).fetchone()[0], 1)

    def test_sensitive_web_dtos_are_redacted(self):
        task = sanitize_brush_task({
            "id": 1,
            "name": "task",
            "cookie": "secret-cookie",
            "rss_url": "https://example.test/rss?passkey=secret",
            "ua": "secret-ua",
        })
        downloader = sanitize_downloader({
            "id": 1,
            "name": "client",
            "username": "user",
            "password": "secret-password",
        })
        self.assertNotIn("cookie", task)
        self.assertNotIn("rss_url", task)
        self.assertNotIn("ua", task)
        self.assertNotIn("password", downloader)

    def test_brush_rule_parser_and_renderer_do_not_execute_or_emit_html(self):
        parsed = parse_brush_rule("{'include': '<img src=x onerror=alert(1)>'}")
        rendered = WebAction.parse_brush_rule_string(parsed)
        self.assertEqual(parsed["include"], "<img src=x onerror=alert(1)>")
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;img", rendered)
        with self.assertRaises(ValueError):
            parse_brush_rule("__import__('os').system('id')")

    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_recommend_params_are_json_escaped(self, mock_get_user, mock_current_user):
        user_mock = MagicMock(id=0, username="admin")
        user_mock.is_authenticated = True
        mock_get_user.return_value = user_mock
        mock_current_user.return_value = user_mock
        payload = {"value": "</script><script>alert(1)</script>"}
        response = self.client.get("/recommend", query_string={"params": json.dumps(payload)})
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertNotIn("</script><script>alert(1)</script>", body)
        self.assertIn("\\u003c/script\\u003e", body)

    def test_empty_login_password_keeps_existing_hash(self):
        config = {"app": {"login_password": "[hash]existing"}}
        updated = WebAction.set_config_value(config, "app.login_password", "")
        self.assertEqual(updated["app"]["login_password"], "[hash]existing")

    def test_masked_external_api_credentials_keep_existing_values(self):
        credentials = {
            "fanart_api_key": "fanart-secret",
            "douban_api_key": "douban-key",
            "douban_api_secret": "douban-secret",
        }
        config = {"app": dict(credentials)}

        for key, expected in credentials.items():
            with self.subTest(key=key):
                updated = WebAction.set_config_value(config, f"app.{key}", "******")
                self.assertEqual(updated["app"][key], expected)


    def test_restart_targets_gunicorn_master_only(self):
        with patch("web.actions.system.os.getppid", return_value=4321), \
                patch("web.actions.system.os.getpid", return_value=1234):
            self.assertEqual(get_restart_target_pid("gunicorn/23.0.0"), 4321)
            self.assertEqual(get_restart_target_pid("Werkzeug/3.0"), 1234)
        with patch("web.actions.system.os.getppid", return_value=1), \
                patch("web.actions.system.os.getpid", return_value=1234):
            self.assertEqual(get_restart_target_pid("gunicorn/23.0.0"), 1234)

    def test_torrent_controls_report_downloader_failure(self):
        action = DownloadActions(MagicMock())
        cases = (
            ("pt_start", "start_torrents"),
            ("pt_stop", "stop_torrents"),
            ("pt_remove", "delete_torrents"),
        )
        for action_name, downloader_method in cases:
            with self.subTest(action=action_name), patch("web.actions.download.Downloader") as downloader:
                method = getattr(downloader.return_value, downloader_method)
                method.return_value = False
                self.assertEqual(getattr(action, action_name)({"id": "hash"})["retcode"], 1)
                method.return_value = True
                self.assertEqual(getattr(action, action_name)({"id": "hash"})["retcode"], 0)

    def test_stored_message_html_is_returned_as_plain_structured_data(self):
        action = SystemActions(MagicMock())
        malicious = '<img src=x onerror="alert(1)">Title<br><script>alert(2)</script>'
        with patch.object(SystemActions, "get_system_message", return_value={
            "message": [{"level": "INFO", "title": malicious, "content": malicious, "time": "now"}],
            "lst_time": "now",
        }):
            result = action.refresh_message({"lst_time": ""})
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("<script", serialized)
        self.assertNotIn("<img", serialized)
        self.assertIn("Title", result["message"][0]["title"])

    def test_message_client_secrets_are_masked_and_preserved(self):
        existing = {"token": "real-token", "chat_id": "123"}
        prepared = prepare_message_client_config(
            "telegram",
            {"token": "******", "chat_id": "123", "user_ids": "", "admin_ids": "", "webhook": 0},
            existing,
        )
        self.assertEqual(prepared["token"], "real-token")
        masked = sanitize_message_client({"config": existing, "name": "Telegram"})
        self.assertEqual(masked["config"]["token"], "******")
        self.assertEqual(masked["config"]["chat_id"], "123")
        with self.assertRaises(ValueError):
            prepare_message_client_config("unknown", {})
        with self.assertRaises(ValueError):
            prepare_message_client_config(
                "telegram",
                {"token": "token", "chat_id": "", "user_ids": "", "admin_ids": "", "webhook": 0},
            )

    def test_message_client_failed_upsert_is_not_reported_as_success(self):
        action = SystemActions(MagicMock())
        action.dbhelper.insert_message_client.return_value = False
        existing = {"config": {"token": "old", "chat_id": "123"}}
        with patch("web.actions.system.Message") as message:
            message.return_value.get_message_client_info.return_value = existing
            result = action.update_message_client({
                "cid": 7,
                "name": "Telegram",
                "type": "telegram",
                "config": json.dumps({
                    "token": "******", "chat_id": "123", "user_ids": "", "admin_ids": "", "webhook": 0,
                }),
                "switchs": [],
                "interactive": 0,
                "enabled": 1,
            })
        self.assertEqual(result.get("code"), 1)
        action.dbhelper.insert_message_client.assert_called_once()
        self.assertEqual(action.dbhelper.insert_message_client.call_args.kwargs["cid"], 7)
        message.return_value.init_config.assert_not_called()

    def test_health_endpoint_is_public_and_lightweight(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    @patch('web.backend.user.User.get_user')
    def test_api_token_accepts_raw_and_bearer_but_rejects_other_schemes(self, mock_get_user):
        user = MagicMock(id=0, username="tester")
        mock_get_user.return_value = user
        token = generate_access_token("tester")
        TokenCache.set(token, token)
        try:
            for authorization in (token, f"Bearer {token}"):
                response = self.client.post(
                    "/api/v1/user/info",
                    data={"username": "tester"},
                    headers={"Authorization": authorization},
                )
                self.assertEqual(response.status_code, 200, authorization[:12])
            response = self.client.post(
                "/api/v1/user/info",
                data={"username": "tester"},
                headers={"Authorization": f"Basic {token}"},
            )
            self.assertEqual(response.status_code, 401)
        finally:
            TokenCache.delete(token)

    @patch('flask_login.utils._get_user')
    @patch('web.backend.user.User.get_user')
    def test_oversized_upload_is_rejected_before_file_processing(self, mock_get_user, mock_current_user):
        user = MagicMock(id=0, username="admin")
        user.is_authenticated = True
        mock_get_user.return_value = user
        mock_current_user.return_value = user
        response = self.client.post(
            "/upload",
            data={"file": (io.BytesIO(b"x" * (20 * 1024 * 1024 + 1)), "large.torrent")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json.get("code"), 413)

    def test_download_torrent_rejects_path_escape_and_non_magnet_urls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir) / "temp"
            temp_root.mkdir()
            outside = Path(temp_dir) / "outside.torrent"
            outside.write_bytes(b"torrent")
            action = DownloadActions(MagicMock())
            with patch("web.actions.download.Config") as config, patch("web.actions.download.Downloader") as downloader:
                config.return_value.get_temp_path.return_value = str(temp_root)
                result = action.download_torrent({
                    "files": [{"upload": {"filename": "../outside.torrent"}}],
                    "magnets": ["http://127.0.0.1/private"],
                })
            self.assertEqual(result.get("code"), 1)
            self.assertTrue(outside.exists())
            downloader.return_value.download.assert_not_called()
        valid = "magnet:?xt=urn:btih:" + "a" * 40
        self.assertTrue(is_valid_btih_magnet(valid))
        self.assertFalse(is_valid_btih_magnet("file:///etc/passwd"))

    def test_download_link_must_match_server_saved_site(self):
        saved_site = {
            "name": "Configured",
            "signurl": "https://tracker.example:443/",
            "rssurl": "https://tracker.example/rss",
            "strict_url": "https://tracker.example/",
        }
        with patch("web.actions.validation.Sites") as sites:
            sites.return_value.get_sites.return_value = [saved_site]
            self.assertEqual(
                validate_configured_site_url("Configured", "https://tracker.example/download?id=1"),
                "https://tracker.example/download?id=1",
            )
            with self.assertRaises(ValueError):
                validate_configured_site_url("Configured", "http://127.0.0.1/admin")
            with self.assertRaises(ValueError):
                validate_configured_site_url("ClientSuppliedName", "https://tracker.example/download")

            action = DownloadActions(MagicMock())
            with patch("web.actions.download.Downloader") as downloader:
                result = action.download_link({
                    "site": "Configured",
                    "enclosure": "http://127.0.0.1/admin",
                    "title": "malicious",
                })
                self.assertNotEqual(result.get("code"), 0)
                downloader.return_value.download.assert_not_called()

    def test_external_titles_are_not_embedded_in_executable_template_contexts(self):
        payload = 'quote"\' </script><script>alert(1)</script>'
        resource = SimpleNamespace(
            enclosure="https://tracker.example/download", title=payload, description=payload,
            page_url="https://tracker.example/details", size=1, seeders=1, peers=1, grabs=1,
            uploadvolumefactor=1.0, downloadvolumefactor=1.0, pubdate="now",
            date_elapsed="now", imdbid=None,
        )
        resources_html = App.jinja_env.get_template("site/resources.html").render(
            Results=[resource], SiteId="1", Title=payload, KeyWord="", TotalCount=1,
            PageRange=range(1), CurrentPage=0, TotalPage=1,
        )

        cache_info = SimpleNamespace(id="1", type="电影", title=payload, poster_path=None)
        cache_html = App.jinja_env.get_template("rename/tmdbcache.html").render(
            TotalCount=1, Count=1, TmdbCaches=[("cache-id", cache_info, payload)], Search=payload,
            CurrentPage=1, TotalPage=1, PageRange=range(1, 2), PageNum=30,
        )

        torrent = SimpleNamespace(
            id="1", site=payload, torrent_name=payload, pageurl="https://tracker.example/details",
            enclosure="https://tracker.example/download", uploadvalue=1.0, downloadvalue=1.0,
            video_encode="", description=payload, reseffect="", size="1 MB", releasegroup="",
            seeders=1,
        )
        group = SimpleNamespace(
            group_info=SimpleNamespace(restype="", respix=""), group_total=1,
            group_torrents={"unique": SimpleNamespace(torrent_list=[torrent])},
        )
        item = SimpleNamespace(
            key="safe-key", exist=False, poster=None,
            filter=SimpleNamespace(season=[], site=[], free=[], video=[]),
            tmdbid="0", type="电影", vote="", overview="",
            torrent_dict=[(payload, {"group": group})],
        )
        search_html = App.jinja_env.get_template("search.html").render(
            Count=1, Results={payload: item}, SiteDict={}, UPCHAR="↑",
        )

        for rendered in (resources_html, cache_html, search_html):
            self.assertNotIn("</script><script>alert(1)</script>", rendered)
        self.assertNotIn("javascript:nametest", resources_html)
        self.assertNotIn("javascript:show_modify", cache_html)
        self.assertNotIn("javascript:show_download_modal", search_html)
        self.assertNotIn("javascript:$('#search_se_accordion_", search_html)

    def test_torrent_modal_ajax_data_is_rendered_as_text_nodes(self):
        root = Path(__file__).resolve().parents[1]
        cases = (
            (
                root / "web/templates/download/torrent_remove.html",
                "function show_remove_torrents_modal",
                "// 单选框事件",
                ("${torrent.name}", "${torrent.site}", "${ret.msg}"),
            ),
            (
                root / "web/templates/site/brushtask.html",
                "function show_brushtask_torrents_modal",
                "</script>",
                ("${download.torrent_name}", "${download.lst_mod_date}", "${ret.msg}"),
            ),
        )
        for template_path, start_marker, end_marker, unsafe_patterns in cases:
            with self.subTest(template=template_path.name):
                source = template_path.read_text(encoding="utf-8")
                snippet = source.split(start_marker, 1)[1].split(end_marker, 1)[0]
                self.assertIn("document.createElement", snippet)
                self.assertIn("textContent", snippet)
                self.assertIn("replaceChildren", snippet)
                self.assertNotIn("`<", snippet)
                for unsafe_pattern in unsafe_patterns:
                    self.assertNotIn(unsafe_pattern, snippet)

    def test_statistics_picture_uses_dom_text_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        template_path = root / "web/templates/site/statistics.html"
        source = template_path.read_text(encoding="utf-8")
        snippet = source.split("function gen_and_save_statistics_pic()", 1)[1].split("</script>", 1)[0]

        App.jinja_env.get_template("site/statistics.html")
        self.assertNotIn("innerHTML", snippet)
        self.assertNotIn("replaceAll('{SITE}'", snippet)
        self.assertNotIn("replaceAll('{USERNAME}'", snippet)
        self.assertIn("statistic.site ?? ''", snippet)
        self.assertIn("statistic.username ?? ''", snippet)
        self.assertGreaterEqual(snippet.count(".textContent ="), 9)
        self.assertIn('<template id="statistics_pic_table_template">', source)
        self.assertIn('<template id="statistics_pic_tr_template">', source)

    def test_basic_settings_report_save_validation_errors(self):
        template_path = Path(__file__).resolve().parents[1] / "web/templates/setting/basic.html"
        source = template_path.read_text(encoding="utf-8")
        save_handler = source.split("function save_basic_config", 1)[1].split(
            "{% if SettingSection == \"media\" %}", 1
        )[0]

        self.assertIn("ret.code !== 0", save_handler)
        self.assertIn("show_fail_modal", save_handler)

    def test_media_api_credentials_are_not_rendered(self):
        credentials = {
            "fanart_api_key": "fanart-raw-secret",
            "douban_api_key": "douban-raw-key",
            "douban_api_secret": "douban-raw-secret",
        }
        config = SimpleNamespace(
            app=SimpleNamespace(
                rmt_tmdbkey="",
                tmdb_domain="api.tmdb.org",
                rmt_match_mode="normal",
                **credentials,
            ),
            media=SimpleNamespace(category="default-category"),
            pt=SimpleNamespace(download_order="site"),
            laboratory=SimpleNamespace(tmdb_proxy="", release_groups=""),
        )
        rendered = App.jinja_env.get_template("setting/basic.html").render(
            SettingSection="media",
            SettingTitle="媒体设置",
            Config=config,
        )

        for key, secret in credentials.items():
            self.assertIn(f'id="app.{key}"', rendered)
            self.assertNotIn(secret, rendered)
        self.assertGreaterEqual(rendered.count('type="password" value="******"'), 3)

    def test_site_links_only_render_saved_http_urls(self):
        context = {
            "DownloadSettings": {},
            "ChromeOk": False,
            "OcrServerConfigured": False,
            "CookieCloudCfg": SimpleNamespace(server="", password="", key=""),
            "CookieUserInfoCfg": SimpleNamespace(username="", password="", two_step_code=""),
        }

        def render_site(signurl):
            site = SimpleNamespace(
                id=1, pri=1, name="Tracker", signurl=signurl, rssurl="", cookie="",
                signin_enable=False, login_enable=False, statistic_enable=False,
                download_setting="",
            )
            return App.jinja_env.get_template("site/site.html").render(Sites=[site], **context)

        for unsafe_url in ("javascript:alert(1)", "data:text/html,<script>alert(1)</script>"):
            with self.subTest(url=unsafe_url):
                rendered = render_site(unsafe_url)
                self.assertNotIn(f'href="{unsafe_url}', rendered)
                self.assertNotIn("target=\"_blank\"", rendered)

        safe_url = "https://tracker.example/path"
        rendered = render_site(safe_url)
        self.assertIn(f'href="{safe_url}"', rendered)
        self.assertIn('target="_blank" rel="noopener noreferrer"', rendered)

        self.assertEqual(
            "https://tracker.example/path",
            validate_site_config_url("https://tracker.example/path"),
        )
        for unsafe_url in ("javascript:alert(1)", "data:text/plain,test"):
            with self.assertRaises(ValueError):
                validate_site_config_url(unsafe_url)

    def test_site_page_never_renders_saved_login_secrets(self):
        template = App.jinja_env.get_template("site/site.html")
        common_context = {
            "Sites": [],
            "DownloadSettings": {},
            "ChromeOk": True,
            "OcrServerConfigured": True,
            "CookieCloudCfg": SimpleNamespace(
                server="https://cookiecloud.example",
                key="cookie-key-secret",
                password="cookie-password-secret",
            ),
            "CookieUserInfoCfg": SimpleNamespace(
                username="saved-user",
                password="site-password-secret",
                two_step_code="two-step-secret",
            ),
        }

        admin_html = template.render(**common_context)

        for secret in ("cookie-key-secret", "cookie-password-secret", "site-password-secret", "two-step-secret"):
            self.assertNotIn(secret, admin_html)
        self.assertIn('id="modal-cookiecloud"', admin_html)
