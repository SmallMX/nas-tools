import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.downloader import Downloader
from app.downloader.client import Qbittorrent, Transmission
from app.torrentremover import TorrentRemover
from app.utils.types import DownloaderType
from config import PT_TAG


class TorrentRecord(dict):
    def __getattr__(self, name):
        return self[name]


class TorrentRemovalContractsTest(unittest.TestCase):
    def setUp(self):
        self.facade = Downloader.__wrapped__.__new__(Downloader.__wrapped__)
        self.facade._pt_monitor_only = False
        self.facade.clients = {}
        self.adapters = {}
        self.native_ids = {}
        now = datetime.now(timezone.utc)
        cases = (
            (11, "Zeta", [PT_TAG, "archive", "watched"]),
            (12, "Alpha", ["archive", "watched"]),
            (13, "Partial archive", [PT_TAG, "archive"]),
            (14, "Partial watched", [PT_TAG, "watched"]),
        )
        for downloader_type in (DownloaderType.QB, DownloaderType.TR):
            torrents = []
            ids = {}
            for number, name, labels in cases:
                if downloader_type == DownloaderType.QB:
                    torrent_id = f"{number:040x}"
                    torrent = TorrentRecord(
                        hash=torrent_id, name=name, tags=", ".join(labels),
                        completion_on=int((now - timedelta(hours=2)).timestamp()),
                        added_on=int((now - timedelta(hours=4)).timestamp()),
                        uploaded=2 * 1024 ** 3, ratio=2, size=1024 ** 3,
                        save_path="/downloads", tracker="https://tracker.example/announce",
                        state="uploading", category="movies",
                    )
                else:
                    torrent_id = number
                    torrent = SimpleNamespace(
                        id=torrent_id, name=name, labels=labels,
                        date_done=now - timedelta(hours=2), date_added=now - timedelta(hours=4),
                        ratio=2, total_size=1024 ** 3, download_dir="/downloads",
                        trackers=[{"announce": "https://tracker.example/announce", "sitename": "tracker"}],
                        status="seeding", error_string="",
                    )
                torrents.append(torrent)
                ids[name] = torrent_id
            adapter_class = Qbittorrent if downloader_type == DownloaderType.QB else Transmission
            adapter = adapter_class.__new__(adapter_class)
            adapter.get_torrents = Mock(return_value=(torrents, False))
            adapter.stop_torrents = Mock(return_value=True)
            adapter.delete_torrents = Mock(return_value=True)
            self.facade.clients[downloader_type.value] = adapter
            self.adapters[downloader_type] = adapter
            self.native_ids[downloader_type] = ids

    def test_global_and_task_tag_limits_preserve_config_and_client_native_ids(self):
        for downloader_type in (DownloaderType.QB, DownloaderType.TR):
            for tags in ("archive;watched", ["archive", "watched"]):
                for monitor_only, onlynastool in ((False, 0), (True, 0), (False, 1), (True, 1)):
                    with self.subTest(downloader=downloader_type, tags=tags,
                                      monitor_only=monitor_only, onlynastool=onlynastool):
                        self.facade._pt_monitor_only = monitor_only
                        config = {"tags": copy.deepcopy(tags), "onlynastool": onlynastool, "samedata": 0}
                        original = copy.deepcopy(config)

                        result = self.facade.get_remove_torrents(downloader=downloader_type, config=config)

                        expected_names = ["Zeta"] if monitor_only or onlynastool else ["Alpha", "Zeta"]
                        self.assertEqual(expected_names, [item["name"] for item in result])
                        self.assertEqual([self.native_ids[downloader_type][name] for name in expected_names],
                                         [item["id"] for item in result])
                        self.assertEqual(original, config)

    def test_previews_and_actions_share_selection_without_touching_other_torrents(self):
        for task_downloader, downloader_type in (("Qb", DownloaderType.QB), ("Tr", DownloaderType.TR)):
            for action in (1, 2, 3):
                with self.subTest(downloader=downloader_type, action=action):
                    adapter = self.adapters[downloader_type]
                    adapter.stop_torrents.reset_mock()
                    adapter.delete_torrents.reset_mock()
                    rules = {"tags": ["archive", "watched"], "onlynastool": 1, "samedata": 0}
                    original_rules = copy.deepcopy(rules)
                    task = {
                        "id": 7, "name": "selected policy", "downloader": task_downloader,
                        "onlynastool": 1, "samedata": 0, "action": action,
                        "config": rules, "interval": 10, "enabled": 1,
                    }
                    service = TorrentRemover.__wrapped__.__new__(TorrentRemover.__wrapped__)
                    service.downloader = self.facade
                    service.message = Mock()
                    service._remove_tasks = {
                        "7": task,
                        "8": {**task, "id": 8, "name": "other policy", "onlynastool": 0,
                              "config": {"tags": ["archive"]}},
                    }
                    with patch.object(self.facade, "get_remove_torrents",
                                      wraps=self.facade.get_remove_torrents) as select, \
                            patch("app.torrentremover.log"):
                        ok, preview = service.get_remove_torrents(7)

                        self.assertTrue(ok)
                        self.assertEqual([self.native_ids[downloader_type]["Zeta"]],
                                         [item["id"] for item in preview])
                        adapter.stop_torrents.assert_not_called()
                        adapter.delete_torrents.assert_not_called()

                        service.auto_remove_torrents(taskids=7)

                    self.assertEqual(2, select.call_count)
                    for selection in select.call_args_list:
                        self.assertEqual(downloader_type, selection.kwargs["downloader"])
                        self.assertEqual(original_rules, selection.kwargs["config"])
                    operation = adapter.stop_torrents if action == 1 else adapter.delete_torrents
                    operation.assert_called_once()
                    call = operation.call_args
                    operated_ids = call.kwargs.get("ids") if "ids" in call.kwargs else call.args[0]
                    self.assertEqual([item["id"] for item in preview], operated_ids)
                    if action == 1:
                        adapter.delete_torrents.assert_not_called()
                    else:
                        adapter.stop_torrents.assert_not_called()
                        self.assertEqual(action == 3, call.kwargs["delete_file"])
                    self.assertEqual(original_rules, rules)


if __name__ == "__main__":
    unittest.main()
