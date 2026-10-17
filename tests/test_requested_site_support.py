import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.helper import DbHelper, IndexerHelper
from app.sites import Sites
from web.actions.sites import SiteActions
from web.actions.download import DownloadActions


class RequestedSiteSupportTest(unittest.TestCase):
    def test_cookiecloud_imports_requested_sites_and_reuses_them_on_next_sync(self):
        db = DbHelper()
        catalog = IndexerHelper()
        urls = ("https://playlet.cc/", "https://pterclub.net/", "https://kp.m-team.cc/")
        names = []
        for url in urls:
            indexer = catalog.get_indexer(url)
            self.assertIsNotNone(indexer, url)
            names.append(indexer.name)
        self.assertEqual(3, len(set(names)))

        def cleanup():
            for name in names:
                for record in db.get_site_by_name(name):
                    db.delete_config_site(record.id)
        self.addCleanup(cleanup)
        self.assertTrue(all(not db.get_site_by_name(name) for name in names))
        with patch("app.sites.sites.Message"):
            sites = Sites.__wrapped__()
        payload = {
            host: [{"domain": "." + host, "name": "session", "value": "fixture-session", "path": "/"}]
            for host in ("playlet.cc", "pterclub.net", "m-team.cc")
        }
        with patch("web.actions.sites.SystemConfig") as config, \
                patch("web.actions.sites.Sites", return_value=sites), \
                patch("app.sites.sites.Message"), \
                patch("web.actions.sites.CookieCloudHelper") as cloud:
            config.return_value.get_system_config.return_value = {
                "server": "https://cloud.example", "key": "fixture-key", "password": "fixture-password", "interval": 180}
            cloud.return_value.download_data.return_value = (payload, "")
            actions = SiteActions(db)

            result = actions.cookiecloud_sync({})
            self.assertEqual(0, result["code"])
            self.assertIn("新增 3 个站点", result["msg"])
            for name in names:
                record = db.get_site_by_name(name)[0]
                self.assertEqual("session=fixture-session", record.cookie)
                self.assertEqual("", record.include)
                self.assertIsNotNone(catalog.get_indexer(record.signurl))

            result = actions.cookiecloud_sync({})
            self.assertEqual(0, result["code"])
            self.assertIn("更新 3 个站点，新增 0 个站点", result["msg"])
            self.assertTrue(all(len(db.get_site_by_name(name)) == 1 for name in names))


class MTeamWebDownloadTest(unittest.TestCase):
    def setUp(self):
        self.saved = {"name": "馒头", "signurl": "https://kp.m-team.cc/", "apikey": "fixture-api-key"}
        self.enterContext(patch("web.actions.validation.Sites")).return_value.get_sites.return_value = [self.saved]
        self.enterContext(patch("web.actions.download.Sites")).return_value.get_sites.return_value = [self.saved]
        self.downloader = self.enterContext(patch("web.actions.download.Downloader")).return_value
        self.downloader.download.return_value = (True, "")
        self.enterContext(patch("web.actions.download.Message"))
        self.enterContext(patch("web.actions.download.current_user", SimpleNamespace(username="fixture")))
        self.media = self.enterContext(patch("web.actions.download.Media")).return_value.get_media_info.return_value

    def test_resource_download_rebuilds_request_from_saved_site_and_detail_id(self):
        encoded_request = base64.b64encode(json.dumps({
            "method": "get", "header": {"Authorization": "{apikey}"}, "params": {"id": "999"}
        }).encode()).decode()
        for remote_url in ("https://attacker.example/api", "https://attacker.example/api]"):
            with self.subTest(remote_url=remote_url):
                self.downloader.download.reset_mock()
                result = DownloadActions.download_link({
                    "site": "馒头", "title": "Fixture Movie", "page_url": "https://kp.m-team.cc/detail/123",
                    "enclosure": f"[{encoded_request}]{remote_url}", "dl_dir": "/downloads",
                })

                self.assertEqual(0, result["code"])
                self.downloader.download.assert_called_once()
                enclosure = self.media.enclosure
                self.assertTrue(enclosure.endswith("https://api.m-team.cc/api/torrent/genDlToken"))
                self.assertNotIn("attacker", enclosure)
                self.assertNotIn("fixture-api-key", enclosure)
                encoded = enclosure[1:enclosure.index("]")]
                descriptor = json.loads(base64.b64decode(encoded))
                self.assertEqual({"id": "123"}, descriptor["params"])
                self.assertEqual("{apikey}", descriptor["header"]["x-api-key"])
                self.assertNotIn("Authorization", descriptor["header"])
                self.assertEqual("post", descriptor["method"])
                self.assertFalse(descriptor["cookie"])

    def test_dynamic_download_rejects_foreign_site_invalid_detail_and_missing_key(self):
        for site, url, key in (
                ("馒头", "https://attacker.example/detail/123", "fixture-key"),
                ("unknown", "https://kp.m-team.cc/detail/123", "fixture-key"),
                ("馒头", "https://kp.m-team.cc/admin/123", "fixture-key"),
                ("馒头", "https://kp.m-team.cc/detail/abc", "fixture-key"),
                ("馒头", "https://kp.m-team.cc/detail/123", "")):
            with self.subTest(site=site, url=url, configured=bool(key)):
                self.saved["apikey"] = key
                result = DownloadActions.download_link({
                    "site": site, "title": "Fixture Movie", "page_url": url,
                    "enclosure": "[e30=]https://api.m-team.cc/api/torrent/genDlToken",
                })
                self.assertEqual(-1, result["code"])
        self.downloader.download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
