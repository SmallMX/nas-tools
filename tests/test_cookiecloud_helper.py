import copy
import json
import unittest
from unittest.mock import Mock, patch

from requests import Response

from app.helper.cookiecloud_helper import CookieCloudHelper


class CookieCloudHelperTest(unittest.TestCase):
    # 固定向量由OpenSSL生成，避免用待测解密实现反向生成测试数据。
    LEGACY_ENCRYPTED = (
        "U2FsdGVkX18BAgMEBQYHCCo3ZGrNIpbUS8YKXdyR47wxGzXbjdTj7k9zIYFNJygj"
        "ccDowK8x1MI1IA6hEPSbEtobA3K9YMivHjiQec8IJcxtu/KZkiArcBo1Kqg/ms+CYWd7"
        "p+l4J6m3VDWkVqVQhzQY6qK1mbJWozT40wlkjvv1Jyc1WhMhPWtWPkXL3ibO+uIz"
        "oxLc2QT4Ircae0TqecT0EJzCrSI1Y52VCwaxZNLF9DPsx9SVYAXsGNr7bhvQ"
    )
    FIXED_ENCRYPTED = (
        "F2DpGy/dsukJSuMZqI/P5frwKpipLsmOwSfh62UdVsYvDwF8ornmyPcOTNjN4sru"
        "pLvmt5C+2d87JhqC37zfnrlX7g73zLmzKdbdMqAXeP00p4yRm8eCeezMqJbnP7NA"
        "jLUfyp4BsLtebh0iu+Fiw6ECzGcYpCQNemKYLLTtqiS1iDtW/KhEbTiXeTeS8U9y"
        "Ck9LB2CvonbFCibgTwYKkcFyc7ltVWvgxrNd/vMd5nI="
    )
    COOKIES = {"tracker.example": [
        {"domain": ".tracker.example", "name": "session", "value": "fixture=="},
    ]}

    def setUp(self):
        patcher = patch("app.helper.cookiecloud_helper.RequestUtils")
        self.addCleanup(patcher.stop)
        self.request = patcher.start().return_value
        self.helper = CookieCloudHelper("https://cookiecloud.example/api/", "test-key", "test-password")

    def _response(self, payload, status=200):
        response = Response()
        response.status_code = status
        response._content = json.dumps(payload).encode("utf-8")
        response._content_consumed = True
        response.close = Mock()
        self.request.get_res.return_value = response
        return response

    def test_download_decrypts_cryptojs_legacy_without_sending_password(self):
        for crypto_type in (None, "legacy"):
            with self.subTest(crypto_type=crypto_type):
                payload = {"encrypted": self.LEGACY_ENCRYPTED}
                if crypto_type is not None:
                    payload["crypto_type"] = crypto_type
                response = self._response(payload)

                self.assertEqual((self.COOKIES, ""), self.helper.download_data())
                self.request.get_res.assert_called_with(url="https://cookiecloud.example/api/get/test-key")
                self.request.post_res.assert_not_called()
                response.close.assert_called_once_with()

    def test_download_decrypts_fixed_iv_aes_format(self):
        self._response({"encrypted": self.FIXED_ENCRYPTED, "crypto_type": "aes-128-cbc-fixed"})

        self.assertEqual((self.COOKIES, ""), self.helper.download_data())

    def test_plaintext_wrapped_and_direct_cookie_maps_remain_supported(self):
        for payload in (self.COOKIES, {"cookie_data": self.COOKIES, "local_storage_data": {"ignored": []}}):
            with self.subTest(payload=payload):
                original = copy.deepcopy(payload)
                self._response(payload)

                self.assertEqual((self.COOKIES, ""), self.helper.download_data())
                self.assertEqual(original, payload)

    def test_empty_cookie_data_does_not_return_local_storage_as_cookies(self):
        for payload in ({}, {"cookie_data": {}, "local_storage_data": {"tracker.example": []}}):
            with self.subTest(payload=payload):
                self._response(payload)

                cookies, error = self.helper.download_data()

                self.assertEqual({}, cookies)
                self.assertIn("未从CookieCloud获取到Cookie数据", error)

    def test_http_errors_preserve_status_for_falsey_response(self):
        for status in (401, 404, 500):
            with self.subTest(status=status):
                response = self._response({"error": "secret-response"}, status=status)
                self.assertFalse(response)

                cookies, error = self.helper.download_data()

                self.assertEqual({}, cookies)
                self.assertIn(str(status), error)
                self.assertNotIn("secret-response", error)
                response.close.assert_called_once_with()

    def test_network_failure_returns_an_actionable_error(self):
        self.request.get_res.return_value = None

        cookies, error = self.helper.download_data()

        self.assertEqual({}, cookies)
        self.assertIn("请求失败", error)

    def test_non_json_response_is_closed_without_exposing_response_content(self):
        response = self._response({})
        response._content = b"<html>secret-response</html>"

        cookies, error = self.helper.download_data()

        self.assertEqual({}, cookies)
        self.assertIn("JSON", error)
        self.assertNotIn("secret-response", error)
        response.close.assert_called_once_with()

    def test_invalid_cookie_payload_is_rejected(self):
        for payload in (None, [], "secret-response", {"error": "secret-response"},
                        {"cookie_data": None}, {"cookie_data": []},
                        {"cookie_data": {"tracker.example": "session=secret"}},
                        {"cookie_data": {"tracker.example": [None]}}):
            with self.subTest(payload=payload):
                self._response(payload)

                cookies, error = self.helper.download_data()

                self.assertEqual({}, cookies)
                self.assertIn("格式不正确", error)
                self.assertNotIn("secret", error)

    def test_invalid_encrypted_payloads_fail_safely(self):
        for encrypted in (None, {}, "", "not-base64!", "U2FsdGVkX18=", self.LEGACY_ENCRYPTED[:-4]):
            with self.subTest(encrypted=encrypted):
                self._response({"encrypted": encrypted})

                cookies, error = self.helper.download_data()

                self.assertEqual({}, cookies)
                self.assertIn("解密失败", error)

    def test_wrong_password_fails_without_exposing_secrets(self):
        self._response({"encrypted": self.LEGACY_ENCRYPTED})
        helper = CookieCloudHelper("https://cookiecloud.example", "test-key", "private-password")

        cookies, error = helper.download_data()

        self.assertEqual({}, cookies)
        self.assertIn("解密失败", error)
        self.assertNotIn("private-password", error)
        self.assertNotIn("test-key", error)

    def test_unknown_crypto_algorithm_is_not_silently_treated_as_legacy(self):
        self._response({"encrypted": self.LEGACY_ENCRYPTED, "crypto_type": "future-format"})

        self.assertEqual(({}, "CookieCloud加密算法不受支持"), self.helper.download_data())

    def test_malformed_decrypted_payload_is_rejected(self):
        self._response({"encrypted": self.LEGACY_ENCRYPTED})
        with patch.object(self.helper, "_decrypt_data", return_value=["secret"]):
            cookies, error = self.helper.download_data()

        self.assertEqual({}, cookies)
        self.assertIn("格式不正确", error)

    def test_missing_configuration_does_not_make_requests(self):
        for params in ((None, "key", "password"), (" ", "key", "password"),
                       ("https://cookiecloud.example", " ", "password"),
                       ("https://cookiecloud.example", "key", None)):
            with self.subTest(params=params):
                self.assertEqual(({}, "CookieCloud参数不正确"), CookieCloudHelper(*params).download_data())

        self.request.get_res.assert_not_called()
        self.request.post_res.assert_not_called()

    def test_server_path_and_key_are_kept_in_their_respective_url_components(self):
        self._response({"cookie_data": self.COOKIES})
        helper = CookieCloudHelper(" cookiecloud.example/api/// ", " test/key?x=1 ", "test-password")

        self.assertEqual((self.COOKIES, ""), helper.download_data())
        self.request.get_res.assert_called_once_with(
            url="http://cookiecloud.example/api/get/test%2Fkey%3Fx%3D1",
        )
