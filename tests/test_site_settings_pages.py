import copy
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from flask import render_template

from app.conf import ModuleConf
from app.utils.types import DownloaderType
from web.main import App


class SiteSettingsPagesTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(App.config, {"TESTING": True}))
        self.client = App.test_client()
        self.user = SimpleNamespace(id=1, username="page-user", pris="站点管理,系统设置,服务", is_authenticated=True)
        self.enterContext(patch("flask_login.utils._get_user", return_value=self.user))
        self.enterContext(patch("web.backend.user.User.get_user", return_value=self.user))
        # 构造器全部替换，渲染和全局鉴权保持真实，避免页面初始化业务单例或访问外部服务。
        self.site = {
            name: self.enterContext(patch(f"web.routes.site_pages.{name}"))
            for name in ("Sites", "Downloader", "ChromeHelper", "SystemConfig", "Config", "WebAction",
                         "Indexer", "SiteUserInfo", "BrushTask")
        }
        self.settings = {
            name: self.enterContext(patch(f"web.routes.settings_pages.{name}"))
            for name in ("BrushTask", "Config", "Downloader", "Message", "MetaHelper", "SystemConfig", "WebAction")
        }
        self.site["Sites"].return_value.get_sites.return_value = []
        self.site["Downloader"].return_value.get_download_setting.return_value = {"7": {"name": "日常下载"}}
        self.site["ChromeHelper"].return_value.get_status.return_value = True
        self.site["Config"].return_value.get_config.return_value = {"ocr_server": "https://ocr.example"}

    def _render(self, module, path, template, method="GET", actual=False):
        kwargs = {"wraps": render_template} if actual else {"return_value": "页面已渲染"}
        with patch(f"web.routes.{module}.render_template", **kwargs) as renderer:
            response = self.client.open(path, method=method)
        self.assertEqual(200, response.status_code)
        renderer.assert_called_once()
        self.assertEqual((template,), renderer.call_args.args)
        return renderer.call_args.kwargs, response.get_data(as_text=True)

    def test_site_user_does_not_read_system_credentials(self):
        self.user.pris = "站点管理"

        context, html = self._render("site_pages", "/site", "site/site.html", actual=True)

        self.site["SystemConfig"].assert_not_called()
        self.assertFalse(context["CanSystemSettings"])
        self.assertEqual({}, context["CookieCloudCfg"])
        self.assertEqual({}, context["CookieUserInfoCfg"])
        self.assertEqual({"7": "日常下载"}, context["DownloadSettings"])
        self.assertTrue(context["ChromeOk"])
        self.assertTrue(context["OcrServerConfigured"])
        self.assertNotIn('id="modal-cookiecloud"', html)
        self.assertNotIn('data-nt-click="site-cookie"', html)

    def test_site_admin_context_and_html_never_refill_saved_login_secrets(self):
        self.user.id, self.user.pris = 0, ""
        values = {
            "CookieCloud": {"server": "https://cloud.example", "key": "cloud-key-secret", "password": "cloud-password-secret"},
            "CookieUserInfo": {"username": "saved-user", "password": "site-password-secret", "two_step_code": "two-step-secret"},
        }
        original = copy.deepcopy(values)
        config = self.site["SystemConfig"].return_value
        config.get_system_config.side_effect = values.get

        context, html = self._render("site_pages", "/site", "site/site.html", method="POST", actual=True)

        self.assertTrue(context["CanSystemSettings"])
        self.assertEqual({"server": "https://cloud.example", "key": "", "password": ""}, context["CookieCloudCfg"])
        self.assertEqual({"username": "saved-user", "password": "", "two_step_code": ""}, context["CookieUserInfoCfg"])
        self.assertEqual([call("CookieCloud"), call("CookieUserInfo")], config.get_system_config.call_args_list)
        self.assertEqual(original, values)
        self.assertIn('id="modal-cookiecloud"', html)
        self.assertIn("https://cloud.example", html)
        self.assertIn("saved-user", html)
        for secret in ("cloud-key-secret", "cloud-password-secret", "site-password-secret", "two-step-secret"):
            self.assertNotIn(secret, html)

    def test_site_ocr_status_only_accepts_nonempty_string(self):
        self.user.pris = "站点管理"
        for value, expected in ((None, False), (123, False), (" \t", False), (" https://ocr.example ", True)):
            with self.subTest(value=value):
                self.site["Config"].return_value.get_config.return_value = {"ocr_server": value}
                context, _ = self._render("site_pages", "/site", "site/site.html")
                self.assertIs(expected, context["OcrServerConfigured"])

    def test_sitelist_keeps_builtin_private_indexer_selection(self):
        sites = [{"id": 9, "name": "站点"}]
        indexer = self.site["Indexer"].return_value
        indexer.get_builtin_indexers.return_value = sites

        context, _ = self._render("site_pages", "/sitelist", "site/sitelist.html")

        indexer.get_builtin_indexers.assert_called_once_with(check=False, public=False)
        self.assertIs(sites, context["Sites"])
        self.assertEqual(1, context["Count"])

    def test_resources_preserves_query_types_defaults_and_download_visibility(self):
        action = self.site["WebAction"].return_value
        entries = [{"title": "fixture"}]
        cases = [
            ("/resources?site=9&title=Example&page=2&keyword=hello", "站点管理,下载管理", entries,
             {"id": "9", "page": "2", "keyword": "hello"}, 2, True),
            ("/resources?site=9&title=Example", "站点管理", None,
             {"id": "9", "page": 0, "keyword": None}, 0, False),
        ]
        for url, permissions, results, params, current_page, can_download in cases:
            with self.subTest(url=url):
                self.user.pris = permissions
                action.action.reset_mock()
                action.action.return_value = {"data": results}

                context, _ = self._render("site_pages", url, "site/resources.html", method="POST")

                action.action.assert_called_once_with("list_site_resources", params)
                self.assertEqual(results or [], context["Results"])
                self.assertEqual(len(results or []), context["TotalCount"])
                self.assertEqual("9", context["SiteId"])
                self.assertEqual("Example", context["Title"])
                self.assertEqual(params["keyword"], context["KeyWord"])
                self.assertIs(can_download, context["CanDownload"])
                self.assertEqual(current_page, context["CurrentPage"])
                self.assertIs(type(context["CurrentPage"]), int)
                self.assertEqual(list(range(10)), list(context["PageRange"]))
                self.assertEqual(10, context["TotalPage"])

    def test_statistics_preserves_refresh_parameters_totals_errors_and_history_window(self):
        data = {
            "A": {"upload": "100", "download": 25, "ratio": "4.04", "seeding": "2", "seeding_size": "90"},
            "empty": {},
            "offline": {"upload": 0, "download": 0, "ratio": 0, "err_msg": "离线"},
            "invalid": {"upload": "N/A", "download": 12, "ratio": 1, "err_msg": "无效数据"},
            "B": {"upload": 60, "download": "40", "ratio": 1.54, "seeding": 3, "seeding_size": 110},
        }
        original = copy.deepcopy(data)
        info = self.site["SiteUserInfo"].return_value
        info.get_pt_date.return_value = data
        info.get_pt_site_statistics_history.return_value = (11, 12, [], [], [])
        statistics = [{"site": "A", "upload": 100}]
        action = self.site["WebAction"].return_value
        action.get_site_user_statistics.return_value = {"data": statistics}

        context, _ = self._render("site_pages", "/statistics?refresh_site=A&refresh_site=B&refresh_force=0", "site/statistics.html")

        # 旧接口将任何非空 refresh_force 当作真；不在模块搬迁时改变请求语义。
        info.get_pt_date.assert_called_once_with(specify_sites=["A", "B"], force=True)
        info.get_pt_site_statistics_history.assert_called_once_with(days=2)
        action.get_site_user_statistics.assert_called_once_with({"encoding": "DICT"})
        self.assertEqual((11, 12, 160, 65, 5, 200), tuple(context[key] for key in (
            "CurrentUpload", "CurrentDownload", "TotalUpload", "TotalDownload", "TotalSeeding", "TotalSeedingSize")))
        self.assertEqual(["A", "B"], context["SiteNames"])
        self.assertEqual([100, 60], context["SiteUploads"])
        self.assertEqual([25, 40], context["SiteDownloads"])
        self.assertEqual([4.0, 1.5], context["SiteRatios"])
        self.assertEqual({"A": "", "offline": "离线", "invalid": "无效数据", "B": ""}, context["SiteErr"])
        self.assertIs(statistics, context["SiteUserStatistics"])
        self.assertEqual(original, data)

    def test_statistics_default_request_keeps_cached_refresh_and_empty_result_shape(self):
        info = self.site["SiteUserInfo"].return_value
        info.get_pt_date.return_value = None
        info.get_pt_site_statistics_history.return_value = (0, 0, [], [], [])
        self.site["WebAction"].return_value.get_site_user_statistics.return_value = {"data": []}

        context, _ = self._render("site_pages", "/statistics", "site/statistics.html", method="POST")

        info.get_pt_date.assert_called_once_with(specify_sites=[], force=False)
        self.assertEqual([], context["SiteNames"])
        self.assertEqual({}, context["SiteErr"])
        self.assertEqual(0, context["TotalUpload"])
        self.assertEqual(0, context["TotalDownload"])

    def test_denied_statistics_request_cannot_trigger_a_refresh(self):
        self.user.pris = "系统设置"

        response = self.client.get("/statistics?refresh_force=1")

        self.assertEqual(403, response.status_code)
        self.site["SiteUserInfo"].assert_not_called()
        self.site["WebAction"].assert_not_called()

    def test_brush_page_keeps_private_fields_out_of_render_context_without_mutation(self):
        self.user.pris = "服务"
        sites = [{"id": 1, "name": "站点"}]
        downloaders = [{"id": 3, "name": "下载器", "password": "downloader-password", "save_dir": "/downloads"}]
        tasks = [{"id": 2, "name": "刷流", "site": "站点", "rss_rule": {}, "cookie": "private-cookie",
                  "rssurl": "https://tracker.example/rss?passkey=private", "ua": "private-ua"}]
        original = copy.deepcopy((downloaders, tasks))
        self.site["Sites"].return_value.get_sites.return_value = sites
        brush = self.site["BrushTask"].return_value
        brush.get_downloader_info.return_value = downloaders
        brush.get_brushtask_info.return_value = tasks

        context, _ = self._render("site_pages", "/brushtask", "site/brushtask.html")

        self.site["Sites"].return_value.get_sites.assert_called_once_with(brush=True)
        self.assertIs(sites, context["Sites"])
        self.assertEqual([{"id": 3, "name": "下载器", "save_dir": "/downloads"}], context["Downloaders"])
        self.assertEqual([{"id": 2, "name": "刷流", "site": "站点", "rss_rule": {}}], context["Tasks"])
        self.assertEqual(1, context["Count"])
        self.assertEqual(original, (downloaders, tasks))

    def test_service_cards_follow_both_independent_permissions_and_admin(self):
        cases = [
            (1, "服务", ["nametest"], False),
            (1, "系统设置", ["nettest", "backup"], True),
            (1, "服务,系统设置", ["nametest", "nettest", "backup"], True),
            (0, "", ["nametest", "nettest", "backup"], True),
        ]
        for user_id, permissions, card_ids, can_settings in cases:
            with self.subTest(permissions=permissions, user_id=user_id):
                self.user.id, self.user.pris = user_id, permissions
                context, html = self._render("settings_pages", "/service", "service.html", actual=True)
                self.assertEqual(card_ids, [item["id"] for item in context["SchedulerTasks"]])
                self.assertEqual(len(card_ids), context["Count"])
                self.assertIs(can_settings, context["CanSystemSettings"])
                self.assertEqual(ModuleConf.NETTEST_TARGETS, context["NettestTargets"])
                for card_id in ("nametest", "nettest", "backup"):
                    self.assertEqual(card_id in card_ids, f'data-service-id="{card_id}"' in html)
                self.assertEqual(can_settings, 'id="modal-nettest"' in html)
                self.assertEqual(can_settings, 'id="modal-backup"' in html)

    def test_basic_setting_sections_mask_copies_and_only_system_loads_custom_script(self):
        self.user.pris = "系统设置"
        config = {
            "app": {"proxies": {"http": "http://proxy.example:8080"}, "login_password": "admin-secret", "rmt_tmdbkey": "tmdb-secret"},
            "security": {"api_key": "api-secret", "flask_secret_key": "session-secret"},
            "qbittorrent": {"qbpassword": "qb-secret"},
            "transmission": {"trpassword": "tr-secret"},
        }
        original = copy.deepcopy(config)
        self.settings["Config"].return_value.get_config.return_value = config
        scripts = {"css": "body{}", "javascript": ""}
        self.settings["SystemConfig"].return_value.get_system_config.return_value = scripts
        cases = [
            ("basic", "system", "基础设置"), ("media_setting", "media", "媒体设置"),
            ("service_setting", "service", "服务设置"), ("security_setting", "security", "安全设置"),
            ("laboratory_setting", "laboratory", "实验室"),
        ]
        for route, section, title in cases:
            with self.subTest(route=route):
                self.settings["SystemConfig"].reset_mock()
                context, _ = self._render("settings_pages", "/" + route, "setting/basic.html", method="POST")
                self.assertEqual(section, context["SettingSection"])
                self.assertEqual(title, context["SettingTitle"])
                for node, key in (("app", "login_password"), ("app", "rmt_tmdbkey"), ("security", "api_key"),
                                  ("security", "flask_secret_key"), ("qbittorrent", "qbpassword"), ("transmission", "trpassword")):
                    self.assertEqual("******", context["Config"][node][key])
                self.assertIsNot(config, context["Config"])
                if section == "system":
                    self.assertEqual("proxy.example:8080", context["Proxy"])
                    self.assertIs(scripts, context["CustomScriptCfg"])
                    self.settings["SystemConfig"].return_value.get_system_config.assert_called_once_with("CustomScript")
                else:
                    self.assertNotIn("Proxy", context)
                    self.assertNotIn("CustomScriptCfg", context)
                    self.settings["SystemConfig"].assert_not_called()
                self.assertEqual(original, config)

    def test_downloader_page_preserves_configuration_contract(self):
        self.user.pris = "系统设置"
        config = {"pt": {"pt_client": "qbittorrent"}, "qbittorrent": {"qbhost": "downloader.example"}}
        self.settings["Config"].return_value.get_config.return_value = config

        context, _ = self._render("settings_pages", "/downloader", "setting/downloader.html")

        self.assertIs(config, context["Config"])
        self.assertIs(ModuleConf.DOWNLOADER_CONF, context["DownloaderConf"])
        self.settings["Config"].return_value.get_config.assert_called_once_with()

    def test_download_settings_keep_default_and_enum_in_context(self):
        entries = {4: {"id": 4, "name": "默认下载"}, 7: {"id": 7, "name": "另一设置"}}
        downloader = self.settings["Downloader"].return_value
        downloader.get_download_setting.return_value = entries
        downloader.get_default_download_setting.return_value = 4

        context, _ = self._render("settings_pages", "/download_setting", "setting/download_setting.html")

        self.assertEqual(2, context["Count"])
        self.assertIs(entries, context["DownloadSetting"])
        self.assertEqual(4, context["DefaultDownloadSetting"])
        self.assertIs(DownloaderType, context["DownloaderTypes"])

    def test_notification_keeps_ids_and_masks_credentials_without_changing_sources(self):
        clients = {8: {"id": 8, "name": "渠道", "type": "telegram", "enabled": True,
                       "config": {"token": "token-secret", "password": "password-secret", "chat_id": "42"}}}
        original = copy.deepcopy(clients)
        self.settings["Message"].return_value.get_message_client_info.return_value = clients

        context, _ = self._render("settings_pages", "/notification", "setting/notification.html")

        self.assertEqual(1, context["ClientCount"])
        self.assertEqual([8], list(context["MessageClients"]))
        self.assertEqual({"token": "******", "password": "******", "chat_id": "42"}, context["MessageClients"][8]["config"])
        self.assertEqual("渠道", context["MessageClients"][8]["name"])
        self.assertIs(ModuleConf.MESSAGE_CONF["client"], context["Channels"])
        self.assertIs(ModuleConf.MESSAGE_CONF["switch"], context["Switchs"])
        self.assertEqual(original, clients)

    def test_custom_downloaders_strip_passwords_without_changing_source(self):
        downloaders = [{"id": 7, "name": "下载器", "type": "qbittorrent", "password": "downloader-secret"}]
        original = copy.deepcopy(downloaders)
        self.settings["BrushTask"].return_value.get_downloader_info.return_value = downloaders

        context, _ = self._render("settings_pages", "/userdownloader", "download/userdownloader.html")

        self.assertEqual(1, context["Count"])
        self.assertEqual([{"id": 7, "name": "下载器", "type": "qbittorrent"}], context["Downloaders"])
        self.assertEqual(original, downloaders)

    def test_users_keep_public_action_results_and_count(self):
        users = [{"name": "viewer", "pris": ["站点管理"]}]
        action = self.settings["WebAction"].return_value
        action.get_users.return_value = {"result": users}

        context, _ = self._render("settings_pages", "/users", "setting/users.html")

        action.get_users.assert_called_once_with()
        self.assertIs(users, context["Users"])
        self.assertEqual(1, context["UserCount"])

    def test_tmdbcache_keeps_query_conversion_and_pagination(self):
        helper = self.settings["MetaHelper"].return_value
        caches = [("key", {"title": "电影"})]
        helper.dump_meta_data.return_value = (140, caches)
        cases = [
            ("/tmdbcache", ("", 1, 30), 5, [1, 2, 3, 4, 5]),
            ("/tmdbcache?s=keyword&page=5&pagenum=10", ("keyword", 5, 10), 14, list(range(2, 9))),
        ]
        for url, args, pages, page_range in cases:
            with self.subTest(url=url):
                helper.dump_meta_data.reset_mock()
                context, _ = self._render("settings_pages", url, "rename/tmdbcache.html")
                helper.dump_meta_data.assert_called_once_with(*args)
                self.assertEqual((args[0], args[1], args[2], pages), tuple(context[key] for key in (
                    "Search", "CurrentPage", "PageNum", "TotalPage")))
                self.assertEqual(page_range, list(context["PageRange"]))
                self.assertIs(caches, context["TmdbCaches"])
                self.assertEqual(140, context["TotalCount"])
                self.assertEqual(1, context["Count"])


if __name__ == "__main__":
    unittest.main()
