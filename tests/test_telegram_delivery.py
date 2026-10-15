import json
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

import requests

from app.message.client.telegram import Telegram


class TelegramDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.client = Telegram.__new__(Telegram)
        self.client._telegram_token = "123456:private-bot-token"
        self.client._telegram_chat_id = "default-chat"
        self.client._webhook_secret = "webhook-secret"
        request_patch = patch("app.message.client.telegram.RequestUtils")
        config_patch = patch("app.message.client.telegram.Config")
        self.request = request_patch.start().return_value
        self.config = config_patch.start().return_value
        self.config.get_proxies.return_value = None
        self.addCleanup(request_patch.stop)
        self.addCleanup(config_patch.stop)

    @staticmethod
    def response(status=200, description=None, data=None):
        response = requests.Response()
        response.status_code = status
        if data is None:
            data = {"ok": status == 200}
            if description is not None:
                data.update(error_code=status, description=description)
        response._content = json.dumps(data).encode()
        return response

    def request_values(self, index=0):
        url = urlsplit(self.request.get_res.call_args_list[index].args[0])
        return url.path.rsplit("/", 1)[-1], parse_qs(url.query, keep_blank_values=True)

    def test_titles_multiline_body_and_links_are_escaped(self):
        self.request.get_res.return_value = self.response()

        result = self.client.send_msg(
            'A <film> & *stars*\nB <tag>',
            text='C & [brackets] _text_ `code`',
            image="https://example.com/image.jpg",
            url='https://example.com/?a="quoted"&b=2',
        )

        self.assertEqual((True, ""), result)
        method, values = self.request_values()
        self.assertEqual("sendPhoto", method)
        self.assertEqual(["HTML"], values["parse_mode"])
        self.assertEqual(
            '<b>A &lt;film&gt; &amp; *stars*</b>\nB &lt;tag&gt;\n'
            'C &amp; [brackets] _text_ `code`\n\n'
            '<a href="https://example.com/?a=&quot;quoted&quot;&amp;b=2">查看详情</a>',
            values["caption"][0],
        )
        self.assertEqual(1, self.request.get_res.call_count)

    def test_text_without_title_has_no_empty_formatting_entity(self):
        self.request.get_res.return_value = self.response()

        self.assertEqual((True, ""), self.client.send_msg(None, text="A < B & C"))
        _, values = self.request_values()
        self.assertEqual(["A &lt; B &amp; C"], values["text"])

    def test_http_400_api_description_is_preserved(self):
        self.request.get_res.return_value = self.response(400, "Bad Request: chat not found")

        result = self.client.send_msg("test")

        self.assertEqual((False, "Telegram 400: Bad Request: chat not found"), result)
        self.assertEqual(1, self.request.get_res.call_count)

    def test_parse_rejection_falls_back_once_with_unescaped_original(self):
        self.request.get_res.side_effect = [
            self.response(400, "Bad Request: can't parse entities"),
            self.response(),
        ]

        result = self.client.send_msg("A < B *title*", "C & [body]", user_id="target-chat")

        self.assertEqual((True, ""), result)
        self.assertEqual(2, self.request.get_res.call_count)
        method, values = self.request_values(1)
        self.assertEqual("sendMessage", method)
        self.assertEqual({"chat_id": ["target-chat"], "text": ["A < B *title*\nC & [body]"]}, values)

    def test_photo_rejection_falls_back_to_text_without_fetching_photo(self):
        self.request.get_res.side_effect = [
            self.response(400, "Bad Request: failed to get HTTP URL content"),
            self.response(),
        ]

        result = self.client.send_msg(
            "Title", "Body", image="http://169.254.169.254/private.jpg",
            url="https://example.com/detail?a=1&b=2",
        )

        self.assertEqual((True, ""), result)
        self.assertEqual(2, self.request.get_res.call_count)
        method, values = self.request_values(1)
        self.assertEqual("sendMessage", method)
        self.assertEqual(["Title\nBody\n\n查看详情：https://example.com/detail?a=1&b=2"], values["text"])
        self.assertNotIn("parse_mode", values)
        self.assertNotIn("photo", values)
        for call in self.request.get_res.call_args_list:
            self.assertEqual("api.telegram.org", urlsplit(call.args[0]).hostname)

    def test_caption_limit_can_fall_back_to_text(self):
        self.request.get_res.side_effect = [
            self.response(400, "Bad Request: message caption is too long"),
            self.response(),
        ]
        body = "a" * 1100

        self.assertEqual((True, ""), self.client.send_msg("Title", body, image="https://example.com/photo"))
        self.assertEqual(["Title\n" + body], self.request_values(1)[1]["text"])

    def test_list_escapes_all_fields_and_keeps_raw_plain_fallback(self):
        self.request.get_res.side_effect = [
            self.response(400, "Bad Request: can't parse entities"),
            self.response(),
        ]
        media = MagicMock()
        media.get_message_image.return_value = "https://example.com/photo"
        media.get_title_string.return_value = "Film <tag> & [1]"
        media.get_detail_url.return_value = 'https://example.com/?a="b"&x=1'
        media.get_type_string.return_value = "Movie <type>"
        media.get_vote_string.return_value = "8 & 9"

        result = self.client.send_list_msg([media], title="List <title>")

        self.assertEqual((True, ""), result)
        _, values = self.request_values()
        self.assertEqual(
            '<b>List &lt;title&gt;</b>\n1. '
            '<a href="https://example.com/?a=&quot;b&quot;&amp;x=1">Film &lt;tag&gt; &amp; [1]</a>'
            '\nMovie &lt;type&gt;，8 &amp; 9', values["caption"][0],
        )
        _, plain_values = self.request_values(1)
        self.assertEqual(
            'List <title>\n1. Film <tag> & [1]\nhttps://example.com/?a="b"&x=1\nMovie <type>，8 & 9',
            plain_values["text"][0],
        )
        self.assertNotIn("parse_mode", plain_values)

    def test_failed_fallback_keeps_both_errors_without_third_attempt(self):
        self.request.get_res.side_effect = [
            self.response(400, "Bad Request: can't parse entities"),
            self.response(400, "Bad Request: message is too long"),
        ]

        flag, message = self.client.send_msg("Title", "Body")

        self.assertFalse(flag)
        self.assertIn("can't parse entities", message)
        self.assertIn("message is too long", message)
        self.assertEqual(2, self.request.get_res.call_count)

    def test_unconfirmed_or_unrelated_failures_are_never_retried(self):
        for response in (
            None,
            self.response(401, "Unauthorized"),
            self.response(403, "Forbidden: bot was blocked by the user"),
            self.response(429, "Too Many Requests: retry after 3"),
            self.response(500, "Internal Server Error"),
            self.response(400, "Bad Request: chat not found"),
            self.response(400, "Bad Request: not enough rights to send photos to the chat"),
            self.response(503, data={"ok": False, "error_code": 400, "description": "can't parse entities"}),
        ):
            with self.subTest(response=response):
                self.request.reset_mock()
                self.request.get_res.return_value = response

                flag, _ = self.client.send_msg("Title", "Body", image="https://example.com/photo")

                self.assertFalse(flag)
                self.assertEqual(1, self.request.get_res.call_count)

    def test_non_json_response_is_reported_without_echoing_body_or_retrying(self):
        response = self.response(502)
        response._content = b"<html>private upstream response</html>"
        self.request.get_res.return_value = response

        flag, message = self.client.send_msg("Title")

        self.assertFalse(flag)
        self.assertIn("502", message)
        self.assertNotIn("private upstream", message)
        self.assertEqual(1, self.request.get_res.call_count)

    def test_malformed_json_response_is_not_retried(self):
        self.request.get_res.return_value = self.response(data=["invalid"])

        self.assertEqual((False, "Telegram 返回信息格式错误"), self.client.send_msg("Title"))
        self.assertEqual(1, self.request.get_res.call_count)

    def test_network_exception_redacts_sensitive_urls_and_does_not_retry(self):
        self.request.get_res.side_effect = requests.Timeout(
            "Timeout https://api.telegram.org/bot123456:private-bot-token/sendMessage?text=private-content"
        )

        with patch("app.message.client.telegram.log.error") as error_log:
            flag, message = self.client.send_msg("Title")

        self.assertFalse(flag)
        self.assertIn("Timeout", message)
        for secret in ("private-bot-token", "private-content"):
            self.assertNotIn(secret, message)
            self.assertNotIn(secret, str(error_log.call_args))
        self.assertEqual(1, self.request.get_res.call_count)

    def test_api_error_redacts_bot_token_and_webhook_secret(self):
        self.request.get_res.return_value = self.response(
            400, "Bad Request: 123456:private-bot-token webhook-secret 123456%3Aprivate-bot-token"
        )

        flag, message = self.client.send_msg("Title")

        self.assertFalse(flag)
        self.assertIn("Bad Request", message)
        self.assertNotIn("private-bot-token", message)
        self.assertNotIn("webhook-secret", message)


if __name__ == "__main__":
    unittest.main()
