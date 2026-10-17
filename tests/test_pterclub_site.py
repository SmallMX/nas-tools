import unittest
from urllib.parse import urlsplit

from lxml import etree
from pyquery import PyQuery

from app.conf.siteconf import SiteConf
from app.helper.indexer_helper import IndexerHelper
from app.indexer.client._spider import TorrentSpider
from app.sites.cookiecloud import cookiecloud_site_candidates


class PterClubSiteTest(unittest.TestCase):
    def setUp(self):
        self.helper = IndexerHelper()

    def test_new_domain_and_legacy_alias_share_builtin_identity(self):
        sites = [site for site in self.helper.get_all_indexers() if site.get("id") == "pterclub"]
        self.assertEqual(1, len(sites))
        for url in ("https://pterclub.net/", "https://pterclub.com/", "https://pterclub.net/torrents.php"):
            with self.subTest(url=url):
                indexer = self.helper.get_indexer(url)
                self.assertEqual("pterclub", indexer.id)
                self.assertEqual(f"https://{urlsplit(url).hostname}", indexer.domain.rstrip("/"))
                self.assertTrue(indexer.builtin)

    def test_cookiecloud_discovers_new_domain_once(self):
        candidates = cookiecloud_site_candidates(self.helper.get_all_indexers(), {
            "pterclub.net": [
                {"domain": ".pterclub.net", "name": "uid", "value": "fixture"},
                {"domain": ".pterclub.net", "name": "pass", "value": "fixture"},
            ],
        }, [])
        self.assertEqual([{"name": "猫站", "signurl": "https://pterclub.net/"}], candidates)

    def test_cookiecloud_existing_new_or_legacy_site_prevents_duplicate(self):
        cookies = {
            "pterclub.net": [{"name": "uid", "value": "fixture"}],
            "pterclub.com": [{"name": "uid", "value": "fixture"}],
        }
        for url in ("https://pterclub.net/", "https://pterclub.com/"):
            with self.subTest(url=url):
                candidates = cookiecloud_site_candidates(
                    self.helper.get_all_indexers(), cookies, [{"name": "我的猫站", "signurl": url}]
                )
                self.assertEqual([], candidates)

    def test_cookiecloud_keeps_alias_candidates_under_same_site_name(self):
        candidates = cookiecloud_site_candidates(self.helper.get_all_indexers(), {
            "pterclub.net": [{"name": "uid", "value": "fixture"}],
            "pterclub.com": [{"name": "uid", "value": "fixture"}],
        }, [])
        self.assertEqual([
            {"name": "猫站", "signurl": "https://pterclub.net/"},
            {"name": "猫站", "signurl": "https://pterclub.com/"},
        ], candidates)

    @staticmethod
    def _torrent_page(tbody, staff, comment_link):
        staff_column = '<td class="rowfollow"><input type="checkbox"></td>' if staff else ""
        row = f"""
            <tr>
              {staff_column}
              <td class="rowfollow"><a href="?cat=401">Movie</a></td>
              <td class="rowfollow"><table class="torrentname"><tr><td class="embedded">
                <div><div><a href="details.php?id=123"><b>Demo Movie 2026 1080p</b></a></div>
                <div><span>Demo description</span></div></div>
                <a href="/download.php?id=123">Download</a><img class="pro_free" src="free.png">
              </td></tr></table></td>
              <td class="rowfollow"><a href="{comment_link}">1</a></td>
              <td class="rowfollow"><span title="2026-10-17 12:00:00">1 day</span></td>
              <td class="rowfollow">1 GB</td>
              <td class="rowfollow">8</td>
              <td class="rowfollow">2</td>
              <td class="rowfollow">10</td>
            </tr>
        """
        return PyQuery(f'<table class="torrents"><tbody>{row}</tbody></table>' if tbody
                       else f'<table class="torrents">{row}</table>')

    def test_search_and_relative_result_urls_keep_configured_domain(self):
        for url in ("https://pterclub.net/", "https://pterclub.com/"):
            with self.subTest(url=url):
                spider = TorrentSpider()
                spider.setparam(self.helper.get_indexer(url), keyword="Demo")
                requests = list(spider.start_requests())
                self.assertEqual(1, len(requests))
                self.assertEqual(urlsplit(url).hostname, urlsplit(requests[0].url).hostname)
                self.assertEqual("/torrents.php", urlsplit(requests[0].url).path)
                page = self._torrent_page(tbody=True, staff=False, comment_link="details.php?id=123&hit=1#startcomments")
                rows = list(page(spider.list["selector"]).items())
                self.assertEqual(1, len(rows))
                result = spider.Getinfo(rows[0])
                self.assertEqual(url + "details.php?id=123", result["page_url"])
                self.assertEqual(url + "download.php?id=123", result["enclosure"])

    def test_nexusphp_rows_support_both_table_layouts_and_staff_columns(self):
        indexer = self.helper.get_indexer("https://pterclub.net/")
        for tbody in (False, True):
            for staff in (False, True):
                for comment_link in ("comment.php?action=add&tid=123", "details.php?id=123#startcomments"):
                    with self.subTest(tbody=tbody, staff=staff, comment_link=comment_link):
                        spider = TorrentSpider()
                        spider.setparam(indexer)
                        page = self._torrent_page(tbody, staff, comment_link)
                        rows = list(page(spider.list["selector"]).items())
                        self.assertEqual(1, len(rows))
                        result = spider.Getinfo(rows[0])
                        self.assertEqual("Demo Movie 2026 1080p", result["title"])
                        self.assertEqual("电影", result["category"])
                        self.assertEqual("8", result["seeders"])
                        self.assertEqual("2", result["peers"])
                        self.assertEqual("10", result["grabs"])
                        self.assertEqual(1024 ** 3, result["size"])
                        self.assertEqual(0, result["downloadvolumefactor"])
                        self.assertEqual(2026, result["pubdate"].year)
                        self.assertEqual(17, result["pubdate"].day)

    def test_rss_promotion_rules_support_both_domains(self):
        page = etree.HTML('<h1 id="top"><b><font class="free">Free</font></b></h1>')
        for host in ("pterclub.net", "pterclub.com"):
            with self.subTest(host=host):
                rules = SiteConf.RSS_SITE_GRAP_CONF[host]
                self.assertTrue(any(page.xpath(xpath) for xpath in rules["FREE"]))
                self.assertEqual(SiteConf.RSS_SITE_GRAP_CONF["pterclub.com"], rules)

    def test_full_title_attribute_takes_precedence_over_truncated_text(self):
        page = self._torrent_page(tbody=True, staff=False, comment_link="details.php?id=123#startcomments")
        full_title = "Demo Movie 2026 2160p BluRay REMUX HEVC TrueHD Atmos 7.1-ReleaseGroup"
        title_link = page('table.torrentname a[href^="details.php?id="]')
        title_link.attr("title", full_title)
        title_link.text("Demo Movie 2026 2160p...")
        spider = TorrentSpider()
        spider.setparam(self.helper.get_indexer("https://pterclub.net/"))

        result = spider.Getinfo(next(page(spider.list["selector"]).items()))

        self.assertEqual(full_title, result["title"])

    def test_plain_text_dates_work_without_span_title_attribute(self):
        for date_html in ("2026-10-17 12:00:00", "2026-10-17<br>12:00:00"):
            with self.subTest(date_html=date_html):
                page = self._torrent_page(tbody=True, staff=True, comment_link="comment.php?action=add&tid=123")
                page("td:has(table.torrentname) + td + td").html(date_html)
                spider = TorrentSpider()
                spider.setparam(self.helper.get_indexer("https://pterclub.net/"))

                result = spider.Getinfo(next(page(spider.list["selector"]).items()))

                self.assertEqual("2026-10-17 12:00:00", result["pubdate"].strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    unittest.main()
