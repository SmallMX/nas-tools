import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.downloader import Downloader
from app.utils.types import DownloaderType, MediaType, SearchType


class TorrentBatchCacheTest(unittest.TestCase):
    def setUp(self):
        cls = Downloader.__closure__[0].cell_contents
        self.service = cls.__new__(cls)
        self.service.sites = Mock()
        self.service.sites.get_site_attr.return_value = {"cookie": "account-one", "ua": "test"}
        self.service.sites.get_site_download_setting.return_value = None
        self.service.message = Mock()
        self.service._default_client_type = DownloaderType.QB
        self.service._download_setting = {"-1": {"downloader": "Qbittorrent"}}
        self.service.get_default_download_setting = Mock(return_value="-1")
        self.service.download = Mock(return_value=(True, ""))
        self.service.get_download_list = Mock(side_effect=lambda items: items)
        self.client = Mock()
        self.client.get_torrent_id_by_tag.return_value = "hash"
        self.client.start_torrents.return_value = True
        self.service._Downloader__get_client = Mock(return_value=self.client)
        self.service.set_files_status = Mock(return_value=list(range(1, 7)))
        directory = tempfile.TemporaryDirectory(prefix="torrent-batch-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "show.torrent"
        self.path.write_bytes(b"validated torrent placeholder")
        patcher = patch("app.downloader.downloader.Torrent")
        self.torrent_factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.torrent_factory.is_dynamic_download_url.return_value = False
        self.get_info = self.torrent_factory.return_value.get_torrent_info
        self.valid_result = (str(self.path), b"content", "Show", [
            f"Show.S01E{episode:02d}.mkv" for episode in range(1, 7)
        ], "")
        self.get_info.return_value = self.valid_result

    @staticmethod
    def item(episodes=()):
        return SimpleNamespace(
            type=MediaType.TV, tmdb_id=42, org_string="Show.S01", site="Test site",
            enclosure="https://tracker.example/download?id=1", page_url="https://tracker.example/details/1",
            save_path="/downloads", download_setting=None,
            get_season_list=lambda: [1], get_episode_list=lambda: list(episodes),
        )

    def test_full_season_check_and_partial_selection_share_one_request(self):
        pack = self.item()
        single = self.item([7])
        single.enclosure = "https://tracker.example/download?id=2"
        requirements = {42: [{"season": 1, "episodes": [], "total_episodes": 12}]}

        downloaded, remaining = self.service.batch_download(SearchType.TG, [pack, single], requirements)

        self.assertEqual([single, pack], downloaded)
        self.assertEqual([8, 9, 10, 11, 12], remaining[42][0]["episodes"])
        self.get_info.assert_called_once()
        self.assertEqual(str(self.path), self.service.download.call_args.kwargs["torrent_file"])

    def test_cache_is_private_to_each_batch(self):
        for _ in range(2):
            self.service.batch_download(SearchType.TG, [self.item()], {
                42: [{"season": 1, "episodes": [1, 2], "total_episodes": 12}],
            })
        self.assertEqual(2, self.get_info.call_count)

    def test_cache_isolates_url_site_context_and_credentials(self):
        cache = {}
        url = "https://tracker.example/download?id=1"
        first = self.service.get_torrent_episodes(url, "https://tracker.example/details/1", cache)
        self.service.get_torrent_episodes(url, "https://tracker.example/details/1", cache)
        self.get_info.assert_called_once()
        first[0].clear()
        self.assertEqual(list(range(1, 7)), sorted(self.service.get_torrent_episodes(
            url, "https://tracker.example/details/1", cache)[0]))

        self.service.get_torrent_episodes(url, "https://tracker.example/details/2", cache)
        self.service.sites.get_site_attr.return_value = {"cookie": "account-two", "ua": "test"}
        self.service.get_torrent_episodes(url, "https://tracker.example/details/1", cache)
        self.service.get_torrent_episodes(url + "&another=1", "https://tracker.example/details/1", cache)
        self.assertEqual(4, self.get_info.call_count)
        self.assertNotIn("account-one", repr(cache))

    def test_missing_cache_file_is_fetched_again(self):
        cache = {}
        self.service.get_torrent_episodes("https://tracker.example/download", cache=cache)
        self.path.unlink()
        self.service.get_torrent_episodes("https://tracker.example/download", cache=cache)
        self.assertEqual(2, self.get_info.call_count)

    def test_failure_does_not_poison_later_attempt(self):
        cache = {}
        self.get_info.side_effect = [(None, None, "", [], "temporary error"), self.valid_result]
        self.assertEqual(([], None), self.service.get_torrent_episodes(
            "https://tracker.example/download", cache=cache))
        self.assertEqual({}, cache)
        episodes, path = self.service.get_torrent_episodes("https://tracker.example/download", cache=cache)
        self.assertEqual(list(range(1, 7)), sorted(episodes))
        self.assertEqual(str(self.path), path)


if __name__ == "__main__":
    unittest.main()
