import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.utils.types import SearchType
from web.actions.download import DownloadActions
from web.actions.search import SearchActions


def search_row(row_id, **changes):
    values = dict(
        id=row_id, title="Show", year="2024", type="TV", es_string="S01 E01",
        res_type=json.dumps({"respix": "1080p", "restype": "WEB-DL", "video_encode": "H264", "reseffect": "HDR"}),
        size="1 GB", otherinfo="Team", seeders=5, enclosure=f"https://tracker.example/{row_id}",
        site="A", torrent_name=f"Show.{row_id}", description="description", pageurl="https://tracker.example/detail",
        upload_volume_factor=1.0, download_volume_factor=1.0, tmdbid=42,
        image="backdrop", poster="poster", overview="overview", vote="8",
    )
    values.update(changes)
    return SimpleNamespace(**values)


class SearchActionContractTest(unittest.TestCase):
    def setUp(self):
        self.database = Mock()
        self.downloads = DownloadActions(self.database)
        self.actions = SearchActions(self.database, self.downloads)

    def test_search_groups_keep_counts_filters_and_season_order(self):
        self.database.get_search_results.return_value = [
            search_row(1),
            search_row(2, site="B", upload_volume_factor=2.0, download_volume_factor=0.0, poster="later poster"),
            search_row(3, res_type=json.dumps({"respix": "1080p", "restype": "WEB-DL", "video_encode": "H265", "reseffect": "HDR"})),
            search_row(4, site="C", download_volume_factor=0.5,
                       res_type=json.dumps({"respix": "720p", "restype": "WEB-DL", "video_encode": "H264"})),
            search_row(5, es_string="S02"),
            search_row(6, site="B", es_string="S01 E02"),
            search_row(7, title="Movie", type="MOV", es_string="ignored", year=None, tmdbid=None, res_type=""),
            search_row(8, title="Broken", res_type="{broken"),
        ]
        with patch("web.actions.search.ExceptionUtils.exception_traceback") as report:
            result = self.actions.get_search_result()

        self.assertEqual(0, result["code"])
        self.assertEqual(8, result["total"])
        self.assertEqual(["Show (2024)", "Movie"], list(result["result"]))
        show = result["result"]["Show (2024)"]
        self.assertEqual("poster", show["poster"])
        self.assertIs(False, show["exist"])
        self.assertEqual(["S02", "S01 E02", "S01 E01"], [key for key, _ in show["torrent_dict"]])
        self.assertEqual(["A", "B", "C"], show["filter"]["site"])
        self.assertEqual(["H264", "H265"], show["filter"]["video"])
        self.assertEqual(["S02", "S01"], show["filter"]["season"])
        self.assertEqual(["1.0 1.0", "2.0 0.0", "1.0 0.5"],
                         [item["value"] for item in show["filter"]["free"]])
        episode = dict(show["torrent_dict"])["S01 E01"]
        self.assertEqual(["1080p_webdl", "720p_webdl"], list(episode))
        self.assertEqual(3, episode["1080p_webdl"]["group_total"])
        self.assertEqual([[1, 2], [3]], [
            [torrent["id"] for torrent in unique["torrent_list"]]
            for unique in episode["1080p_webdl"]["group_torrents"].values()
        ])
        self.assertEqual(1, episode["720p_webdl"]["group_total"])
        movie = result["result"]["Movie"]
        self.assertEqual(["MOV"], [key for key, _ in movie["torrent_dict"]])
        self.assertEqual([], movie["filter"]["season"])
        self.assertEqual([], movie["filter"]["video"])
        report.assert_called_once()

    def test_empty_search_results_keep_the_public_shape(self):
        self.database.get_search_results.return_value = []
        self.assertEqual({"code": 0, "total": 0, "result": {}}, self.actions.get_search_result())

    def test_download_history_recommendation_delegates_to_download_actions(self):
        self.database.get_download_history.return_value = [SimpleNamespace(
            tmdbid=7, title="Movie", type="电影", year="2024", vote="8", poster="poster",
            torrent="Movie.2024", date="2026-10-15", site="A",
        )]
        with patch.object(self.downloads, "get_downloaded", wraps=self.downloads.get_downloaded) as history:
            result = self.actions.get_recommend({"type": "DOWNLOADED", "page": "2"})

        history.assert_called_once_with({"page": 2})
        self.database.get_download_history.assert_called_once_with(page=2)
        self.assertEqual({"code": 0, "Items": [{
            "id": 7, "orgid": 7, "tmdbid": 7, "title": "Movie", "type": "MOV", "media_type": "电影",
            "year": "2024", "vote": "8", "image": "poster", "overview": "Movie.2024",
            "date": "2026-10-15", "site": "A",
        }]}, result)


