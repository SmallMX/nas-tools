import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from flask import url_for
from werkzeug.exceptions import NotFound

from web import main
from web.routes import download_pages, search_pages, settings_pages, site_pages


GET = ("GET", "HEAD", "OPTIONS")
POST = ("OPTIONS", "POST")
PAGE_METHODS = ("GET", "HEAD", "OPTIONS", "POST")

# 单管理员模式的完整运行时路由快照；RESTX 为 /api/v1/ 注册两条 GET 规则。
EXPECTED_ROUTES = {
    GET: """
        /api/v1/ /api/v1/ /api/v1/service/mediainfo /api/v1/site/sites /api/v1/site/statistics
        /api/v1/swagger.json /healthz /robots.txt /static/<path:filename> /swaggerui/<path:filename>
    """.split(),
    POST: """
        /api/v1/brushtask/delete /api/v1/brushtask/downloader/delete /api/v1/brushtask/downloader/info
        /api/v1/brushtask/downloader/list /api/v1/brushtask/downloader/update /api/v1/brushtask/info
        /api/v1/brushtask/list /api/v1/brushtask/run /api/v1/brushtask/torrents /api/v1/brushtask/update
        /api/v1/config/info /api/v1/config/test /api/v1/config/update
        /api/v1/download/config/delete /api/v1/download/config/directory /api/v1/download/config/info
        /api/v1/download/config/list /api/v1/download/config/update /api/v1/download/history
        /api/v1/download/info /api/v1/download/item /api/v1/download/now /api/v1/download/remove
        /api/v1/download/search /api/v1/download/start /api/v1/download/stop
        /api/v1/media/cache/clear /api/v1/media/cache/delete /api/v1/media/cache/update
        /api/v1/media/category/list /api/v1/media/detail /api/v1/media/info /api/v1/media/person
        /api/v1/media/recommendations /api/v1/media/search /api/v1/media/similar /api/v1/media/tv/seasons
        /api/v1/message/client/delete /api/v1/message/client/info /api/v1/message/client/status
        /api/v1/message/client/test /api/v1/message/client/update /api/v1/recommend/list
        /api/v1/search/keyword /api/v1/search/result /api/v1/service/name/test
        /api/v1/service/network/test /api/v1/service/run /api/v1/site/check /api/v1/site/delete
        /api/v1/site/favicon /api/v1/site/indexers /api/v1/site/info /api/v1/site/list
        /api/v1/site/resources /api/v1/site/statistics/activity /api/v1/site/statistics/history
        /api/v1/site/statistics/seedinfo /api/v1/site/test /api/v1/site/update
        /api/v1/system/logging /api/v1/system/logout /api/v1/system/message /api/v1/system/progress
        /api/v1/system/restart /api/v1/torrentremover/task/delete /api/v1/torrentremover/task/info
        /api/v1/torrentremover/task/list /api/v1/torrentremover/task/update /api/v1/user/info
        /api/v1/user/login /backup /dirlist /do /telegram /upload
    """.split(),
    PAGE_METHODS: """
        / /bangumi /basic /brushtask /discovery_person /download_setting /downloaded /downloader
        /downloading /laboratory_setting /media_detail /media_setting /notification /ranking
        /recommend /resources /search /security_setting /service /service_setting /site /sitelist
        /statistics /tmdb_movie /tmdb_tv /tmdbcache /tools /tools/site-signin /torrent_remove
        /userdownloader /tencent /iqiyi /mgtv
    """.split(),
}

