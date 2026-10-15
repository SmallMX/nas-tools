import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from bencoder import bencode

from app.utils.torrent import Torrent


class TorrentRetryTest(unittest.TestCase):
    CONTENT = bencode({b"info": {b"length": 10, b"name": b"Show.E01.mkv"}})

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="torrent-retry-")
        self.addCleanup(directory.cleanup)
        self.torrent = Torrent.__new__(Torrent)
        self.torrent._torrent_temp_path = directory.name
        patcher = patch("app.utils.torrent.RequestUtils")
        self.request = patcher.start()
        self.addCleanup(patcher.stop)
        sleep_patcher = patch("app.utils.torrent.time.sleep")
        self.sleep = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    @classmethod
    def response(cls, status=200, content=None, headers=None):
        response = Mock(spec=requests.Response)
        response.status_code = status
        response.headers = headers or {}
        response.iter_content.return_value = [cls.CONTENT if content is None else content]
        return response

    def download(self, url="https://tracker.example/download?id=1", **kwargs):
        return self.torrent.save_torrent_file(url, **kwargs)

    def test_transient_responses_retry_then_save_valid_content(self):
        for first in (None, self.response(503), self.response(content=b"")):
            with self.subTest(response=first):
                self.request.reset_mock()
                self.sleep.reset_mock()
                success = self.response()
                self.request.return_value.get_res.side_effect = [first, success]

                path, content, error = self.download()

                self.assertEqual("", error)
                self.assertEqual(self.CONTENT, Path(path).read_bytes())
                self.assertEqual(self.CONTENT, content)
                self.assertEqual(2, self.request.return_value.get_res.call_count)
                self.sleep.assert_called_once_with(1)
                success.close.assert_called_once()
                if first is not None:
                    first.close.assert_called_once()

    def test_stream_exception_and_truncation_retry(self):
        broken = self.response()
        broken.iter_content.side_effect = requests.exceptions.ChunkedEncodingError("cut off")
        truncated = self.response(content=self.CONTENT[:8], headers={"Content-Length": str(len(self.CONTENT))})
        success = self.response()
        self.request.return_value.get_res.side_effect = [broken, truncated, success]

        path, content, error = self.download()

        self.assertEqual("", error)
        self.assertEqual(self.CONTENT, content)
        self.assertTrue(Path(path).is_file())
        self.assertEqual([1, 2], [call.args[0] for call in self.sleep.call_args_list])
        for response in (broken, truncated, success):
            response.close.assert_called_once()

    def test_retry_budget_is_bounded_and_does_not_write_empty_files(self):
        responses = [self.response(502, b"upstream unavailable") for _ in range(3)]
        self.request.return_value.get_res.side_effect = responses

        path, content, error = self.download()

        self.assertIsNone(path)
        self.assertIsNone(content)
        self.assertIn("502", error)
        self.assertEqual(3, self.request.return_value.get_res.call_count)
        self.assertEqual([1, 2], [call.args[0] for call in self.sleep.call_args_list])
        self.assertEqual([], list(Path(self.torrent._torrent_temp_path).iterdir()))
        for response in responses:
            response.close.assert_called_once()

    def test_rate_limit_stops_immediately_and_preserves_wait(self):
        response = self.response(429, headers={"Retry-After": "120"})
        self.request.return_value.get_res.return_value = response

        _, _, error = self.download()

        self.assertIn("限流", error)
        self.assertIn("120", error)
        self.sleep.assert_not_called()
        self.request.return_value.get_res.assert_called_once()
        response.close.assert_called_once()

    def test_json_quota_errors_are_not_retried_or_reported_as_corrupt_torrents(self):
        for status, message in (
                (200, "今天下载次数已达上限 passkey=private-value"),
                (503, "Too many requests token=private-value")):
            with self.subTest(status=status):
                self.request.reset_mock()
                response = self.response(status, json.dumps({"message": message}).encode())
                self.request.return_value.get_res.return_value = response

                _, _, error = self.download()

                self.assertTrue("配额" in error or "限流" in error)
                self.assertNotIn("private-value", error)
                self.assertNotIn("种子数据有误", error)
                self.request.return_value.get_res.assert_called_once()
                response.close.assert_called_once()
        self.sleep.assert_not_called()

    def test_permanent_http_errors_and_login_pages_are_not_retried(self):
        for response in (self.response(401), self.response(403), self.response(404),
                         self.response(200, b"<html>Login required</html>")):
            with self.subTest(status=response.status_code):
                self.request.reset_mock()
                self.request.return_value.get_res.return_value = response
                self.assertIsNone(self.download()[0])
                self.request.return_value.get_res.assert_called_once()
                response.close.assert_called_once()
        self.sleep.assert_not_called()

    def test_signed_url_and_redirected_ticket_are_consumed_once(self):
        for key in ("ticket", "signature", "X-Amz-Signature", "expires"):
            with self.subTest(key=key):
                self.request.reset_mock()
                self.request.return_value.get_res.return_value = None
                self.assertIsNone(self.download(f"https://tracker.example/download?{key}=secret")[0])
                self.request.return_value.get_res.assert_called_once()
        redirect = self.response(302, headers={"Location": "https://cdn.example/a?token=secret"})
        self.request.reset_mock()
        self.request.return_value.get_res.side_effect = [redirect, None]
        self.assertIsNone(self.download()[0])
        self.assertEqual(2, self.request.return_value.get_res.call_count)
        self.sleep.assert_not_called()

    def test_dynamic_resolved_url_does_not_retry_even_without_signature_marker(self):
        self.request.return_value.get_res.return_value = self.response(503)
        with patch.object(Torrent, "resolve_dynamic_download_url", return_value=(
                "https://tracker.example/temporary-download", "")) as resolve:
            result = self.torrent.get_torrent_info("[e30=]https://tracker.example/ticket")

        self.assertIsNone(result[0])
        resolve.assert_called_once()
        self.request.return_value.get_res.assert_called_once()
        self.sleep.assert_not_called()

    def test_dynamic_result_strips_credentials_when_origin_changes(self):
        for resolved in ("https://cdn.example/file", "https://tracker.example:8443/file",
                         "http://tracker.example/file"):
            with self.subTest(resolved=resolved):
                self.request.reset_mock()
                self.request.return_value.get_res.return_value = self.response()
                with patch.object(Torrent, "resolve_dynamic_download_url", return_value=(resolved, "")):
                    result = self.torrent.get_torrent_info(
                        "[e30=]https://tracker.example/ticket", cookie="session=secret",
                        ua={"Authorization": "Bearer secret", "X-Keep": "test"},
                        referer="https://tracker.example/details")
                self.assertEqual("", result[-1])
                options = self.request.call_args.kwargs
                self.assertIsNone(options["cookies"])
                self.assertIsNone(options["referer"])
                self.assertEqual({"X-Keep": "test"}, options["headers"])

    def test_dynamic_same_origin_keeps_credentials(self):
        self.request.return_value.get_res.return_value = self.response()
        with patch.object(Torrent, "resolve_dynamic_download_url", return_value=(
                "https://tracker.example/file", "")):
            result = self.torrent.get_torrent_info(
                "[e30=]https://tracker.example/ticket", cookie="session=secret",
                referer="https://tracker.example/details")
        self.assertEqual("", result[-1])
        self.assertEqual("session=secret", self.request.call_args.kwargs["cookies"])

    def test_retry_keeps_cross_origin_credentials_stripped(self):
        responses = [
            self.response(302, headers={"Location": "https://cdn.example/file"}),
            self.response(503),
            self.response(302, headers={"Location": "https://cdn.example/file"}),
            self.response(),
        ]
        self.request.return_value.get_res.side_effect = responses

        _, _, error = self.download(cookie="session=secret", ua={
            "Authorization": "Bearer secret", "X-Keep": "test",
        }, referer="https://tracker.example/details")

        self.assertEqual("", error)
        for index in (1, 3):
            options = self.request.call_args_list[index].kwargs
            self.assertIsNone(options["cookies"])
            self.assertIsNone(options["referer"])
            self.assertEqual({"X-Keep": "test"}, options["headers"])
        for response in responses:
            response.close.assert_called_once()

    def test_oversized_response_is_not_retried(self):
        response = self.response(headers={"Content-Length": str(Torrent._MAX_TORRENT_SIZE + 1)})
        self.request.return_value.get_res.return_value = response
        self.assertIn("20MB", self.download()[2])
        response.iter_content.assert_not_called()
        self.request.return_value.get_res.assert_called_once()
        self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
