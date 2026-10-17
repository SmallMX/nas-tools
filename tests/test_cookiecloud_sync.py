import copy
import json
import unittest
from unittest.mock import Mock, call, patch

from web.actions.sites import SiteActions, _cookiecloud_sync_lock


class CookieCloudSyncTest(unittest.TestCase):
    def setUp(self):
        self.config = self.enterContext(patch("web.actions.sites.SystemConfig")).return_value
        self.saved = {"server": "https://cloud.example", "key": "saved-key", "password": "saved-password"}
        self.config.get_system_config.return_value = self.saved
        self.config.set_system_config.return_value = True
        self.scheduler_instance = self.enterContext(patch("web.actions.sites.get_singleton_instance", return_value=None))
        self.indexers = self.enterContext(patch("web.actions.sites.IndexerHelper")).return_value
        self.indexers.get_all_indexers.return_value = []
        self.sites = self.enterContext(patch("web.actions.sites.Sites")).return_value
        self.sites.get_sites.return_value = [{"id": 1, "signurl": "https://pt.example.org/"}]
        self.brush = self.enterContext(patch("web.actions.sites.BrushTask")).return_value
        self.cloud = self.enterContext(patch("web.actions.sites.CookieCloudHelper"))
        self.cloud.return_value.download_data.return_value = ({
            "example.org": [{"domain": ".example.org", "name": "session", "value": "parent"}]
        }, "")
        self.db = Mock()
        self.db.update_site_cookie_ua.return_value = True
        self.db.get_site_by_name.return_value = []
        self.db.insert_config_site.return_value = True
        self.actions = SiteActions(self.db)

    def test_sync_uses_saved_credentials_without_rewriting_them(self):
        for data in ({}, None, {"key": "", "password": ""}):
            with self.subTest(data=data):
                result = self.actions.cookiecloud_sync(data)
                self.assertEqual(0, result["code"])
                self.cloud.assert_called_with(**self.saved)
        self.config.set_system_config.assert_not_called()

    def test_save_preserves_blank_secrets_without_downloading_or_leaking_them(self):
        original = copy.deepcopy(self.saved)
        result = self.actions.cookiecloud_save({"server": "https://cloud.example/", "key": "", "password": ""})
        self.assertEqual(0, result["code"])
        self.config.set_system_config.assert_called_once_with(key="CookieCloud", value={**original, "interval": 0})
        self.assertEqual(original, self.saved)
        self.assertNotIn("saved-key", str(result))
        self.assertNotIn("saved-password", str(result))
        self.cloud.assert_not_called()

    def test_changed_server_requires_new_secrets_for_save_and_sync(self):
        for action in (self.actions.cookiecloud_save, self.actions.cookiecloud_sync):
            for params in ({}, {"key": "new-key"}, {"password": "new-password"}):
                with self.subTest(action=action.__name__, params=params):
                    result = action({"server": "https://other.example", **params})
                    self.assertEqual(1, result["code"])
        self.config.set_system_config.assert_not_called()
        self.cloud.assert_not_called()
        self.assertEqual(0, self.actions.cookiecloud_save({
            "server": "https://other.example", "key": "new-key", "password": "new-password"})["code"])

    def test_missing_or_invalid_config_never_fetches_or_saves(self):
        self.config.get_system_config.return_value = {}
        for data in ({}, [], {"server": ""}, {"server": "file:///tmp/data"},
                     {"server": "https://cloud.example", "key": ["invalid"], "password": "x"}):
            with self.subTest(data=data):
                self.assertEqual(1, self.actions.cookiecloud_sync(data)["code"])
        self.cloud.assert_not_called()
        self.config.set_system_config.assert_not_called()

    def test_config_save_failure_stops_sync(self):
        self.config.set_system_config.return_value = False
        result = self.actions.cookiecloud_sync({"password": "replacement"})
        self.assertEqual(1, result["code"])
        self.cloud.assert_not_called()

    def test_interval_save_preserves_credentials_and_refreshes_running_schedule(self):
        scheduler = Mock()
        scheduler.reload_cookiecloud_config.return_value = True
        self.scheduler_instance.return_value = scheduler
        for interval in (0, "60", 10080):
            with self.subTest(interval=interval):
                result = self.actions.cookiecloud_save({"interval": interval})
                self.assertEqual(0, result["code"])
                self.config.set_system_config.assert_called_with(
                    key="CookieCloud", value={**self.saved, "interval": int(interval)})
        self.assertEqual(3, scheduler.reload_cookiecloud_config.call_count)
        self.cloud.assert_not_called()

    def test_invalid_intervals_never_save_or_refresh_schedule(self):
        for interval in (-1, 10081, True, 1.5, "1.5", "", "bad", None, [], {}):
            with self.subTest(interval=interval):
                result = self.actions.cookiecloud_save({"interval": interval})
                self.assertEqual(1, result["code"])
                self.assertIn("整数分钟", result["msg"])
        self.config.set_system_config.assert_not_called()
        self.scheduler_instance.assert_not_called()

    def test_failed_schedule_reload_reports_saved_config_without_claiming_success(self):
        scheduler = Mock()
        scheduler.reload_cookiecloud_config.return_value = False
        self.scheduler_instance.return_value = scheduler
        result = self.actions.cookiecloud_save({"interval": 60})
        self.assertEqual(1, result["code"])
        self.assertIn("配置已保存", result["msg"])
        self.assertIn("计划更新失败", result["msg"])

    def test_overlapping_sync_is_rejected_and_errors_release_the_lock(self):
        with _cookiecloud_sync_lock:
            result = self.actions.cookiecloud_sync({})
        self.assertIn("正在进行", result["msg"])
        self.cloud.assert_not_called()
        self.cloud.return_value.download_data.side_effect = RuntimeError("fixture")
        with self.assertRaises(RuntimeError):
            self.actions.cookiecloud_sync({})
        self.assertFalse(_cookiecloud_sync_lock.locked())

    def test_all_sites_receive_merged_domain_cookies_once(self):
        self.sites.get_sites.return_value = [
            {"id": 1, "signurl": "https://PT.example.org:443/"},
            {"id": 2, "rssurl": "https://pt.example.org/rss"},
            {"id": 3, "signurl": "https://other.example.org/"},
            {"id": 4, "signurl": "https://notexample.org/"},
        ]
        self.cloud.return_value.download_data.return_value = ({
            "browser-bucket": [
                {"domain": ".example.org", "name": "session", "value": "parent"},
                {"domain": ".example.org", "name": "shared", "value": "yes"},
                {"domain": "pt.example.org", "hostOnly": True, "name": "session", "value": "specific"},
                {"domain": "pt.example.org", "name": "local", "value": "only-pt"},
            ],
            "pt.example.org": [{"name": "legacy", "value": "fallback"}],
        }, "")
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(0, result["code"])
        self.assertIn("3 个站点", result["msg"])
        self.assertEqual([
            call(tid=1, cookie="session=specific; shared=yes; local=only-pt; legacy=fallback"),
            call(tid=2, cookie="session=specific; shared=yes; local=only-pt; legacy=fallback"),
            call(tid=3, cookie="session=parent; shared=yes"),
        ], self.db.update_site_cookie_ua.call_args_list)
        self.sites.init_config.assert_called_once_with()
        self.brush.init_config.assert_not_called()

    def test_host_only_parent_and_sibling_cookies_cannot_overwrite_site(self):
        self.cloud.return_value.download_data.return_value = ({"example.org": [
            {"domain": "example.org", "hostOnly": True, "name": "session", "value": "parent-only"},
            {"domain": "other.example.org", "name": "session", "value": "sibling"},
        ]}, "")
        self.assertEqual(1, self.actions.cookiecloud_sync({})["code"])
        self.db.update_site_cookie_ua.assert_not_called()

    def test_cookie_paths_select_the_correct_session_for_each_site(self):
        self.sites.get_sites.return_value = [
            {"id": 1, "signurl": "https://pt.example.org/"},
            {"id": 2, "signurl": "https://pt.example.org/forum/index.php"},
            {"id": 3, "signurl": "https://pt.example.org/forums"},
        ]
        self.cloud.return_value.download_data.return_value = ({"pt.example.org": [
            {"name": "PHPSESSID", "value": "forum-session", "path": "/forum"},
            {"name": "PHPSESSID", "value": "root-session", "path": "/"},
        ]}, "")
        self.assertEqual(0, self.actions.cookiecloud_sync({})["code"])
        self.assertEqual([
            call(tid=1, cookie="PHPSESSID=root-session"),
            call(tid=2, cookie="PHPSESSID=forum-session"),
            call(tid=3, cookie="PHPSESSID=root-session"),
        ], self.db.update_site_cookie_ua.call_args_list)

    def test_primary_address_is_preferred_and_rss_is_a_separate_fallback(self):
        self.sites.get_sites.return_value = [
            {"id": 1, "signurl": "https://primary.example/", "rssurl": "https://rss.example/"},
            {"id": 2, "signurl": "https://missing.example/", "rssurl": "https://rss.example/"},
        ]
        self.cloud.return_value.download_data.return_value = ({
            "primary.example": [{"name": "session", "value": "primary"}],
            "rss.example": [{"name": "session", "value": "rss"}, {"name": "rss_only", "value": "1"}],
        }, "")
        self.assertEqual(0, self.actions.cookiecloud_sync({})["code"])
        self.assertEqual([call(tid=1, cookie="session=primary"), call(tid=2, cookie="session=rss; rss_only=1")],
                         self.db.update_site_cookie_ua.call_args_list)

    def test_expired_invalid_extension_and_cf_only_cookies_do_not_replace_login(self):
        self.cloud.return_value.download_data.return_value = ({"example.org": [
            {"name": "session", "value": "expired", "expirationDate": 1},
            {"name": "CookieAutoDeleteBrowsingDataCleanup", "value": "1"},
            {"name": "cf_clearance", "value": "clearance"},
            {"name": "invalid", "value": "value\r\nInjected: yes"},
            {"name": "missing-value"}, None,
        ]}, "")
        self.assertEqual(1, self.actions.cookiecloud_sync({})["code"])
        self.db.update_site_cookie_ua.assert_not_called()

    def test_write_failure_is_reported_and_successful_updates_are_reloaded(self):
        self.sites.get_sites.return_value *= 2
        self.db.update_site_cookie_ua.side_effect = [True, False]
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(1, result["code"])
        self.assertIn("已更新 1 个站点，新增 0 个站点，1 个站点保存失败", result["msg"])
        self.sites.init_config.assert_called_once_with()
        self.brush.init_config.assert_not_called()

    def test_empty_sites_and_empty_cloud_data_have_actionable_errors(self):
        self.sites.get_sites.return_value = []
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(1, result["code"])
        self.assertIn("内置站点库未收录", result["msg"])
        self.cloud.return_value.download_data.assert_called_once_with()
        self.sites.get_sites.return_value = [{"id": 1, "signurl": "https://pt.example.org/"}]
        self.cloud.return_value.download_data.return_value = ({}, "")
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(1, result["code"])
        self.assertTrue(result["msg"])

    def test_first_sync_adds_known_sites_and_repeat_sync_updates_without_duplicates(self):
        self.sites.get_sites.return_value = []
        self.indexers.get_all_indexers.return_value = [
            {"id": "fixture", "name": "Fixture", "domain": "https://pt.example.org/"}
        ]
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(0, result["code"])
        self.assertIn("更新 0 个站点，新增 1 个站点", result["msg"])
        values = self.db.insert_config_site.call_args.kwargs
        self.assertEqual("Fixture", values["name"])
        self.assertEqual("https://pt.example.org/", values["signurl"])
        self.assertEqual("session=parent", values["cookie"])
        self.assertEqual("", values["rssurl"])
        self.assertEqual("", values["rss_uses"])
        self.sites.init_config.assert_called_once_with()
        self.db.update_site_cookie_ua.assert_not_called()

        self.sites.get_sites.return_value = [{"id": 9, **values}]
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(0, result["code"])
        self.assertIn("更新 1 个站点，新增 0 个站点", result["msg"])
        self.db.insert_config_site.assert_called_once()
        self.db.update_site_cookie_ua.assert_called_once_with(tid=9, cookie="session=parent")

    def test_known_alias_is_imported_but_unknown_domains_and_cf_only_are_skipped(self):
        self.sites.get_sites.return_value = []
        self.indexers.get_all_indexers.return_value = [
            {"id": "fixture", "name": "Fixture", "domain": "https://primary.example/",
             "aliases": ["https://alias.example/"]},
            {"id": "cf", "name": "CF", "domain": "https://cf.example/"},
        ]
        self.cloud.return_value.download_data.return_value = ({
            "alias.example": [{"name": "session", "value": "alias"}],
            "unknown.example": [{"name": "session", "value": "unknown"}],
            "cf.example": [{"name": "cf_clearance", "value": "cf"}],
        }, "")
        self.assertEqual(0, self.actions.cookiecloud_sync({})["code"])
        self.db.insert_config_site.assert_called_once()
        self.assertEqual("https://alias.example/", self.db.insert_config_site.call_args.kwargs["signurl"])

    def test_failed_insert_is_reported_without_reloading_sites(self):
        self.sites.get_sites.return_value = []
        self.indexers.get_all_indexers.return_value = [
            {"id": "fixture", "name": "Fixture", "domain": "https://pt.example.org/"}
        ]
        self.db.insert_config_site.return_value = False
        result = self.actions.cookiecloud_sync({})
        self.assertEqual(1, result["code"])
        self.assertIn("新增 0 个站点，1 个站点保存失败", result["msg"])
        self.sites.init_config.assert_not_called()