# 所有业务页面均由配置中的唯一管理员访问。
PAGE_ROUTES = {
    "search_pages": (
        ("/search", "search"),
        ("/recommend", "recommend"),
        ("/ranking", "ranking"),
        ("/tmdb_movie", "tmdb_movie"),
        ("/tmdb_tv", "tmdb_tv"),
        ("/bangumi", "discovery_bangumi"),
        ("/tencent", "tencent"),
        ("/iqiyi", "iqiyi"),
        ("/mgtv", "mgtv"),
        ("/media_detail", "media_detail"),
        ("/discovery_person", "discovery_person"),
    ),
    "download_pages": (
        ("/downloading", "downloading"),
        ("/downloaded", "downloaded"),
        ("/torrent_remove", "torrent_remove"),
    ),
    "site_pages": (
        ("/site", "sites"),
        ("/sitelist", "sitelist"),
        ("/resources", "resources"),
        ("/statistics", "statistics"),
        ("/brushtask", "brushtask"),
    ),
    "settings_pages": (
        ("/userdownloader", "userdownloader"),
        ("/service", "service"),
        ("/tmdbcache", "tmdbcache"),
        ("/basic", "basic"),
        ("/media_setting", "media_setting"),
        ("/service_setting", "service_setting"),
        ("/security_setting", "security_setting"),
        ("/laboratory_setting", "laboratory_setting"),
        ("/downloader", "downloader"),
        ("/download_setting", "download_setting"),
        ("/notification", "notification"),
    ),
}


class PageRouteRegistryTest(unittest.TestCase):
    def test_expected_urls_and_methods_are_registered(self):
        expected = Counter((url, methods) for methods, urls in EXPECTED_ROUTES.items() for url in urls)
        actual = Counter((rule.rule, tuple(sorted(rule.methods))) for rule in main.App.url_map.iter_rules())
        self.assertEqual(119, expected.total())
        self.assertEqual(expected, actual)

    def test_pages_use_explicit_blueprint_endpoints_without_changing_paths(self):
        self.assertEqual(30, sum(map(len, PAGE_ROUTES.values())))
        with main.App.test_request_context():
            for blueprint, routes in PAGE_ROUTES.items():
                self.assertEqual(f"web.routes.{blueprint}", main.App.blueprints[blueprint].import_name)
                for path, name in routes:
                    with self.subTest(path=path):
                        endpoint = f"{blueprint}.{name}"
                        rules = [rule for rule in main.App.url_map.iter_rules() if rule.rule == path]
                        self.assertEqual(1, len(rules))
                        self.assertEqual(endpoint, rules[0].endpoint)
                        self.assertEqual(PAGE_METHODS, tuple(sorted(rules[0].methods)))
                        self.assertEqual(f"web.routes.{blueprint}", main.App.view_functions[endpoint].__module__)
                        self.assertEqual(path, url_for(endpoint))
            for endpoint, path in {"login": "/", "healthz": "/healthz", "do": "/do",
                                   "robots": "/robots.txt", "telegram": "/telegram"}.items():
                self.assertEqual(path, url_for(endpoint))
                self.assertEqual("web.main", main.App.view_functions[endpoint].__module__)
            self.assertEqual("/static/favicon.ico", url_for("static", filename="favicon.ico"))
        self.assertEqual("login", main.LoginManager.login_view)


