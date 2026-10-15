import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.brushtask import BrushTask
from app.config_reload import apply_config_changes
from app.conf import SystemConfig
from app.downloader import Downloader
from app.helper import DisplayHelper, IndexerHelper, MetaHelper, ProgressHelper, ThreadHelper
from app.indexer import Indexer
from app.media import DouBan
from app.media.category import Category
from app.message import Message
from app.scheduler import Scheduler
from app.sites import Sites, SiteUserInfo
from app.sites.site_cookie import SiteCookie
from app.tools import SiteSignin
from app.torrentremover import TorrentRemover
from app.utils.types import DownloaderType


class ConfigDispatchTest(unittest.TestCase):
    def setUp(self):
        self.factories = (Downloader, Indexer, MetaHelper, Category, Message, Scheduler, SiteSignin,
                          DouBan, SiteCookie, Sites, SiteUserInfo, BrushTask, TorrentRemover,
                          SystemConfig, DisplayHelper, IndexerHelper, ProgressHelper, ThreadHelper)
        self.services = {factory: Mock() for factory in self.factories}
        self.registry = {factory.__wrapped__: service for factory, service in self.services.items()}
        self._patch("app.utils.commons.INSTANCES", self.registry)
        self.media = self._patch("app.media.Media")
        self.fanart = self._patch("app.media.fanart.Fanart.reload_runtime_config")
        self.wallpaper = self._patch("web.backend.wallpaper._get_login_wallpaper_for_date")
        self.security = self._patch("web.main.configure_security")
        self.logging = self._patch("log.Logger.reload_config")
        self._patch("app.config_reload.log.error")
        self.indexer_client = SimpleNamespace(media=object())
        self.services[Indexer].get_client.return_value = self.indexer_client

    def _patch(self, target, value=None):
        patcher = patch(target, value) if value is not None else patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _assert_untouched(self, *changed):
        for factory, service in self.services.items():
            if factory not in changed:
                self.assertEqual([], service.mock_calls, factory.__name__)

    def test_request_time_settings_do_not_refresh_cached_services(self):
        self.assertTrue(apply_config_changes({}, {
            "app": {"login_user": "updated", "ocr_server": "https://ocr.example"},
            "pt": {"indexer_sites": ["site"], "search_auto": False, "site_search_concurrency": 4},
            "security": {"api_key": "updated"},
            "laboratory": {"search_en_title": True, "release_groups": "example"},
        }))
        self._assert_untouched()
        for callback in (self.media, self.fanart, self.wallpaper, self.security, self.logging):
            callback.assert_not_called()

    def test_download_preferences_do_not_drop_connections_or_restart_tasks(self):
        self.assertTrue(apply_config_changes({}, {
            "pt": {"pt_client": "transmission", "download_order": "seeder"},
            "downloaddir": [{"path": "/downloads"}],
        }))
        self.services[Downloader].reload_runtime_config.assert_called_once_with()
        self.services[Downloader].reset_client.assert_not_called()
        self.services[Downloader].init_config.assert_not_called()
        self._assert_untouched(Downloader)

    def test_connection_change_only_invalidates_its_downloader(self):
        for section, downloader_type in (("qbittorrent", DownloaderType.QB), ("transmission", DownloaderType.TR)):
            with self.subTest(section=section):
                self.services[Downloader].reset_mock()
                self.assertTrue(apply_config_changes({}, {section: {"host": "updated"}}))
                self.services[Downloader].reset_client.assert_called_once_with(downloader_type)
                self.services[Downloader].reload_runtime_config.assert_not_called()
                self.services[Downloader].init_config.assert_not_called()
                self._assert_untouched(Downloader)

    def test_media_options_replace_only_long_lived_media_objects(self):
        replacement = self.media.return_value
        self.assertTrue(apply_config_changes({}, {"laboratory": {"search_tmdbweb": True}}))
        self.assertIs(replacement, self.services[Downloader].media)
        self.assertIs(replacement, self.indexer_client.media)
        self.assertEqual(2, self.media.call_count)
        self.services[Downloader].init_config.assert_not_called()
        self.services[Downloader].reset_client.assert_not_called()
        self.services[Indexer].init_config.assert_not_called()
        self._assert_untouched(Downloader, Indexer)

    def test_cache_policy_changes_do_not_reload_cache_or_clients(self):
        self.assertTrue(apply_config_changes({}, {"laboratory": {"tmdb_cache_expire": True}}))
        self.services[MetaHelper].reload_runtime_config.assert_called_once_with()
        self.services[MetaHelper].init_config.assert_not_called()
        self._assert_untouched(MetaHelper)

    def test_signin_options_do_not_reschedule_jobs(self):
        before = {"tools": {"site_signin": {"cron": "08:00", "notify": True}}}
        after = {"tools": {"site_signin": {"cron": "08:00", "notify": False}}}
        self.assertTrue(apply_config_changes(before, after))
        self.services[SiteSignin].init_config.assert_called_once_with()
        self._assert_untouched(SiteSignin)

    def test_signin_cron_only_refreshes_signin_and_its_schedule(self):
        self.assertTrue(apply_config_changes({}, {"tools": {"site_signin": {"cron": "08:00"}}}))
        self.services[SiteSignin].init_config.assert_called_once_with()
        self.services[Scheduler].reload_runtime_config.assert_called_once_with()
        self.services[Scheduler].stop_service.assert_not_called()
        self._assert_untouched(SiteSignin, Scheduler)

    def test_secret_and_domain_share_one_message_refresh(self):
        self.assertTrue(apply_config_changes({}, {
            "app": {"domain": "https://nas.example"},
            "security": {"telegram_webhook_secret": "updated"},
        }))
        self.services[Message].reload_runtime_config.assert_called_once_with()
        self.services[Message].init_config.assert_not_called()
        self._assert_untouched(Message)

    def test_failed_consumer_does_not_prevent_other_related_refreshes(self):
        self.services[MetaHelper].reload_runtime_config.side_effect = RuntimeError("cache policy failed")
        self.assertFalse(apply_config_changes({}, {
            "laboratory": {"tmdb_cache_expire": True}, "app": {"domain": "https://nas.example"},
        }))
        self.services[Message].reload_runtime_config.assert_called_once_with()
        self._assert_untouched(MetaHelper, Message)

    def test_retry_paths_reapply_restored_or_deleted_configuration(self):
        self.assertTrue(apply_config_changes({}, {}, retry_paths={"downloaddir", "tools.site_signin.cron"}))
        self.services[Downloader].reload_runtime_config.assert_called_once_with()
        self.services[SiteSignin].init_config.assert_called_once_with()
        self.services[Scheduler].reload_runtime_config.assert_called_once_with()
        self._assert_untouched(Downloader, SiteSignin, Scheduler)

    def test_dormant_services_are_not_started_by_configuration_changes(self):
        self.registry.clear()
        self.assertTrue(apply_config_changes({}, {
            "pt": {"pt_client": "transmission"}, "qbittorrent": {"qbhost": "localhost"},
            "app": {"domain": "https://nas.example"}, "tools": {"site_signin": {"cron": "08:00"}},
        }))
        self.assertEqual({}, self.registry)
        self._assert_untouched()


if __name__ == "__main__":
    unittest.main()
