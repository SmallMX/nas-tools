import unittest
from threading import Event
from unittest.mock import MagicMock, patch

from app.helper.security_helper import SecurityHelper
from app.message.client.telegram import TELEGRAM_LOCAL_CALLBACK_URL, Telegram


class TelegramSecurityTest(unittest.TestCase):
    def test_local_polling_callback_uses_fixed_internal_port(self):
        self.assertEqual("http://127.0.0.1:3000/telegram", TELEGRAM_LOCAL_CALLBACK_URL)

    def test_stop_service_wakes_and_clears_polling_event(self):
        client = Telegram.__new__(Telegram)
        event = Event()
        client._enabled = True
        client._message_proxy_event = event

        client.stop_service()
        client.stop_service()

        self.assertFalse(client._enabled)
        self.assertTrue(event.is_set())
        self.assertIsNone(client._message_proxy_event)

    def test_failed_photo_url_is_not_fetched_by_server(self):
        client = Telegram.__new__(Telegram)
        client._telegram_token = "token"
        response = MagicMock()
        response.json.return_value = {"ok": False, "description": "photo rejected"}
        request = MagicMock()
        request.get_res.return_value = response
        config = MagicMock()
        config.get_proxies.return_value = None

        with patch("app.message.client.telegram.Config", return_value=config), \
                patch("app.message.client.telegram.RequestUtils", return_value=request), \
                patch("app.message.client.telegram.requests.post") as post_request:
            result = client._Telegram__send_request(
                chat_id="1",
                image="http://169.254.169.254/latest/meta-data",
                caption="test",
            )

        self.assertEqual((False, "photo rejected"), result)
        self.assertEqual(1, request.get_res.call_count)
        post_request.assert_not_called()

    def test_ip_allowlist_fails_closed_when_family_is_missing(self):
        self.assertFalse(SecurityHelper.allow_access({}, "127.0.0.1"))
        self.assertFalse(
            SecurityHelper.allow_access({"ipv6": "::1/128"}, "127.0.0.1")
        )
        self.assertTrue(
            SecurityHelper.allow_access({"ipv4": "127.0.0.1/32"}, "127.0.0.1")
        )

    def test_regular_users_are_not_added_to_admin_list(self):
        client = Telegram.__new__(Telegram)
        client._client_config = {
            "admin_ids": "1001",
            "user_ids": "2001,2002",
            "interactive": False,
        }
        config = MagicMock()
        config.get_config.return_value = {"telegram_webhook_secret": "secret"}

        with patch("app.message.client.telegram.Config", return_value=config):
            client.init_config()

        self.assertEqual(["1001"], client.get_admin())
        self.assertEqual(["1001", "2001", "2002"], client.get_users())

    def test_webhook_registration_retries_after_secret_is_configured(self):
        config = MagicMock()
        config.get_domain.return_value = "https://nastool.example"
        config.get_config.side_effect = [
            {"telegram_webhook_secret": ""},
            {"telegram_webhook_secret": "secret"},
        ]
        config.get_proxies.return_value = None
        response = MagicMock()
        response.json.return_value = {"ok": True}
        request = MagicMock()
        request.get_res.return_value = response
        client_config = {
            "token": "token",
            "chat_id": "chat",
            "webhook": 1,
            "interactive": False,
        }

        with patch("app.message.client.telegram.Config", return_value=config), \
                patch("app.message.client.telegram.RequestUtils", return_value=request), \
                patch.object(Telegram, "_Telegram__get_bot_webhook", return_value=3), \
                patch("app.message.client.telegram.log.error") as error_log:
            client = Telegram(client_config)
            request.get_res.assert_not_called()

            client.init_config()

        self.assertEqual(1, request.get_res.call_count)
        self.assertIn("secret_token=secret", request.get_res.call_args.args[0])
        error_log.assert_called_once_with(
            "【Telegram】Webhook 密钥未初始化，拒绝注册不安全的 Webhook"
        )

    def test_webhook_registration_retries_after_telegram_failure(self):
        config = MagicMock()
        config.get_domain.return_value = "https://nastool.example"
        config.get_config.return_value = {"telegram_webhook_secret": "secret"}
        config.get_proxies.return_value = None
        failed_response = MagicMock()
        failed_response.json.return_value = {
            "ok": False,
            "description": "temporary failure",
        }
        successful_response = MagicMock()
        successful_response.json.return_value = {"ok": True}
        request = MagicMock()
        request.get_res.side_effect = [failed_response, successful_response]
        client_config = {
            "token": "token",
            "chat_id": "chat",
            "webhook": 1,
            "interactive": False,
        }

        with patch("app.message.client.telegram.Config", return_value=config), \
                patch("app.message.client.telegram.RequestUtils", return_value=request), \
                patch.object(Telegram, "_Telegram__get_bot_webhook", return_value=3), \
                patch("app.message.client.telegram.log.error") as error_log, \
                patch("app.message.client.telegram.log.info") as info_log:
            client = Telegram(client_config)
            client.init_config()

        self.assertEqual(2, request.get_res.call_count)
        error_log.assert_called_once_with(
            "【Telegram】Webhook 设置失败：temporary failure"
        )
        info_log.assert_called_once_with(
            "【Telegram】Webhook 设置成功，地址为：https://nastool.example/telegram"
        )


if __name__ == "__main__":
    unittest.main()
