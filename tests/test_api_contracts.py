import json
import unittest
from unittest.mock import MagicMock, patch

from app.utils import TokenCache
from web.main import App
from web.security import generate_access_token


class ApiContractTest(unittest.TestCase):
    def setUp(self):
        App.config["TESTING"] = True
        self.client = App.test_client()
        self.token = generate_access_token("admin")
        TokenCache.set(self.token, self.token)
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.admin = MagicMock(id=0, username="admin", pris="系统设置")

    def tearDown(self):
        TokenCache.delete(self.token)

    def test_swagger_declares_json_encoded_form_fields_as_form_data(self):
        response = self.client.get("/api/v1/swagger.json")

        self.assertEqual(200, response.status_code)
        spec = response.get_json()
        expected_fields = {
            "/config/update": "items",
            "/message/client/update": "switchs",
        }
        for path, field_name in expected_fields.items():
            with self.subTest(path=path):
                parameters = spec["paths"][path]["post"]["parameters"]
                parameter = next(item for item in parameters if item["name"] == field_name)
                self.assertEqual("formData", parameter["in"])
                self.assertTrue(parameter["required"])

    @patch("web.apiv1.WebAction.api_action")
    @patch("web.backend.user.User.get_user")
    def test_config_update_accepts_json_object_in_form(self, get_user, api_action):
        get_user.return_value = self.admin
        api_action.return_value = {"code": 0, "success": True}

        response = self.client.post(
            "/api/v1/config/update",
            data={"items": json.dumps({"pt.site_search_concurrency": 4})},
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"pt.site_search_concurrency": 4},
            api_action.call_args.kwargs["data"],
        )

    @patch("web.apiv1.WebAction.api_action")
    @patch("web.backend.user.User.get_user")
    def test_message_update_preserves_switch_list(self, get_user, api_action):
        get_user.return_value = self.admin
        api_action.return_value = {"code": 0, "success": True}

        response = self.client.post(
            "/api/v1/message/client/update",
            data={
                "name": "Telegram",
                "type": "telegram",
                "config": "{}",
                "switchs": json.dumps(["download_start"]),
                "interactive": 0,
                "enabled": 1,
            },
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            ["download_start"],
            api_action.call_args.kwargs["data"]["switchs"],
        )

    @patch("web.apiv1.WebAction.api_action")
    @patch("web.backend.user.User.get_user")
    def test_message_status_includes_checked_and_channel_type(self, get_user, api_action):
        get_user.return_value = self.admin
        api_action.return_value = {"code": 0, "success": True}

        response = self.client.post(
            "/api/v1/message/client/status",
            data={"flag": "enable", "cid": 1, "type": "telegram", "checked": "true"},
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code)
        submitted = api_action.call_args.kwargs["data"]
        self.assertIs(True, submitted["checked"])
        self.assertEqual("telegram", submitted["type"])

    @patch("web.apiv1.WebAction.api_action")
    @patch("web.backend.user.User.get_user")
    def test_recommend_contract_keeps_type_and_subtype_separate(self, get_user, api_action):
        get_user.return_value = self.admin
        api_action.return_value = {"code": 0, "success": True}

        response = self.client.post(
            "/api/v1/recommend/list",
            data={"type": "MOV", "subtype": "hm", "page": 2},
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code)
        submitted = api_action.call_args.kwargs["data"]
        self.assertEqual("MOV", submitted["type"])
        self.assertEqual("hm", submitted["subtype"])
        self.assertEqual(2, submitted["page"])


if __name__ == "__main__":
    unittest.main()
