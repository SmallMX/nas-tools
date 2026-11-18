import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import qbittorrentapi
import transmission_rpc

from app.brushtask import BrushTask
from app.downloader.client import Qbittorrent, Transmission
from app.downloader.client.transmission import _BrushTransmissionClient


class DownloaderSdkContractsTest(unittest.TestCase):
    def test_tr_brush_rejects_existing_torrent_before_sdk_merges_add_results(self):
        client = _BrushTransmissionClient.__new__(_BrushTransmissionClient)
        for kind in ("torrent-added", "torrent-duplicate"):
            response = '{"arguments":{"' + kind + '":{"id":17}},"result":"success"}'
            with patch.object(transmission_rpc.Client, "_http_query", return_value=response):
                if kind == "torrent-duplicate":
                    with self.assertRaises(ValueError):
                        client._http_query({"method": "torrent-add"})
                else:
                    self.assertEqual(response, client._http_query({"method": "torrent-add"}))

    def test_qb_sends_scalar_status_and_tag_to_sdk(self):
        adapter = Qbittorrent.__new__(Qbittorrent)
        adapter.qbc = qbittorrentapi.Client()
        adapter.ver = "v5.0.0"
        with patch.object(adapter.qbc, "_post_cast", return_value=[]) as request, \
                patch.object(adapter.qbc, "app_web_api_version", return_value="2.11.0"):
            adapter.get_downloading_torrents(tag=["NASTOOL"])
            self.assertEqual("downloading", request.call_args.kwargs["data"]["filter"])
            self.assertEqual("NASTOOL", request.call_args.kwargs["data"]["tag"])
            adapter.get_torrents(status="paused")
            self.assertEqual("stopped", request.call_args.kwargs["data"]["filter"])

    def test_tr_uses_locked_sdk_transfer_fields_selection_and_limits(self):
        torrent = transmission_rpc.Torrent(fields={
            "id": 17, "name": "Test", "status": 3, "percentDone": 0.25,
            "rateDownload": 2048, "rateUpload": 1024,
            "files": [{"length": 5, "name": "S01E02.mkv", "bytesCompleted": 0}],
            "wanted": [1], "priorities": [0], "labels": ["NASTOOL"],
        })
        adapter = Transmission.__new__(Transmission)
        adapter.trc = transmission_rpc.Client.__new__(transmission_rpc.Client)
        with patch.object(adapter.trc, "get_torrents", return_value=[torrent]):
            results, error = adapter.get_downloading_progress(tag=["NASTOOL"], with_error=True)
            self.assertFalse(error)
            self.assertEqual((17, 25), (results[0]["id"], results[0]["progress"]))
        with patch.object(adapter.trc, "get_torrent", return_value=torrent):
            self.assertEqual("S01E02.mkv", adapter.get_files(17)[0].name)
        with patch.object(adapter.trc, "_request") as request:
            self.assertTrue(adapter.set_files(file_info={17: {0: {"selected": True}, 1: {"selected": False}}}))
            self.assertEqual({"files-wanted": [0], "files-unwanted": [1]}, request.call_args.args[1])
            adapter.set_uploadspeed_limit(17, 5)
            self.assertEqual({"uploadLimit": 5, "uploadLimited": True}, request.call_args.args[1])
            adapter.set_downloadspeed_limit(17, 6)
            self.assertEqual({"downloadLimit": 6, "downloadLimited": True}, request.call_args.args[1])

    def test_brush_looks_up_legacy_ids_only_on_the_original_downloader(self):
        service = BrushTask.__wrapped__.__new__(BrushTask.__wrapped__)
        service.dbhelper = Mock()
        service.dbhelper.get_brushtask_torrents.return_value = [
            SimpleNamespace(id=12, downloader="1", download_id="7", torrent_name="Old", torrent_size="100"),
            SimpleNamespace(id=13, downloader="2", download_id="7", torrent_name="User file", torrent_size="100"),
            SimpleNamespace(id=14, downloader=None, download_id="7"),
        ]
        service.get_downloader_info = lambda owner: {"type": "transmission", "id": owner}
        old_client, new_client = Mock(), Mock()
        old_client.get_torrents.return_value = ([], False)
        new_client.get_torrents.return_value = ([transmission_rpc.Torrent(fields={
            "id": 7, "name": "Different file", "hashString": "a" * 40, "totalSize": 100
        })], False)
        with patch("app.brushtask.Transmission", side_effect=lambda config: {"1": old_client, "2": new_client}[config["id"]]):
            service._clean_task_torrents({"id": 1, "downloader": "2", "name": "Brush"})
        service.dbhelper.delete_brushtask_torrent.assert_called_once_with(12)
        new_client.delete_torrents.assert_not_called()
        old_client.delete_torrents.assert_not_called()

    def test_brush_failed_or_rejected_item_can_be_reconsidered_by_each_task(self):
        service = BrushTask.__wrapped__.__new__(BrushTask.__wrapped__)
        service.get_brushtask_info = Mock(return_value={"rss_url": "url", "rss_rule": {}, "name": "Test"})
        service.get_downloader_info = Mock(return_value={"id": 1})
        service.sites = Mock()
        service.dbhelper = Mock()
        service.dbhelper.is_brushtask_torrent_exists.side_effect = [False, False, False, True]
        service._BrushTask__is_allow_new_torrent = Mock(return_value=True)
        service._BrushTask__check_rss_rule = Mock(side_effect=[False, True, True])
        service._BrushTask__download_torrent = Mock(side_effect=[False, True])
        feed = [{"title": "Test", "enclosure": "item"}]
        with patch("app.brushtask.RssParser.parse_rssxml", return_value=feed):
            for task_id in (1, 2, 2, 2):
                service.check_task_rss(task_id)
        self.assertEqual(3, service._BrushTask__check_rss_rule.call_count)
        self.assertEqual(2, service._BrushTask__download_torrent.call_count)