class PageRequestBoundaryTest(unittest.TestCase):
    def setUp(self):
        self._patch_dict(main.App.config, {"TESTING": True, "PROPAGATE_EXCEPTIONS": False})
        self.client = main.App.test_client()
        self.user = SimpleNamespace(id=0, username="admin", is_authenticated=True)
        self._patch("flask_login.utils._get_user", return_value=self.user)
        self.renderers = {}
        self.services = []
        dependencies = {
            search_pages: ("Indexer", "WebAction"),
            download_pages: ("Config", "WebAction", "TorrentRemover"),
            site_pages: ("BrushTask", "SystemConfig", "Downloader", "ChromeHelper", "Indexer",
                         "Sites", "SiteUserInfo", "Config", "WebAction"),
            settings_pages: ("BrushTask", "SystemConfig", "Downloader", "MetaHelper", "Message", "Config"),
        }
        configuration = {"app": {"proxies": {}}, "pt": {"pt_client": "qbittorrent"}}
        for module, names in dependencies.items():
            self.renderers[module.__name__.rsplit(".", 1)[1]] = self._patch(
                f"{module.__name__}.render_template", return_value="page-rendered")
            for name in names:
                service = self._patch(f"{module.__name__}.{name}")
                self.services.append(service)
                instance = service.return_value
                if name == "Config":
                    instance.get_config.side_effect = lambda section=None: configuration if section is None else configuration.get(section, {})
                elif name == "WebAction":
                    instance.get_search_result.return_value = {"result": {}, "total": 0}
                    instance.get_downloading.return_value = {"result": []}
                    instance.get_site_user_statistics.return_value = {"data": []}
                    instance.action.return_value = {"data": []}
                elif name == "Indexer":
                    instance.get_builtin_indexers.return_value = []
                    instance.get_indexer_hash_dict.return_value = {}
                elif name == "Downloader":
                    instance.get_download_setting.return_value = {}
                    instance.get_default_download_setting.return_value = None
                elif name == "BrushTask":
                    instance.get_downloader_info.return_value = []
                    instance.get_brushtask_info.return_value = []
                elif name == "Sites":
                    instance.get_sites.return_value = []
                elif name == "SiteUserInfo":
                    instance.get_pt_date.return_value = {}
                    instance.get_pt_site_statistics_history.return_value = (0, 0, None, None, None)
                elif name == "MetaHelper":
                    instance.dump_meta_data.return_value = (0, [])
                elif name == "TorrentRemover":
                    instance.get_torrent_remove_tasks.return_value = {}
                elif name == "Message":
                    instance.get_message_client_info.return_value = {}
                elif name == "SystemConfig":
                    instance.get_system_config.return_value = {}

    def _patch(self, target, **options):
        patcher = patch(target, **options)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def _patch_dict(self, target, values):
        patcher = patch.dict(target, values)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _reset_calls(self):
        for mock in [*self.services, *self.renderers.values()]:
            mock.reset_mock()

    def _assert_no_page_work(self):
        for mock in [*self.services, *self.renderers.values()]:
            mock.assert_not_called()

    def test_every_migrated_page_keeps_html_login_redirect_and_json_401(self):
        self.user.is_authenticated = False
        for routes in PAGE_ROUTES.values():
            for path, _ in routes:
                for method in ("GET", "POST"):
                    with self.subTest(path=path, method=method):
                        self._reset_calls()
                        response = self.client.open(path, method=method)
                        self.assertEqual(302, response.status_code)
                        location = urlsplit(response.location)
                        self.assertEqual("/", location.path)
                        self.assertEqual([path.lstrip("/")], parse_qs(location.query)["next"])
                        response = self.client.open(path, method=method, headers={"Accept": "application/json"})
                        self.assertEqual(401, response.status_code)
                        self.assertEqual(401, response.json["code"])
                        self.assertFalse(response.json["success"])
                        self._assert_no_page_work()
        response = self.client.get("/resources?site=7&page=2", headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(401, response.status_code)

    def test_admin_can_render_all_pages(self):
        for blueprint, routes in PAGE_ROUTES.items():
            for path, _ in routes:
                for method in ("GET", "POST"):
                    with self.subTest(path=path, method=method):
                        self._reset_calls()
                        response = self.client.open(path, method=method)
                        self.assertEqual(200, response.status_code)
                        self.renderers[blueprint].assert_called_once()

    def test_global_headers_error_handlers_and_teardown_apply_to_blueprint_requests(self):
        cleanup = self._patch("web.main.remove_db_session")
        self._patch("web.main.App.logger.error")
        renderer = self.renderers["search_pages"]
        cases = ((None, {}, 200), (NotFound(), {}, 404),
                 (RuntimeError("fixture-error"), {}, 500),
                 (RuntimeError("fixture-error"), {"Accept": "application/json"}, 500))
        for error, headers, status in cases:
            with self.subTest(status=status, json=bool(headers)):
                cleanup.reset_mock()
                renderer.side_effect = error
                response = self.client.get("/ranking", headers=headers, base_url="https://localhost")
                self.assertEqual(status, response.status_code)
                self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
                self.assertEqual("SAMEORIGIN", response.headers["X-Frame-Options"])
                self.assertEqual("no-store", response.headers["Cache-Control"])
                self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])
                cleanup.assert_called_once_with()
                if headers:
                    self.assertEqual(500, response.json["code"])
                    self.assertFalse(response.json["success"])
                    self.assertNotIn("fixture-error", response.get_data(as_text=True))
                elif status != 200:
                    self.assertIn(str(status), response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
