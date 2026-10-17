import datetime
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock

from pyquery import PyQuery

from app.helper.indexer_helper import IndexerHelper
from app.indexer.client._spider import TorrentSpider
from app.utils.types import MediaType


class PlayLetSiteTest(unittest.TestCase):
    @staticmethod
    def _spider(keyword=None, page=0, mtype=None):
        indexer = IndexerHelper().get_indexer("https://playlet.cc/", cookie="session=test")
        spider = TorrentSpider()
        spider.setparam(indexer, keyword=keyword, page=page, mtype=mtype)
        return spider

    @staticmethod
    def _row(promotion="", title_attribute=' title="完整短剧 2026 1080p"', date=None):
        # 按公开的 PlayLet/NexusPHP 适配契约构造，不包含真实站点账号或种子数据。
        date = date or '<span title="2026-10-18 12:30:00">1 小时</span>'
        return f"""
            <tr>
              <td class="rowfollow"><a href="?cat=408">短剧</a></td>
              <td class="rowfollow">
                <table class="torrentname"><tr><td class="embedded">
                  <a href="details.php?id=123&amp;hit=1"{title_attribute}><b>短剧标题</b></a>
                  <img class="{promotion}" />
                  <a href="download.php?id=123">下载</a>
                  <br />剧情说明
                </td></tr></table>
              </td>
              <td class="rowfollow">2</td>
              <td class="rowfollow">{date}</td>
              <td class="rowfollow">1.5<br />GB</td>
              <td class="rowfollow">12</td>
              <td class="rowfollow">3</td>
              <td class="rowfollow">45</td>
              <td class="rowfollow">匿名</td>
            </tr>
        """

    def test_catalog_identifies_current_and_legacy_domain(self):
        helper = IndexerHelper()
        for url in ("https://playlet.cc/", "https://playletpt.xyz/"):
            with self.subTest(url=url):
                indexer = helper.get_indexer(url)
                self.assertEqual("playletpt", indexer.id)
                self.assertEqual("PlayLet", indexer.name)
                self.assertEqual(url.rstrip("/"), indexer.domain.rstrip("/"))

    def test_search_encodes_keyword_and_uses_zero_based_pagination(self):
        spider = self._spider(keyword="短剧 & Demo", page=2, mtype=MediaType.TV)
        requests = list(spider.start_requests())
        self.assertEqual(1, len(requests))
        parsed = urlparse(requests[0].url)
        self.assertEqual("https", parsed.scheme)
        self.assertEqual("playlet.cc", parsed.netloc)
        self.assertEqual("/torrents.php", parsed.path)
        params = parse_qs(parsed.query)
        self.assertEqual(["短剧 & Demo"], params["search"])
        self.assertEqual(["2"], params["page"])
        self.assertEqual(["0"], params["search_area"])
        self.assertEqual(["0"], params["incldead"])
        self.assertEqual(["1"], params["cat408"])
        self.assertEqual(["1"], params["cat409"])

    def test_imdb_search_uses_imdb_field(self):
        request = next(self._spider(keyword="tt1234567").start_requests())
        self.assertEqual(["4"], parse_qs(urlparse(request.url).query)["search_area"])

    def test_browse_keeps_requested_page(self):
        for page in (0, 3):
            with self.subTest(page=page):
                request = next(self._spider(page=page).start_requests())
                parsed = urlparse(request.url)
                self.assertEqual("/torrents.php", parsed.path)
                self.assertEqual([str(page)], parse_qs(parsed.query)["page"])

    def test_torrent_fields_and_table_wrappers(self):
        for wrapper in ("{row}", "<tbody>{row}</tbody>"):
            with self.subTest(wrapper=wrapper):
                spider = self._spider()
                response = MagicMock()
                response.extract.return_value = (
                    '<table class="torrents"><tr><td>表头</td></tr>'
                    + wrapper.format(row=self._row("pro_free2up"))
                    + '</table>'
                )
                spider.parse(None, response)
                self.assertEqual(1, len(spider.torrents_info_array))
                torrent = spider.torrents_info_array[0]
                self.assertEqual("完整短剧 2026 1080p", torrent["title"])
                self.assertEqual("剧情说明", torrent["description"])
                self.assertEqual("电视剧", torrent["category"])
                self.assertEqual("https://playlet.cc/details.php?id=123&hit=1", torrent["page_url"])
                self.assertEqual("https://playlet.cc/download.php?id=123", torrent["enclosure"])
                self.assertEqual(1610612736, torrent["size"])
                self.assertEqual("12", torrent["seeders"])
                self.assertEqual("3", torrent["peers"])
                self.assertEqual("45", torrent["grabs"])
                self.assertEqual(datetime.datetime(2026, 10, 18, 12, 30), torrent["pubdate"])
                self.assertEqual(0, torrent["downloadvolumefactor"])
                self.assertEqual(2, torrent["uploadvolumefactor"])

    def test_title_and_date_without_optional_attributes(self):
        torrent = self._spider().Getinfo(PyQuery(self._row(
            title_attribute="", date="2026-10-18<br />12:30:00"
        )))
        self.assertEqual("短剧标题", torrent["title"])
        self.assertEqual(datetime.datetime(2026, 10, 18, 12, 30), torrent["pubdate"])

    def test_promotion_factors(self):
        cases = (
            ("", 1, 1),
            ("pro_free", 0, 1),
            ("pro_free2up", 0, 2),
            ("pro_50pctdown", 0.5, 1),
            ("pro_50pctdown2up", 0.5, 2),
            ("pro_30pctdown", 0.3, 1),
            ("pro_2up", 1, 2),
        )
        for promotion, download_factor, upload_factor in cases:
            with self.subTest(promotion=promotion):
                torrent = self._spider().Getinfo(PyQuery(self._row(promotion)))
                self.assertEqual(download_factor, torrent["downloadvolumefactor"])
                self.assertEqual(upload_factor, torrent["uploadvolumefactor"])


if __name__ == "__main__":
    unittest.main()
