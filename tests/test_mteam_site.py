import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from app.helper.indexer_helper import IndexerConf, IndexerHelper
from app.indexer.client._api_spider import MTorrentSpider
from app.sites.sites import Sites


class MTeamSiteTest(unittest.TestCase):
    def setUp(self):
        config = patch("app.indexer.client._api_spider.Config").start()
        self.addCleanup(patch.stopall)
        config.return_value.get_ua.return_value = "fixture-agent"
        config.return_value.get_config.return_value = {"site_search_result_num": 30}
        config.return_value.get_proxies.return_value = {"https": "http://proxy.example:8080"}
        self.request = patch("app.indexer.client._api_spider.RequestUtils").start()

    @staticmethod
    def _response(payload=None, status=200):
        response = MagicMock()
        response.status_code = status
        response.__bool__.return_value = status < 400
        response.json.return_value = payload
        return response

    def _site(self, url="https://kp.m-team.cc/", apikey="fixture-api-key", cookie=None,
              proxy=False):
        sites = Sites.__wrapped__.__new__(Sites.__wrapped__)
        sites.get_sites = MagicMock(return_value={
            "id": 1, "name": "馒头", "signurl": url, "apikey": apikey,
            "cookie": cookie, "ua": "fixture-agent", "proxy": proxy
        })
        return sites

    def test_api_key_only_connection_uses_profile_for_all_web_domains(self):
        for url in ("https://kp.m-team.cc/", "https://m-team.cc/", "https://m-team.io/"):
            with self.subTest(url=url):
                self.request.reset_mock()
                response = self._response({"code": "0", "data": {"id": "123"}})
                self.request.return_value.post_res.return_value = response
                success, message, elapsed = self._site(url).test_connection(1)
                self.assertTrue(success)
                self.assertEqual("连接成功", message)
                self.assertGreaterEqual(elapsed, 0)
                self.request.return_value.post_res.assert_called_once_with(
                    url="https://api.m-team.cc/api/member/profile", json=None,
                    allow_redirects=False)
                self.assertIsNone(self.request.call_args.kwargs["cookies"])
                self.assertEqual("fixture-api-key",
                                 self.request.call_args.kwargs["headers"]["x-api-key"])
                response.close.assert_called_once()

    def test_cookie_only_connection_explains_api_key_requirement_without_request(self):
        success, message, _ = self._site(apikey=None, cookie="session=fixture").test_connection(1)
        self.assertFalse(success)
        self.assertIn("API Key", message)
        self.assertIn("未配置", message)
        self.request.assert_not_called()

    def test_connection_honors_proxy_but_does_not_send_web_cookie(self):
        self.request.return_value.post_res.return_value = self._response(
            {"code": 0, "data": {"id": "123"}})
        self.assertTrue(self._site(cookie="session=web-only", proxy=True).test_connection(1)[0])
        self.assertIsNone(self.request.call_args.kwargs["cookies"])
        self.assertEqual({"https": "http://proxy.example:8080"},
                         self.request.call_args.kwargs["proxies"])

    def test_profile_handles_http_failures_and_never_follows_redirects(self):
        for status in (301, 401, 403, 500):
            with self.subTest(status=status):
                response = self._response({"message": "secret-response"}, status)
                self.request.return_value.post_res.return_value = response
                success, message, _ = self._site().test_connection(1)
                self.assertFalse(success)
                self.assertNotIn("secret-response", message)
                self.assertFalse(self.request.return_value.post_res.call_args.kwargs["allow_redirects"])
                if status in (401, 403):
                    self.assertIn("API Key", message)
                else:
                    self.assertIn(str(status), message)
                response.json.assert_not_called()
                response.close.assert_called_once()

    def test_profile_rejects_business_errors_and_malformed_data(self):
        for payload in (
            {"code": "1", "message": "secret-response", "data": {"id": "123"}},
            {"code": 0, "data": {}}, {"code": 0, "data": []},
            {"code": 0, "data": "secret-response"}, {"data": {"id": "123"}},
            [], None,
        ):
            with self.subTest(payload=payload):
                response = self._response(payload)
                self.request.return_value.post_res.return_value = response
                success, message, _ = self._site().test_connection(1)
                self.assertFalse(success)
                self.assertNotIn("secret-response", message)
                response.close.assert_called_once()

    def test_profile_handles_network_failure_and_invalid_json(self):
        self.request.return_value.post_res.return_value = None
        self.assertIn("无法连接", self._site().test_connection(1)[1])
        response = self._response()
        response.json.side_effect = ValueError("secret-response")
        self.request.return_value.post_res.return_value = response
        success, message, _ = self._site().test_connection(1)
        self.assertFalse(success)
        self.assertIn("JSON", message)
        self.assertNotIn("secret-response", message)
        response.close.assert_called_once()

    def test_other_sites_still_require_cookie(self):
        success, message, _ = self._site(url="https://hdhome.org/").test_connection(1)
        self.assertFalse(success)
        self.assertEqual("未配置站点Cookie", message)
        self.request.assert_not_called()

    def test_search_and_download_use_api_domain_separately_from_web_domain(self):
        for url in ("https://kp.m-team.cc/", "https://m-team.cc/", "https://m-team.io/"):
            with self.subTest(url=url):
                self.request.reset_mock()
                response = self._response({"code": 0, "data": {"data": [{
                    "id": "123", "name": "Fixture Movie", "size": "1024",
                    "category": "401", "status": {"discount": "FREE", "seeders": "2"}
                }]}})
                self.request.return_value.post_res.return_value = response
                indexer = IndexerHelper().get_indexer(url, apikey="fixture-api-key",
                                                     cookie="session=web-only")
                results = MTorrentSpider(indexer).search("Fixture")
                self.assertEqual(1, len(results))
                torrent = results[0]
                self.assertEqual(url + "detail/123", torrent["page_url"])
                self.assertEqual(0, torrent["downloadvolumefactor"])
                self.assertEqual(2, torrent["seeders"])
                self.assertTrue(torrent["enclosure"].endswith(
                    "]https://api.m-team.cc/api/torrent/genDlToken"))
                descriptor = json.loads(base64.b64decode(
                    torrent["enclosure"][1: torrent["enclosure"].index("]")]))
                self.assertEqual("{apikey}", descriptor["header"]["x-api-key"])
                self.assertFalse(descriptor["cookie"])
                self.assertNotIn("fixture-api-key", json.dumps(results))
                self.assertIsNone(self.request.call_args.kwargs["cookies"])
                self.request.return_value.post_res.assert_called_once_with(
                    url="https://api.m-team.cc/api/torrent/search",
                    json={"keyword": "Fixture", "categories": [], "pageNumber": 1,
                          "pageSize": 30, "visible": 1},
                    allow_redirects=False)
                response.close.assert_called_once()

    def test_search_rejects_api_failure_even_when_payload_contains_torrents(self):
        indexer = IndexerHelper().get_indexer("https://kp.m-team.cc/", apikey="fixture-api-key")
        for payload in (
            {"code": 1, "data": {"data": [{"id": "123"}]}, "message": "secret-response"},
            {"code": 0, "data": {"data": "invalid"}},
            {"code": 0, "data": []}, [],
        ):
            with self.subTest(payload=payload), patch("app.indexer.client._api_spider.log.warn") as warn:
                response = self._response(payload)
                self.request.return_value.post_res.return_value = response
                self.assertEqual([], MTorrentSpider(indexer).search("Fixture"))
                self.assertNotIn("secret-response", str(warn.call_args_list))
                response.close.assert_called_once()

    def test_missing_api_key_skips_search(self):
        indexer = IndexerHelper().get_indexer("https://kp.m-team.cc/")
        self.assertEqual([], MTorrentSpider(indexer).search("Fixture"))
        self.request.assert_not_called()

    def test_configured_api_domain_is_used_and_insecure_domain_is_rejected(self):
        indexer = IndexerConf(datas={
            "id": "mteam", "name": "馒头", "domain": "https://kp.m-team.cc/",
            "api_domain": "https://api.custom.example/", "parser": "MTorrentSpider"
        }, apikey="fixture-api-key")
        response = self._response({"code": 0, "data": {"id": "123"}})
        self.request.return_value.post_res.return_value = response
        self.assertTrue(MTorrentSpider(indexer).test_connection()[0])
        self.assertEqual("https://api.custom.example/api/member/profile",
                         self.request.return_value.post_res.call_args.kwargs["url"])
        for invalid in ("http://api.m-team.cc/", "https://[", "https://user@api.m-team.cc/",
                        "https://api.m-team.cc/?token=secret", 123):
            with self.subTest(api_domain=invalid):
                self.request.reset_mock()
                indexer.api_domain = invalid
                self.assertFalse(MTorrentSpider(indexer).test_connection()[0])
                self.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
