import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app.utils import TokenCache
from web.backend.user import User
from web.main import App
from web.security import generate_access_token


class AdminAuthenticationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash("admin-password")

    def setUp(self):
        self.config = {
            "login_user": "owner",
            "login_password": f"[hash]{self.password_hash}",
        }
        config_patch = patch("web.backend.user.Config")
        config_patch.start().return_value.get_config.return_value = self.config
        self.addCleanup(config_patch.stop)
        self.client = App.test_client()

    def test_only_configured_admin_can_be_resolved(self):
        user = User()
        self.assertIs(user, user.get_user("owner"))
        self.assertEqual("0", user.get_id())
        for user_id in (0, "0"):
            self.assertIs(user, user.get(user_id))
        for user_id in (1, "1", None, "", "owner", "invalid"):
            self.assertIsNone(user.get(user_id))
        for username in ("admin", "legacy-user", "", None):
            self.assertIsNone(user.get_user(username))

    def test_password_hash_is_required_and_checked(self):
        user = User()
        self.assertTrue(user.verify_password("admin-password"))
        for password in ("wrong", "", None):
            self.assertFalse(user.verify_password(password))
        for configured_password in (None, "", "[hash]", "plaintext"):
            self.config["login_password"] = configured_password
            self.assertIsNone(User().get("0"))
            self.assertIsNone(User().get_user("owner"))

    @patch("web.main.get_login_wallpaper", return_value="")
    @patch("web.main.Indexer")
    @patch("web.main.Sites")
    @patch("web.main.render_template", return_value="page")
    def test_browser_login_and_logout(self, render, sites, indexer, wallpaper):
        response = self.client.post("/", data={
            "username": "owner", "password": "admin-password", "remember": "on",
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual("navigation.html", render.call_args.args[0])
        self.assertEqual("owner", render.call_args.kwargs["UserName"])
        with self.client.session_transaction() as session:
            self.assertEqual("0", session["_user_id"])
            self.assertTrue(session.permanent)
        self.assertEqual(200, self.client.get("/tools").status_code)
        self.assertEqual(200, self.client.post("/do", data={"cmd": "logout"}).status_code)
        self.assertEqual(401, self.client.post("/do", data={"cmd": "logout"}).status_code)

    @patch("web.main.get_login_wallpaper", return_value="")
    @patch("web.main.render_template", return_value="login")
    def test_browser_rejects_legacy_username_wrong_or_missing_password(self, render, wallpaper):
        for credentials in (
            {"username": "legacy-user", "password": "admin-password"},
            {"username": "owner", "password": "wrong"},
            {"username": "owner"},
        ):
            with self.subTest(credentials=list(credentials)):
                response = self.client.post("/", data=credentials)
                self.assertEqual(200, response.status_code)
                self.assertEqual("login.html", render.call_args.args[0])
                self.assertEqual("用户名或密码错误", render.call_args.kwargs["err_msg"])
                with self.client.session_transaction() as session:
                    self.assertNotIn("_user_id", session)

    def test_api_login_and_token_identity(self):
        response = self.client.post("/api/v1/user/login", data={
            "username": "owner", "password": "admin-password",
        })
        self.assertEqual(200, response.status_code)
        token = response.json["data"]["token"]
        self.addCleanup(TokenCache.delete, token)
        identity = {"userid": 0, "username": "owner"}
        self.assertEqual(identity, response.json["data"]["userinfo"])
        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.post("/api/v1/user/info", headers=headers)
        self.assertEqual(identity, response.json["data"])
        self.config["login_user"] = "new-owner"
        self.assertEqual(401, self.client.post("/api/v1/user/info", headers=headers).status_code)

    def test_api_rejects_legacy_login_and_cached_token(self):
        for username, password in (("legacy-user", "admin-password"), ("owner", "wrong")):
            response = self.client.post("/api/v1/user/login", data={
                "username": username, "password": password,
            })
            self.assertEqual(401, response.status_code)
        token = generate_access_token("legacy-user")
        TokenCache.set(token, token)
        self.addCleanup(TokenCache.delete, token)
        response = self.client.post("/api/v1/user/info", headers={"Authorization": token})
        self.assertEqual(401, response.status_code)

    def test_all_private_api_routes_reject_anonymous_requests(self):
        public_paths = {"/api/v1/", "/api/v1/swagger.json", "/api/v1/user/login"}
        for rule in App.url_map.iter_rules():
            if not rule.rule.startswith("/api/v1/") or rule.rule in public_paths:
                continue
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                with self.subTest(path=rule.rule, method=method):
                    response = self.client.open(rule.rule, method=method)
                    self.assertEqual(401, response.status_code)


if __name__ == "__main__":
    unittest.main()
