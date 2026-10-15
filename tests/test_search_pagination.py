import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from app.helper.indexer_helper import IndexerConf, IndexerHelper
from app.indexer.client._spider import TorrentSpider


class SearchPaginationTest(unittest.TestCase):
    @staticmethod
    def _spider(indexer, page, keyword="Example"):
        spider = TorrentSpider()
        spider.setparam(indexer, keyword=keyword, page=page)
        return spider

    @staticmethod
    def _request_url(spider):
        requests = list(spider.start_requests())
        if len(requests) != 1:
            raise AssertionError(f"Expected one request, got {len(requests)}")
        return requests[0].url

    def test_public_sites_use_distinct_server_search_pages(self):
        helper = IndexerHelper()
        cases = (
            ("https://1337x.to/", "/search/Example/1/", "/search/Example/2/", None),
            ("https://nyaa.si/", "/", "/", "p"),
            ("https://acg.rip/", "/page/1", "/page/2", None),
        )
        for domain, first_path, second_path, page_parameter in cases:
            with self.subTest(domain=domain):
                indexer = helper.get_indexer(domain)
                first = self._request_url(self._spider(indexer, 0))
                second = self._request_url(self._spider(indexer, 1))
                self.assertNotEqual(first, second)
                self.assertEqual(first_path, urlparse(first).path)
                self.assertEqual(second_path, urlparse(second).path)
                self.assertEqual(first, self._request_url(self._spider(indexer, None)))
                if page_parameter:
                    self.assertEqual(["1"], parse_qs(urlparse(first).query)[page_parameter])
                    self.assertEqual(["2"], parse_qs(urlparse(second).query)[page_parameter])

    def test_search_keyword_cannot_change_path_or_query_parameters(self):
        helper = IndexerHelper()
        keyword = "Show/Film & p=99 # end"
        for domain, parameter in (("https://nyaa.si/", "q"), ("https://acg.rip/", "term")):
            with self.subTest(domain=domain):
                url = self._request_url(self._spider(helper.get_indexer(domain), 1, keyword))
                parsed = urlparse(url)
                self.assertEqual([keyword], parse_qs(parsed.query)[parameter])
                self.assertEqual("", parsed.fragment)
        url = self._request_url(self._spider(helper.get_indexer("https://1337x.to/"), 1, keyword))
        self.assertEqual("/search/Show%2FFilm%20%26%20p%3D99%20%23%20end/2/", urlparse(url).path)

    def test_nyaa_and_acg_browse_keep_one_based_page_numbers(self):
        helper = IndexerHelper()
        for domain in ("https://nyaa.si/", "https://acg.rip/"):
            with self.subTest(domain=domain):
                indexer = helper.get_indexer(domain)
                first = self._request_url(self._spider(indexer, 0, keyword=None))
                second = self._request_url(self._spider(indexer, 1, keyword=None))
                self.assertNotEqual(first, second)
                if indexer.id == "nyaa":
                    self.assertEqual(["2"], parse_qs(urlparse(second).query)["p"])
                else:
                    self.assertEqual("/page/2", urlparse(second).path)

    def test_parameter_search_preserves_zero_based_default(self):
        indexer = IndexerConf(datas={
            "id": "demo", "name": "Demo", "domain": "https://example.com/",
            "search": {"paths": [{"path": "torrents.php"}], "params": {"search": "{keyword}"}}
        })
        query = parse_qs(urlparse(self._request_url(self._spider(indexer, 2))).query)
        self.assertEqual(["2"], query["page"])
        self.assertEqual(["Example"], query["search"])

    def test_parameter_search_formats_page_placeholder_and_start(self):
        indexer = IndexerConf(datas={
            "id": "demo", "name": "Demo", "domain": "https://example.com/",
            "search": {"start": 1, "paths": [{"path": "torrents.php"}],
                       "params": {"q": "{keyword}", "page": "{page}"}}
        })
        query = parse_qs(urlparse(self._request_url(self._spider(indexer, 2))).query)
        self.assertEqual(["3"], query["page"])

    def test_server_page_rows_are_not_locally_offset_again(self):
        indexer = IndexerHelper().get_indexer("https://nyaa.si/")
        spider = self._spider(indexer, 1)
        self._request_url(spider)
        spider.list = {"selector": "tr"}
        spider.fields = {"title": {"selector": "td"}}
        spider.result_num = 2
        response = Mock()
        response.extract.return_value = "<table><tr><td>Second page A</td></tr><tr><td>Second page B</td></tr></table>"

        spider.parse(None, response)

        self.assertEqual(["Second page A", "Second page B"], [item["title"] for item in spider.torrents_info_array])


if __name__ == "__main__":
    unittest.main()
