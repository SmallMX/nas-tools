import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.downloader import Downloader
from app.helper.meta_helper import MetaHelper
from app.media.category import Category
from app.media.fanart import Fanart
from app.sites.site_cookie import SiteCookie
from app.utils.types import DownloaderType, MediaType


def fresh_singleton(factory):
    service_class = factory.__closure__[0].cell_contents
    return service_class.__new__(service_class)


class ConfigConsumersTest(unittest.TestCase):
    def test_downloader_runtime_reload_keeps_clients_database_and_dependencies(self):
        service = fresh_singleton(Downloader)
        clients = {DownloaderType.QB.value: Mock(), DownloaderType.TR.value: Mock()}
        settings = {"7": {"name": "日常下载"}}
        service.clients = clients
        service._download_setting = settings
        dependencies = {name: Mock() for name in ("dbhelper", "message", "media", "sites")}
        for name, value in dependencies.items():
            setattr(service, name, value)
        config = {
            "pt": {"pt_client": "transmission", "pt_monitor_only": True, "download_order": "seeder"},
            "downloaddir": [{"save_path": "/downloads/new"}],
        }

        with patch("app.downloader.downloader.Config") as config_factory, \
                patch("app.downloader.downloader.DbHelper") as database, \
                patch("app.downloader.downloader.Message") as message, \
                patch("app.downloader.downloader.Media") as media, \
                patch("app.downloader.downloader.Sites") as sites:
            config_factory.return_value.get_config.side_effect = lambda key: config.get(key, {})
            service.reload_runtime_config()

            self.assertEqual(DownloaderType.TR, service.get_default_client_type())
            self.assertTrue(service._pt_monitor_only)
            self.assertEqual("seeder", service._download_order)
            self.assertEqual(config["downloaddir"], service._downloaddir)
            config.clear()
            service.reload_runtime_config()

            self.assertIsNone(service.get_default_client_type())
            self.assertFalse(service._pt_monitor_only)
            self.assertIsNone(service._download_order)
            self.assertEqual([], service._downloaddir)
            for factory in (database, message, media, sites):
                factory.assert_not_called()

        self.assertIs(clients, service.clients)
        self.assertIs(settings, service._download_setting)
        for name, value in dependencies.items():
            self.assertIs(value, getattr(service, name))
            self.assertEqual([], value.mock_calls)

    def test_reset_client_only_rebuilds_selected_downloader_on_next_access(self):
        for target in (DownloaderType.QB, "QB", "Qbittorrent", "qbittorrent"):
            with self.subTest(target=target):
                service = fresh_singleton(Downloader)
                old_qb, transmission, replacement = Mock(), Mock(), Mock()
                service.clients = {DownloaderType.QB.value: old_qb, DownloaderType.TR.value: transmission}
                service._default_client_type = DownloaderType.QB
                service._Downloader__build_class = Mock(return_value=replacement)

                service.reset_client(target)

                self.assertEqual({DownloaderType.TR.value: transmission}, service.clients)
                service._Downloader__build_class.assert_not_called()
                self.assertEqual([], old_qb.mock_calls)
                self.assertIs(replacement, service.default_client)
                service._Downloader__build_class.assert_called_once_with(DownloaderType.QB.value, None)
                service._default_client_type = DownloaderType.TR
                self.assertIs(transmission, service.default_client)
                service.reset_client("unknown")
                self.assertEqual({DownloaderType.QB.value: replacement, DownloaderType.TR.value: transmission},
                                 service.clients)

    def test_meta_runtime_reload_preserves_unsaved_cache_and_resets_removed_option(self):
        service = fresh_singleton(MetaHelper)
        unsaved = {"new-media": {"id": 42, "title": "尚未保存"}}
        service._meta_data = unsaved
        service._meta_path = "/unchanged/tmdb.dat"
        with patch("app.helper.meta_helper.Config") as config_factory, \
                patch.object(service, "_MetaHelper__load_meta_data") as load:
            for config, expected in (({"tmdb_cache_expire": True}, True), ({}, False), (None, False)):
                with self.subTest(config=config):
                    config_factory.return_value.get_config.return_value = config
                    service.reload_runtime_config()
                    self.assertEqual(expected, service._tmdb_cache_expire)
                    self.assertIs(unsaved, service._meta_data)
                    self.assertEqual(42, service._meta_data["new-media"]["id"])
                    self.assertEqual("/unchanged/tmdb.dat", service.get_meta_data_path())
            load.assert_not_called()

    def test_category_removal_clears_all_previous_classifications(self):
        for config in ({"category": ""}, {"category": None}, {}, None):
            with self.subTest(config=config):
                service = fresh_singleton(Category)
                for attribute in ("_category_path", "_categorys", "_movie_categorys",
                                  "_tv_categorys", "_anime_categorys"):
                    setattr(service, attribute, {"old": {}})
                with patch("app.media.category.Config") as config_factory, \
                        patch("builtins.open") as open_file:
                    config_factory.return_value.get_config.return_value = config
                    service.init_config()
                    open_file.assert_not_called()
                self.assertIsNone(service._category_path)
                self.assertIsNone(service._categorys)
                self.assertFalse(service.get_movie_category_flag())
                self.assertFalse(service.get_tv_category_flag())
                self.assertFalse(service.get_anime_category_flag())
                self.assertEqual([], service.get_movie_categorys())
                self.assertEqual([], service.get_tv_categorys())
                self.assertEqual([], service.get_anime_categorys())

    def test_category_reload_still_reads_selected_file(self):
        service = fresh_singleton(Category)
        with tempfile.TemporaryDirectory(prefix="nastool-category-test-") as directory:
            path = Path(directory) / "selected.yaml"
            path.write_text("movie:\n  电影分类: {}\ntv:\n  剧集分类: {}\nanime:\n  动漫分类: {}\n", encoding="utf-8")
            with patch("app.media.category.Config") as config_factory:
                config_factory.return_value.get_config.return_value = {"category": "selected"}
                config_factory.return_value.get_config_path.return_value = directory
                service.init_config()
            self.assertEqual(str(path), service._category_path)
            self.assertEqual(["电影分类"], list(service.get_movie_categorys()))
            self.assertEqual(["剧集分类"], list(service.get_tv_categorys()))
            self.assertEqual(["动漫分类"], list(service.get_anime_categorys()))

    def test_fanart_proxy_reload_discards_cached_failure_and_supports_proxy_removal(self):
        Fanart._Fanart__request_fanart.cache_clear()
        self.addCleanup(Fanart._Fanart__request_fanart.cache_clear)
        response = Mock(status_code=200)
        response.json.return_value = {"movieposter": [{"url": "https://images.example/poster.jpg"}]}
        with patch.object(Fanart, "_proxies", {"https": "http://old-proxy.example"}), \
                patch("app.media.fanart.Config") as config_factory, \
                patch("app.media.fanart.RequestUtils") as requests:
            config_factory.return_value.get_config.return_value = {"fanart_api_key": "test-key"}
            requests.return_value.get_res.side_effect = [None, response, None]
            self.assertIsNone(Fanart().get_poster(MediaType.MOVIE, 1))
            self.assertIsNone(Fanart().get_poster(MediaType.MOVIE, 1))
            self.assertEqual(1, requests.call_count)

            proxies = {"https": "http://new-proxy.example"}
            config_factory.return_value.get_proxies.return_value = proxies
            Fanart.reload_runtime_config()

            self.assertEqual("https://images.example/poster.jpg", Fanart().get_poster(MediaType.MOVIE, 1))
            self.assertEqual(proxies, requests.call_args.kwargs["proxies"])
            config_factory.return_value.get_proxies.return_value = None
            Fanart.reload_runtime_config()
            self.assertIsNone(Fanart().get_poster(MediaType.MOVIE, 1))
            self.assertIsNone(requests.call_args.kwargs["proxies"])
            self.assertEqual(3, requests.call_count)

    def test_site_cookie_runtime_reload_keeps_pending_captcha_and_progress(self):
        service = fresh_singleton(SiteCookie)
        captcha = {"site": "pending-code"}
        progress, sites, database = Mock(), Mock(), Mock()
        service.captcha_code = captcha
        service.progress, service.sites, service.dbhelpter = progress, sites, database
        with patch("app.utils.http_utils.Config") as config_factory:
            config_factory.return_value.get_ua.return_value = "old-agent"
            service.reload_runtime_config()
            old_request = service.ocrhelper.req
            config_factory.return_value.get_ua.return_value = "new-agent"
            service.reload_runtime_config()

        self.assertIsNot(old_request, service.ocrhelper.req)
        self.assertEqual("new-agent", service.ocrhelper.req._headers["User-Agent"])
        self.assertIs(captcha, service.captcha_code)
        self.assertEqual("pending-code", service.get_code("site"))
        self.assertIs(progress, service.progress)
        self.assertIs(sites, service.sites)
        self.assertIs(database, service.dbhelpter)
        for dependency in (progress, sites, database):
            self.assertEqual([], dependency.mock_calls)


if __name__ == "__main__":
    unittest.main()
