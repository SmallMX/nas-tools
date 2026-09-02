import os
import unittest
from unittest.mock import patch

from app.media.tmdbv3api.tmdb import TMDb
from app.media.media import Media
from app.helper.ocr_helper import OcrHelper
from app.helper.cookiecloud_helper import CookieCloudHelper
from app.utils.http_utils import RequestUtils


class HttpSecurityTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(TMDb.TMDB_PROXIES, None)
        TMDb.cached_request.cache_clear()

    def test_cookie_parser_preserves_equals_in_value(self):
        self.assertEqual(
            {"session": "abc==", "name": "demo"},
            RequestUtils.cookie_parse("session=abc==; name=demo"),
        )

    @patch("app.utils.http_utils.requests.get")
    def test_tls_verification_is_enabled_by_default(self, request_get):
        RequestUtils(headers={"User-Agent": "test"}).get_res("https://example.com")

        self.assertTrue(request_get.call_args.kwargs["verify"])

    @patch("app.utils.http_utils.requests.get")
    def test_tls_verification_can_be_explicitly_overridden(self, request_get):
        RequestUtils(headers={"User-Agent": "test"}, verify=False).get_res("https://example.com")

        self.assertFalse(request_get.call_args.kwargs["verify"])

    @patch("app.utils.http_utils.requests.get")
    def test_streaming_response_is_forwarded_to_requests(self, request_get):
        RequestUtils(headers={"User-Agent": "test"}).get_res(
            "https://example.com/file.torrent",
            stream=True,
        )

        self.assertTrue(request_get.call_args.kwargs["stream"])

    @patch("app.media.tmdbv3api.tmdb.requests.request")
    def test_tmdb_proxy_is_json_parsed_without_eval(self, request):
        tmdb = TMDb()
        tmdb.proxies = {"https": "http://127.0.0.1:7890", "other": "ignored"}

        TMDb.cached_request("GET", "https://example.com", None, tmdb.proxies)

        self.assertEqual(
            {"https": "http://127.0.0.1:7890"},
            request.call_args.kwargs["proxies"],
        )
        self.assertTrue(request.call_args.kwargs["verify"])

    def test_empty_tmdb_proxy_uses_the_configured_domain(self):
        app = {"tmdb_domain": "api.tmdb.org"}

        self.assertEqual("api.tmdb.org", Media._get_tmdb_domain(app, {"tmdb_proxy": ""}))

    def test_explicit_tmdb_proxy_address_is_normalized(self):
        self.assertEqual(
            "https://tmdb-proxy.example.com",
            Media._get_tmdb_domain(
                {"tmdb_domain": "api.tmdb.org"},
                {"tmdb_proxy": " https://tmdb-proxy.example.com/ "},
            ),
        )

    @patch("app.helper.ocr_helper.RequestUtils")
    @patch("app.helper.ocr_helper.Config")
    def test_ocr_does_not_request_without_an_explicit_server(self, config, request_utils):
        config.return_value.get_config.return_value = {"ocr_server": ""}

        result = OcrHelper().get_captcha_text(image_b64="encoded-image")

        self.assertEqual("", result)
        request_utils.return_value.post_res.assert_not_called()

    @patch("app.helper.ocr_helper.RequestUtils")
    @patch("app.helper.ocr_helper.Config")
    def test_ocr_uses_the_explicit_server(self, config, request_utils):
        config.return_value.get_config.return_value = {
            "ocr_server": " https://ocr.example.com/ "
        }
        request_utils.return_value.post_res.return_value.json.return_value = {
            "result": "1234"
        }

        result = OcrHelper().get_captcha_text(image_b64="encoded-image")

        self.assertEqual("1234", result)
        request_utils.return_value.post_res.assert_called_once_with(
            url="https://ocr.example.com/captcha/base64",
            json={"base64_img": "encoded-image"},
        )

    @patch("app.helper.cookiecloud_helper.RequestUtils")
    def test_cookiecloud_does_not_request_without_explicit_parameters(self, request_utils):
        contents, message = CookieCloudHelper(
            server="", key="", password=""
        ).download_data()

        self.assertEqual({}, contents)
        self.assertEqual("CookieCloud参数不正确", message)
        request_utils.return_value.post_res.assert_not_called()


if __name__ == "__main__":
    unittest.main()
