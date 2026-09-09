import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import tests
from app.downloader import Downloader
from app.utils.types import DownloaderType, MediaType, SearchType


class DownloadSelectionTest(unittest.TestCase):
    def setUp(self):
        downloader_class = Downloader.__closure__[0].cell_contents
        self.service = downloader_class.__new__(downloader_class)
        self.service._default_client_type = DownloaderType.QB
        self.service._download_setting = {
            "-1": {"downloader": "Qbittorrent"},
            "site": {"downloader": "Transmission"},
        }
        self.service.get_default_download_setting = Mock(return_value="-1")
        self.service.sites = Mock()
        self.service.sites.get_site_download_setting.return_value = None
        self.service.message = Mock()
        self.service.download = Mock(return_value=(True, ""))
        self.service.get_download_list = Mock(side_effect=lambda items: items)
        self.service.get_torrent_episodes = Mock(return_value=([1, 2, 3], "/tmp/show.torrent"))
        self.client = Mock()
        self.client.get_torrent_id_by_tag.return_value = "hash"
        self.client.start_torrents.return_value = True
        self.client.set_files.return_value = True
        self.service._Downloader__get_client = Mock(return_value=self.client)

    @staticmethod
    def media(season=1, episodes=(), download_setting=None):
        return SimpleNamespace(
            type=MediaType.TV,
            tmdb_id=42,
            org_string=f"Show.S{season:02d}",
            save_path="/downloads",
            download_setting=download_setting,
            site="Test site",
            enclosure=f"https://tracker.invalid/show/{season}",
            page_url=f"https://tracker.invalid/details/{season}",
            get_season_list=lambda: [season],
            get_episode_list=lambda: list(episodes),
        )

    @staticmethod
    def requirements(*seasons, episodes=(2,)):
        return {42: [
            {"season": season, "episodes": list(episodes), "total_episodes": 3}
            for season in seasons
        ]}

    def run_partial(self):
        item = self.media()
        pending = self.requirements(1)
        result = self.service.batch_download(SearchType.TG, [item], pending)
        return item, result

    def test_episode_downloads_do_not_skip_next_season_after_removal(self):
        items = [self.media(season=season, episodes=[2]) for season in (1, 2, 3)]
        downloaded, remaining = self.service.batch_download(
            SearchType.TG, items, self.requirements(1, 2, 3),
        )

        self.assertEqual(items, downloaded)
        self.assertEqual({}, remaining)
        self.assertEqual(3, self.service.download.call_count)
        self.service.get_torrent_episodes.assert_not_called()

    def test_partial_downloads_process_all_seasons_and_report_once(self):
        items = [self.media(season=season) for season in (1, 2, 3)]
        self.service.set_files_status = Mock(return_value=[2])

        downloaded, remaining = self.service.batch_download(
            SearchType.TG, items, self.requirements(1, 2, 3),
        )

        self.assertEqual(items, downloaded)
        self.assertEqual({}, remaining)
        self.assertEqual(3, self.client.start_torrents.call_count)
        self.assertEqual(3, self.service.message.send_download_message.call_count)
        self.service.message.send_download_fail_message.assert_not_called()
        for call in self.service.download.call_args_list:
            self.assertIs(True, call.kwargs["is_paused"])

    def test_selection_failure_keeps_missing_episodes_and_does_not_start(self):
        self.service.set_files_status = Mock(return_value=[])
        item, (downloaded, remaining) = self.run_partial()

        self.assertEqual([], downloaded)
        self.assertEqual(self.requirements(1), remaining)
        self.client.start_torrents.assert_not_called()
        self.service.message.send_download_message.assert_not_called()
        self.service.message.send_download_fail_message.assert_called_once_with(
            item, "选集失败，下载任务保持暂停",
        )

    def test_missing_task_id_does_not_mark_episodes_downloaded(self):
        self.client.get_torrent_id_by_tag.return_value = None
        self.service.set_files_status = Mock()
        _, (downloaded, remaining) = self.run_partial()

        self.assertEqual([], downloaded)
        self.assertEqual(self.requirements(1), remaining)
        self.service.set_files_status.assert_not_called()
        self.client.start_torrents.assert_not_called()
        self.service.message.send_download_message.assert_not_called()
        self.service.message.send_download_fail_message.assert_called_once()

    def test_start_failure_keeps_missing_episodes_and_reports_failure(self):
        self.service.set_files_status = Mock(return_value=[2])
        self.client.start_torrents.return_value = False
        _, (downloaded, remaining) = self.run_partial()

        self.assertEqual([], downloaded)
        self.assertEqual(self.requirements(1), remaining)
        self.service.message.send_download_message.assert_not_called()
        self.service.message.send_download_fail_message.assert_called_once()

    def test_only_confirmed_selected_episodes_are_removed(self):
        item = self.media()
        self.service.set_files_status = Mock(return_value=[2])

        downloaded, remaining = self.service.batch_download(
            SearchType.TG, [item], self.requirements(1, episodes=(1, 2)),
        )

        self.assertEqual([item], downloaded)
        self.assertEqual(self.requirements(1, episodes=(1,)), remaining)
        self.client.start_torrents.assert_called_once_with("hash")

    def test_selection_uses_site_downloader_when_no_explicit_setting(self):
        self.service.sites.get_site_download_setting.return_value = "site"
        self.service.download.return_value = (SimpleNamespace(id=7), "")
        self.service.set_files_status = Mock(return_value=[2])

        _, (_, remaining) = self.run_partial()

        self.assertEqual({}, remaining)
        self.service._Downloader__get_client.assert_called_once_with(DownloaderType.TR)
        self.service.set_files_status.assert_called_once_with(7, {2}, DownloaderType.TR)
        self.client.get_torrent_id_by_tag.assert_not_called()
        self.client.start_torrents.assert_called_once_with(7)

    def test_explicit_download_setting_takes_precedence_over_site(self):
        item = self.media(download_setting="-1")
        self.service.sites.get_site_download_setting.return_value = "site"
        self.service.set_files_status = Mock(return_value=[2])

        self.service.batch_download(SearchType.TG, [item], self.requirements(1))

        self.service.sites.get_site_download_setting.assert_not_called()
        self.service._Downloader__get_client.assert_called_once_with(DownloaderType.QB)

    def test_download_settings_resolve_a_single_default_record(self):
        item = self.media()
        for setting in (None, "missing"):
            with self.subTest(setting=setting):
                attributes = self.service._Downloader__get_download_attributes(item, setting)
                self.assertEqual({"downloader": "Qbittorrent"}, attributes)

    def test_qb_selection_failure_returns_no_selected_episodes(self):
        self.client.get_files.return_value = [
            {"index": 0, "name": "Show.S01E01.mkv"},
            {"index": 1, "name": "Show.S01E02.mkv"},
        ]
        self.client.set_files.return_value = False

        selected = self.service.set_files_status("hash", [2], DownloaderType.QB)

        self.assertEqual([], selected)
        self.client.set_files.assert_called_once_with(
            torrent_hash="hash", file_ids=[0], priority=0,
        )

    def test_tr_selection_failure_returns_no_selected_episodes(self):
        self.client.get_files.return_value = [
            SimpleNamespace(name="Show.S01E01.mkv"),
            SimpleNamespace(name="Show.S01E02.mkv"),
        ]
        self.client.set_files.return_value = False

        selected = self.service.set_files_status(7, [2], DownloaderType.TR)

        self.assertEqual([], selected)
        self.client.set_files.assert_called_once_with(file_info={7: {
            0: {"priority": "normal", "selected": False},
            1: {"priority": "normal", "selected": True},
        }})

    def test_all_requested_qb_files_can_start_without_exclusions(self):
        self.client.get_files.return_value = [{"index": 0, "name": "Show.S01E02.mkv"}]

        self.assertEqual([2], self.service.set_files_status("hash", [2], DownloaderType.QB))
        self.client.set_files.assert_not_called()


if __name__ == "__main__":
    unittest.main()