class DownloadActionContractTest(unittest.TestCase):
    def setUp(self):
        self.database = Mock()
        self.actions = DownloadActions(self.database)
        self.downloader_factory = self._patch("web.actions.download.Downloader")
        self.downloader = self.downloader_factory.return_value
        self.media_factory = self._patch("web.actions.download.Media")
        self.media_service = self.media_factory.return_value
        self.message_factory = self._patch("web.actions.download.Message")
        self.message = self.message_factory.return_value
        self._patch("web.actions.download.current_user", SimpleNamespace(username="tester"))

    def _patch(self, target, value=None):
        patcher = patch(target) if value is None else patch(target, value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_torrent_controls_keep_validation_results_and_operation_options(self):
        cases = (
            (self.actions.pt_start, "start_torrents", "下载器未能启动任务", {}),
            (self.actions.pt_stop, "stop_torrents", "下载器未能停止任务", {}),
            (self.actions.pt_remove, "delete_torrents", "下载器未能删除任务", {"delete_file": True}),
        )
        for action, operation, failure, options in cases:
            for data in (None, [], {}, {"id": ""}):
                with self.subTest(action=action.__name__, data=data):
                    self.downloader_factory.reset_mock()
                    tid = data.get("id") if isinstance(data, dict) else None
                    self.assertEqual({"retcode": 1, "retmsg": "下载任务 ID 不能为空", "id": tid}, action(data))
                    self.downloader_factory.assert_not_called()
            for success in (False, True):
                with self.subTest(action=action.__name__, success=success):
                    method = getattr(self.downloader, operation)
                    method.reset_mock()
                    method.return_value = success
                    expected = {"retcode": 0, "id": "hash"} if success else {
                        "retcode": 1, "retmsg": failure, "id": "hash",
                    }
                    self.assertEqual(expected, action({"id": "hash"}))
                    method.assert_called_once_with(ids="hash", **options)

    def test_search_result_download_keeps_response_and_success_only_notification(self):
        self.database.get_search_result_by_id.return_value = [search_row(1)]
        for success in (False, True):
            with self.subTest(success=success):
                media = Mock()
                self.media_service.get_media_info.return_value = media
                self.downloader.download.reset_mock()
                self.downloader.download.return_value = (success, "" if success else "拒绝")
                self.message_factory.reset_mock()

                result = self.actions.download({"id": 1, "dir": "/downloads", "setting": "7"})

                self.assertEqual({"retcode": 0, "retmsg": ""} if success else
                                 {"retcode": -1, "retmsg": "拒绝"}, result)
                self.downloader.download.assert_called_once_with(
                    media_info=media, download_dir="/downloads", download_setting="7"
                )
                if success:
                    self.assertEqual("tester", media.user_name)
                    self.message.send_download_message.assert_called_once_with(in_from=SearchType.WEB, can_item=media)
                else:
                    self.message_factory.assert_not_called()
                self.message.send_download_fail_message.assert_not_called()

    def test_download_link_keeps_response_fallback_and_success_only_notification(self):
        sites = self._patch("web.actions.validation.Sites")
        sites.return_value.get_sites.return_value = [{"name": "A", "signurl": "https://tracker.example/"}]
        for success, error in ((True, ""), (False, "拒绝"), (False, "")):
            with self.subTest(success=success, error=error):
                media = Mock()
                self.media_service.get_media_info.return_value = media
                self.downloader.download.reset_mock()
                self.downloader.download.return_value = (success, error)
                self.message_factory.reset_mock()

                result = self.actions.download_link({
                    "site": "A", "enclosure": "https://tracker.example/download", "title": "Movie",
                    "dl_dir": "/downloads", "dl_setting": "7",
                })

                self.assertEqual({"code": 0, "msg": "下载成功"} if success else {
                    "code": 1, "msg": error or "如连接正常，请检查下载任务是否存在",
                }, result)
                self.downloader.download.assert_called_once_with(
                    media_info=media, download_dir="/downloads", download_setting="7"
                )
                if success:
                    self.message.send_download_message.assert_called_once_with(SearchType.WEB, media)
                else:
                    self.message_factory.assert_not_called()
                self.message.send_download_fail_message.assert_not_called()

    def test_uploaded_torrent_and_magnet_keep_batch_results_notifications_and_cleanup(self):
        magnet = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=Other"
        config = self._patch("web.actions.download.Config")
        for outcomes in ((True, True), (False, False), (True, False)):
            with self.subTest(outcomes=outcomes), tempfile.TemporaryDirectory() as directory:
                file_path = Path(directory) / "Example.torrent"
                file_path.write_bytes(b"torrent")
                config.return_value.get_temp_path.return_value = directory
                file_media, magnet_media = Mock(), Mock()
                self.media_service.get_media_info.side_effect = [file_media, magnet_media]
                self.downloader.download.reset_mock()
                self.downloader.download.side_effect = [(success, "" if success else "拒绝") for success in outcomes]
                self.message_factory.reset_mock()

                result = self.actions.download_torrent({
                    "files": [{"upload": {"filename": "Example.torrent"}}], "magnets": [magnet],
                    "dl_dir": "/downloads", "dl_setting": "7",
                })

                failures = [f"{label} 1: 拒绝" for label, success in zip(("文件", "磁链"), outcomes) if not success]
                count = sum(outcomes)
                expected = {"code": 0, "msg": "成功添加 2 个下载任务"} if not failures else {
                    "code": 1, "msg": f"成功 {count} 项，失败 {len(failures)} 项：" + "；".join(failures),
                    "success_count": count, "failures": failures,
                }
                self.assertEqual(expected, result)
                self.assertFalse(file_path.exists())
                calls = self.downloader.download.call_args_list
                self.assertEqual(2, len(calls))
                self.assertEqual(str(file_path.resolve()), calls[0].kwargs["torrent_file"])
                self.assertIsNone(calls[1].kwargs["torrent_file"])
                for media, success in zip((file_media, magnet_media), outcomes):
                    self.assertEqual("WEB", media.site)
                    self.assertEqual("tester", media.user_name)
                    if success:
                        self.message.send_download_message.assert_any_call(SearchType.WEB, media)
                    else:
                        self.message.send_download_fail_message.assert_any_call(media, "拒绝")
                self.assertEqual(count, self.message.send_download_message.call_count)
                self.assertEqual(2 - count, self.message.send_download_fail_message.call_count)

    def test_file_and_url_rejections_happen_before_downloader_access(self):
        config = self._patch("web.actions.download.Config")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "uploads"
            root.mkdir()
            outside = Path(directory) / "outside.torrent"
            outside.write_bytes(b"torrent")
            (root / "linked.torrent").symlink_to(outside)
            config.return_value.get_temp_path.return_value = str(root)
            result = self.actions.download_torrent({
                "files": [{"upload": {"filename": "../outside.torrent"}},
                          {"upload": {"filename": "linked.torrent"}}],
                "magnets": ["http://127.0.0.1/private"],
            })
            self.assertEqual(1, result["code"])
            self.assertEqual(0, result["success_count"])
            self.assertEqual(3, len(result["failures"]))
            self.assertTrue(outside.exists())
            self.assertTrue((root / "linked.torrent").is_symlink())
        sites = self._patch("web.actions.validation.Sites")
        sites.return_value.get_sites.return_value = [{"name": "A", "signurl": "https://tracker.example/"}]
        for url in ("http://127.0.0.1/private", "https://tracker.example:8443/download", "file:///tmp/item"):
            with self.subTest(url=url):
                self.assertEqual(-1, self.actions.download_link({
                    "site": "A", "enclosure": url, "title": "Movie",
                })["code"])
        self.downloader_factory.assert_not_called()
        self.media_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