class CookieCloudPersistenceTest(unittest.TestCase):
    def test_initial_sync_creates_a_real_site_and_next_sync_reuses_it(self):
        from requests import Response
        from app.helper import DbHelper
        from app.sites import Sites

        db = DbHelper()
        name = "CookieCloud discovery persistence fixture"
        def cleanup():
            for site in db.get_site_by_name(name):
                db.delete_config_site(site.id)
        self.addCleanup(cleanup)
        with patch("app.sites.sites.Message"):
            sites = Sites.__wrapped__()
        actions = SiteActions(db)
        with patch("web.actions.sites.SystemConfig") as config, \
                patch("web.actions.sites.IndexerHelper") as indexers, \
                patch("web.actions.sites.Sites", return_value=sites), \
                patch("app.sites.sites.Message"), \
                patch("app.helper.cookiecloud_helper.RequestUtils") as request:
            config.return_value.get_system_config.return_value = {
                "server": "https://cloud.example", "key": "fixture-key", "password": "fixture-password", "interval": 0}
            indexers.return_value.get_all_indexers.return_value = [
                {"id": "discovery-fixture", "name": name, "domain": "https://pt.discovery.example/"}]
            response = Response()
            response.status_code = 200
            response._content = json.dumps({"cookie_data": {"discovery.example": [
                {"domain": ".discovery.example", "name": "session", "value": "discovered", "path": "/"}
            ]}}).encode()
            response._content_consumed = True
            request.return_value.get_res.return_value = response
            self.assertIn("新增 1 个站点", actions.cookiecloud_sync({})["msg"])
            records = db.get_site_by_name(name)
            self.assertEqual(1, len(records))
            self.assertEqual("session=discovered", records[0].cookie)
            self.assertEqual("https://pt.discovery.example/", records[0].signurl)
            self.assertEqual("", records[0].include)
            self.assertEqual("session=discovered", sites.get_sites(siteid=records[0].id)["cookie"])
            self.assertIn("更新 1 个站点，新增 0 个站点", actions.cookiecloud_sync({})["msg"])
            self.assertEqual(1, len(db.get_site_by_name(name)))

    def test_saved_config_reload_and_sync_update_the_database_and_site_cache(self):
        from requests import Response
        from app.conf import SystemConfig
        from app.helper import DbHelper
        from app.sites import Sites

        # tests.__init__ provides an isolated temporary database for the whole suite.
        config_class = SystemConfig.__closure__[0].cell_contents
        old_config = config_class().get_system_config("CookieCloud")
        self.addCleanup(lambda: config_class().set_system_config("CookieCloud", old_config))
        db = DbHelper()
        self.assertTrue(db.insert_config_site(
            name="CookieCloud persistence fixture", site_pri=1, rssurl="", signurl="https://pt.fixture.example/",
            cookie="old-session", note='{"ua":"fixture-agent"}', rss_uses="T"))
        site_id = db.get_site_by_name("CookieCloud persistence fixture")[0].id
        self.addCleanup(db.delete_config_site, site_id)
        with patch("app.sites.sites.Message"):
            sites = Sites.__closure__[0].cell_contents()
        config = {"server": "https://cloud.example", "key": "fixture-key", "password": "fixture-password", "interval": 0}
        actions = SiteActions(db)
        with patch("web.actions.sites.SystemConfig", side_effect=config_class), \
                patch("web.actions.sites.get_singleton_instance", return_value=None), \
                patch("web.actions.sites.Sites", return_value=sites), \
                patch("app.sites.sites.Message"), \
                patch("app.helper.cookiecloud_helper.RequestUtils") as request:
            self.assertEqual(0, actions.cookiecloud_save(config)["code"])
            self.assertEqual(config, config_class().get_system_config("CookieCloud"))
            response = Response()
            response.status_code = 200
            response._content = json.dumps({"cookie_data": {"fixture.example": [
                {"domain": ".fixture.example", "name": "session", "value": "new-session", "path": "/"}
            ]}}).encode()
            response._content_consumed = True
            request.return_value.get_res.return_value = response
            self.assertEqual(0, actions.cookiecloud_sync({})["code"])
        self.assertEqual("session=new-session", db.get_site_by_id(site_id)[0].cookie)
        self.assertEqual("session=new-session", sites.get_sites(siteid=site_id)["cookie"])
        self.assertEqual("fixture-agent", sites.get_sites(siteid=site_id)["ua"])


if __name__ == "__main__":
    unittest.main()
