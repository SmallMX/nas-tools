import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pyquery import PyQuery

from app.helper.indexer_helper import IndexerConf, IndexerHelper
from app.indexer.client._api_spider import MTorrentSpider
from app.indexer.client._spider import TorrentSpider
from app.utils.torrent import Torrent


class IndexerSitesTest(unittest.TestCase):
    _TORRENT_CONTENT = b"d4:infod4:name4:testee"

    @classmethod
    def _response(cls, status_code=200, headers=None, content=None):
        response = MagicMock()
        response.status_code = status_code
        response.headers = headers or {}
        response.content = cls._TORRENT_CONTENT if content is None else content
        response.iter_content.return_value = [response.content]
        return response

    def test_moviepilot_site_overlays_and_aliases(self):
        helper = IndexerHelper()

        mteam = helper.get_indexer(url="https://kp.m-team.cc/", apikey="secret")
        self.assertEqual("mteam", mteam.id)
        self.assertEqual("https://m-team.io/", mteam.domain)
        self.assertEqual("MTorrentSpider", mteam.parser)
        self.assertEqual("secret", mteam.apikey)

        expected = {
            "https://yemapt.org/": "YemaSpider",
            "https://haidan.video/": "HaiDanSpider",
            "https://hddolby.com/": "HDDolbySpider",
            "https://rousi.pro/": "RousiSpider"
        }
        for url, parser in expected.items():
            with self.subTest(url=url):
                self.assertEqual(parser, helper.get_indexer(url=url).parser)

        merged = helper._IndexerHelper__merge_dict(
            {"search": {"params": {"search": "old", "page": 0}}},
            {"search": {"params": {"search": "new"}}}
        )
        self.assertEqual({"search": {"params": {"search": "new", "page": 0}}}, merged)

    @patch("app.utils.torrent.RequestUtils")
    def test_dynamic_download_url(self, request_utils):
        response = request_utils.return_value.get_res.return_value
        response.status_code = 200
        response.json.return_value = {
            "data": {"download_url": "https://example.com/test.torrent"}
        }
        descriptor = base64.b64encode(json.dumps({
            "method": "get",
            "header": {"Authorization": "Bearer {apikey}"},
            "result": "data.download_url"
        }).encode("utf-8")).decode("utf-8")

        url, error = Torrent.resolve_dynamic_download_url(
            f"[{descriptor}]https://example.com/api/torrents/1",
            apikey="secret")

        self.assertEqual("", error)
        self.assertEqual("https://example.com/test.torrent", url)
        request_utils.return_value.get_res.assert_called_once_with(
            url="https://example.com/api/torrents/1",
            params=None,
            allow_redirects=False,
        )
        request_utils.assert_called_once_with(
            headers={"Authorization": "Bearer secret"},
            cookies=None,
            proxies=None)

    def test_dynamic_download_does_not_leak_cookie_cross_site(self):
        descriptor = base64.b64encode(json.dumps({
            "method": "get",
            "cookie": True,
            "result": "data.download_url"
        }).encode("utf-8")).decode("utf-8")

        url, error = Torrent.resolve_dynamic_download_url(
            f"[{descriptor}]https://attacker.example/api/torrents/1",
            cookie="session=secret",
            source_url="https://tracker.example/details/1")

        self.assertIsNone(url)
        self.assertIn("已拒绝发送 Cookie", error)

    @patch("app.utils.torrent.RequestUtils")
    def test_dynamic_download_redirect_strips_cross_host_credentials(self, request_utils):
        redirect = self._response(
            status_code=302,
            headers={"Location": "https://attacker.example/dynamic"},
        )
        success = self._response()
        success.json.return_value = {
            "data": {"download_url": "https://cdn.example/test.torrent"}
        }
        request_utils.return_value.get_res.side_effect = [redirect, success]
        descriptor = base64.b64encode(json.dumps({
            "method": "get",
            "cookie": True,
            "header": {
                "Authorization": "Bearer secret-token",
                "X-Api-Key": "secret-key",
                "Referer": "https://tracker.example/details/1",
                "X-Keep": "value",
            },
            "result": "data.download_url",
        }).encode("utf-8")).decode("utf-8")

        url, error = Torrent.resolve_dynamic_download_url(
            f"[{descriptor}]https://tracker.example/api/torrents/1",
            cookie="session=secret",
            source_url="https://tracker.example/details/1",
        )

        self.assertEqual("", error)
        self.assertEqual("https://cdn.example/test.torrent", url)
        first_request = request_utils.call_args_list[0].kwargs
        second_request = request_utils.call_args_list[1].kwargs
        self.assertEqual("session=secret", first_request["cookies"])
        self.assertIsNone(second_request["cookies"])
        self.assertEqual({"X-Keep": "value"}, second_request["headers"])
        for request_call in request_utils.return_value.get_res.call_args_list:
            self.assertFalse(request_call.kwargs["allow_redirects"])

    @patch("app.utils.torrent.RequestUtils")
    def test_dynamic_download_https_downgrade_strips_credentials(self, request_utils):
        redirect = self._response(
            status_code=307,
            headers={"Location": "http://tracker.example/dynamic"},
        )
        success = self._response()
        success.json.return_value = {
            "data": {"download_url": "https://cdn.example/test.torrent"}
        }
        request_utils.return_value.post_res.side_effect = [redirect, success]
        descriptor = base64.b64encode(json.dumps({
            "method": "post",
            "cookie": True,
            "header": {
                "Authorization": "Bearer secret-token",
                "Referer": "https://tracker.example/details/1",
                "X-Keep": "value",
            },
            "params": {"passkey": "secret-passkey"},
            "result": "data.download_url",
        }).encode("utf-8")).decode("utf-8")

        url, error = Torrent.resolve_dynamic_download_url(
            f"[{descriptor}]https://tracker.example/api/torrents/1",
            cookie="session=secret",
            source_url="https://tracker.example/details/1",
        )

        self.assertEqual("", error)
        self.assertEqual("https://cdn.example/test.torrent", url)
        second_request = request_utils.call_args_list[1].kwargs
        self.assertIsNone(second_request["cookies"])
        self.assertEqual({"X-Keep": "value"}, second_request["headers"])
        self.assertIsNone(
            request_utils.return_value.post_res.call_args_list[1].kwargs["params"]
        )

    @patch("app.utils.torrent.RequestUtils")
    def test_dynamic_download_malformed_location_closes_response(self, request_utils):
        response = self._response(
            status_code=302,
            headers={"Location": "http://[invalid"},
        )
        request_utils.return_value.get_res.return_value = response
        descriptor = base64.b64encode(json.dumps({
            "method": "get",
            "result": "data.download_url",
        }).encode("utf-8")).decode("utf-8")

        url, error = Torrent.resolve_dynamic_download_url(
            f"[{descriptor}]https://tracker.example/api/torrents/1"
        )

        self.assertIsNone(url)
        self.assertIn("重定向仅支持", error)
        response.close.assert_called_once_with()

    @patch("app.utils.torrent.RequestUtils")
    def test_dynamic_download_redirect_loop_is_rejected(self, request_utils):
        request_utils.return_value.get_res.return_value = self._response(
            status_code=301,
            headers={"Location": "/api/torrents/1"},
        )
        descriptor = base64.b64encode(json.dumps({
            "method": "get",
            "result": "data.download_url",
        }).encode("utf-8")).decode("utf-8")

        url, error = Torrent.resolve_dynamic_download_url(
            f"[{descriptor}]https://tracker.example/api/torrents/1"
        )

        self.assertIsNone(url)
        self.assertIn("循环重定向", error)
        request_utils.return_value.get_res.assert_called_once()

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_download_ignores_remote_filename_and_writes_unique_temp_file(self, request_utils):
        response = self._response(headers={
            "Content-Disposition": 'attachment; filename="../outside.torrent"'
        })
        request_utils.return_value.get_res.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir) / "temp"
            temp_root.mkdir()
            outside_path = Path(temp_dir) / "outside.torrent"
            torrent = Torrent.__new__(Torrent)
            torrent._torrent_temp_path = str(temp_root)

            file_path, content, error = torrent.save_torrent_file(
                "https://tracker.example/download?id=1"
            )

            saved_path = Path(file_path)
            self.assertEqual("", error)
            self.assertEqual(self._TORRENT_CONTENT, content)
            self.assertEqual(temp_root, saved_path.parent)
            self.assertTrue(saved_path.name.startswith("torrent-"))
            self.assertEqual(".torrent", saved_path.suffix)
            self.assertEqual(self._TORRENT_CONTENT, saved_path.read_bytes())
            self.assertFalse(outside_path.exists())

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_cross_host_redirect_strips_cookie_and_referer(self, request_utils):
        request_utils.return_value.get_res.side_effect = [
            self._response(
                status_code=302,
                headers={"Location": "https://cdn.example/files/test.torrent"},
            ),
            self._response(),
        ]
        headers = {
            "User-Agent": "test",
            "Cookie": "header-secret",
            "Referer": "https://tracker.example/details?id=1",
            "X-Keep": "value",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            torrent = Torrent.__new__(Torrent)
            torrent._torrent_temp_path = temp_dir
            file_path, _, error = torrent.save_torrent_file(
                "https://tracker.example/download?id=1",
                cookie="session=secret",
                ua=headers,
                referer="https://tracker.example/details?id=1",
            )

        self.assertEqual("", error)
        self.assertIsNotNone(file_path)
        first_request = request_utils.call_args_list[0].kwargs
        second_request = request_utils.call_args_list[1].kwargs
        self.assertEqual("session=secret", first_request["cookies"])
        self.assertEqual("https://tracker.example/details?id=1", first_request["referer"])
        self.assertIsNone(second_request["cookies"])
        self.assertIsNone(second_request["referer"])
        self.assertEqual(
            {"User-Agent": "test", "X-Keep": "value"},
            second_request["headers"],
        )
        self.assertEqual(
            "https://cdn.example/files/test.torrent",
            request_utils.return_value.get_res.call_args_list[1].kwargs["url"],
        )

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_same_host_port_change_strips_credentials(self, request_utils):
        request_utils.return_value.get_res.side_effect = [
            self._response(
                status_code=308,
                headers={"Location": "https://tracker.example:8443/files/test.torrent"},
            ),
            self._response(),
        ]
        headers = {
            "Authorization": "Bearer secret-token",
            "Referer": "https://tracker.example/details/1",
            "X-Keep": "value",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            torrent = Torrent.__new__(Torrent)
            torrent._torrent_temp_path = temp_dir
            file_path, _, error = torrent.save_torrent_file(
                "https://tracker.example/download",
                cookie="session=secret",
                ua=headers,
                referer="https://tracker.example/details/1",
            )

        self.assertEqual("", error)
        self.assertIsNotNone(file_path)
        second_request = request_utils.call_args_list[1].kwargs
        self.assertIsNone(second_request["cookies"])
        self.assertIsNone(second_request["referer"])
        self.assertEqual({"X-Keep": "value"}, second_request["headers"])

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_malformed_location_closes_response(self, request_utils):
        response = self._response(
            status_code=302,
            headers={"Location": "http://[invalid"},
        )
        request_utils.return_value.get_res.return_value = response
        torrent = Torrent.__new__(Torrent)
        torrent._torrent_temp_path = "/unused"

        file_path, content, error = torrent.save_torrent_file(
            "https://tracker.example/download"
        )

        self.assertIsNone(file_path)
        self.assertIsNone(content)
        self.assertIn("重定向仅支持", error)
        response.close.assert_called_once_with()

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_relative_redirect_is_resolved(self, request_utils):
        request_utils.return_value.get_res.side_effect = [
            self._response(status_code=307, headers={"Location": "../files/test.torrent"}),
            self._response(),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            torrent = Torrent.__new__(Torrent)
            torrent._torrent_temp_path = temp_dir
            file_path, _, error = torrent.save_torrent_file(
                "https://tracker.example/download/start"
            )

        self.assertEqual("", error)
        self.assertIsNotNone(file_path)
        self.assertEqual(
            "https://tracker.example/files/test.torrent",
            request_utils.return_value.get_res.call_args_list[1].kwargs["url"],
        )

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_redirect_loop_is_rejected(self, request_utils):
        request_utils.return_value.get_res.return_value = self._response(
            status_code=308,
            headers={"Location": "/download?passkey=secret"},
        )
        torrent = Torrent.__new__(Torrent)
        torrent._torrent_temp_path = "/unused"

        file_path, content, error = torrent.save_torrent_file(
            "https://tracker.example/download?passkey=secret"
        )

        self.assertIsNone(file_path)
        self.assertIsNone(content)
        self.assertIn("循环重定向", error)
        self.assertNotIn("secret", error)
        request_utils.return_value.get_res.assert_called_once()

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_redirect_limit_is_enforced(self, request_utils):
        request_utils.return_value.get_res.side_effect = [
            self._response(status_code=303, headers={"Location": f"/step/{index}"})
            for index in range(1, 7)
        ]
        torrent = Torrent.__new__(Torrent)
        torrent._torrent_temp_path = "/unused"

        file_path, content, error = torrent.save_torrent_file(
            "https://tracker.example/start"
        )

        self.assertIsNone(file_path)
        self.assertIsNone(content)
        self.assertIn("重定向次数超过限制", error)
        self.assertEqual(6, request_utils.return_value.get_res.call_count)

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_response_size_is_limited(self, request_utils):
        request_utils.return_value.get_res.return_value = self._response(headers={
            "Content-Length": str(Torrent._MAX_TORRENT_SIZE + 1)
        })
        torrent = Torrent.__new__(Torrent)
        torrent._torrent_temp_path = "/unused"

        file_path, content, error = torrent.save_torrent_file(
            "https://tracker.example/download?passkey=secret"
        )

        self.assertIsNone(file_path)
        self.assertIsNone(content)
        self.assertIn("20MB", error)
        self.assertNotIn("secret", error)
        request_utils.return_value.get_res.return_value.iter_content.assert_not_called()

    @patch("app.utils.torrent.RequestUtils")
    def test_torrent_stream_stops_as_soon_as_size_limit_is_exceeded(self, request_utils):
        response = self._response(headers={})
        consumed_chunks = []

        def chunks():
            for chunk in (b"12345", b"6789", b"must-not-be-read"):
                consumed_chunks.append(chunk)
                yield chunk

        response.iter_content.return_value = chunks()
        request_utils.return_value.get_res.return_value = response
        torrent = Torrent.__new__(Torrent)
        torrent._torrent_temp_path = "/unused"

        with patch.object(Torrent, "_MAX_TORRENT_SIZE", 8):
            file_path, content, error = torrent.save_torrent_file(
                "https://tracker.example/download"
            )

        self.assertIsNone(file_path)
        self.assertIsNone(content)
        self.assertIn("20MB", error)
        self.assertEqual([b"12345", b"6789"], consumed_chunks)
        response.iter_content.assert_called_once_with(chunk_size=64 * 1024)
        response.close.assert_called_once_with()
        request_utils.return_value.get_res.assert_called_once_with(
            url="https://tracker.example/download",
            allow_redirects=False,
            stream=True,
        )

    def test_generic_spider_newer_site_fields(self):
        indexer = IndexerConf(datas={
            "id": "demo",
            "name": "Demo",
            "domain": "https://example.com/",
            "search": {"paths": [{"path": "torrents.php"}]},
            "category": {
                "movie": [{"id": "401"}],
                "tv": [{"id": "402"}]
            },
            "torrents": {
                "list": {"selector": "tr"},
                "fields": {
                    "title": {"selector": "a.title"},
                    "details": {"selector": "a.title", "attribute": "href"},
                    "download": {
                        "selector": "a.download",
                        "attribute": "href",
                        "filters": [{"name": "lstrip", "args": ["/"]}]
                    },
                    "category": {
                        "selector": "a.category",
                        "attribute": "href",
                        "filters": [{"name": "querystring", "args": "cat"}]
                    },
                    "date_added": {"selector": "span.date", "attribute": "title"},
                    "date": {
                        "text": "{{ fields['date_added'] }}",
                        "filters": [{"name": "dateparse", "args": "%Y-%m-%d %H:%M:%S"}]
                    },
                    "free_deadline": {
                        "selector": "span.free",
                        "attribute": "title",
                        "filters": [{"name": "dateparse", "args": "%Y-%m-%d %H:%M:%S"}]
                    },
                    "downloadvolumefactor": {"case": {"span.free": 0, "*": 1}},
                    "uploadvolumefactor": {"case": {"*": 1}}
                }
            }
        })
        spider = TorrentSpider()
        spider.setparam(indexer)
        torrent = PyQuery("""
            <tr><td>
              <a class="title" href="details.php?id=1">Demo Movie</a>
              <a class="download" href="/download.php?id=1">Download</a>
              <a class="category" href="?cat=401">Movie</a>
              <span class="date" title="2026-07-13 12:00:00"></span>
              <span class="free" title="2026-07-14 12:00:00"></span>
            </td></tr>
        """)

        result = spider.Getinfo(torrent)

        self.assertEqual("https://example.com/download.php?id=1", result.get("enclosure"))
        self.assertEqual("电影", result.get("category"))
        self.assertEqual(0, result.get("downloadvolumefactor"))
        self.assertEqual(2026, result.get("pubdate").year)
        self.assertEqual(14, result.get("freedate").day)

    @patch("app.indexer.client._api_spider.RequestUtils")
    def test_mteam_search_does_not_embed_api_key_in_result(self, request_utils):
        response = request_utils.return_value.post_res.return_value
        response.status_code = 200
        response.json.return_value = {
            "data": {
                "data": [{
                    "id": "1",
                    "name": "Demo Movie 2026 1080p",
                    "category": "401",
                    "createdDate": "1783920000",
                    "size": "1024",
                    "status": {"seeders": 2, "leechers": 1, "timesCompleted": 3}
                }]
            }
        }
        indexer = IndexerConf(
            datas={
                "id": "mteam",
                "name": "馒头",
                "domain": "https://m-team.io/",
                "parser": "MTorrentSpider"
            },
            apikey="very-secret"
        )

        results = MTorrentSpider(indexer).search(keyword="Demo")

        self.assertEqual(1, len(results))
        enclosure = results[0].get("enclosure")
        self.assertNotIn("very-secret", enclosure)
        encoded = enclosure[1:enclosure.index("]")]
        descriptor = json.loads(base64.b64decode(encoded).decode("utf-8"))
        self.assertEqual("{apikey}", descriptor.get("header", {}).get("x-api-key"))


if __name__ == "__main__":
    unittest.main()
