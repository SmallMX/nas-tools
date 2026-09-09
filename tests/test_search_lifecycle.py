import unittest
from unittest.mock import Mock, call, patch

from app.searcher import Searcher
from app.utils.types import MediaType, SearchType
from web.backend import search_torrents


class WebSearchLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.progress = self._patch("ProgressHelper").return_value
        self.searcher = self._patch("Searcher").return_value
        self.database = self._patch("DbHelper").return_value
        self.media = self._patch("Media").return_value
        self._patch("log")
        self._patch("StringUtils").get_keyword_from_string.return_value = (
            None, "Example", None, None, None, "Example"
        )
        self.result = Mock(title="Example", res_order=1, site_order=1, seeders=1)
        self.searcher.search_medias.return_value = [self.result]

    def _patch(self, name):
        patcher = patch.object(search_torrents, name)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_success_ends_progress_after_results_are_saved(self):
        events = Mock()
        events.attach_mock(self.progress.start, "start")
        events.attach_mock(self.database.insert_search_results, "save")
        events.attach_mock(self.progress.end, "end")

        result = search_torrents.search_medias_for_web("Example", ident_flag=False)

        self.assertEqual((0, ""), result)
        self.assertEqual([
            call.start("search"),
            call.save(media_items=[self.result], ident_flag=False, title="Example"),
            call.end("search"),
        ], events.mock_calls)

    def test_empty_results_end_progress(self):
        self.searcher.search_medias.return_value = []

        result = search_torrents.search_medias_for_web("Example", ident_flag=False)

        self.assertEqual((1, "Example 未检索到任何资源"), result)
        self.progress.start.assert_called_once_with("search")
        self.progress.end.assert_called_once_with("search")
        self.database.insert_search_results.assert_not_called()

    def test_failures_end_progress_and_preserve_original_exception(self):
        failures = (
            (self.media.get_media_info, True),
            (self.searcher.search_medias, False),
            (self.database.delete_all_search_torrents, False),
            (self.database.insert_search_results, False),
        )
        for operation, identify in failures:
            with self.subTest(operation=operation):
                self.progress.reset_mock()
                error = RuntimeError("search operation failed")
                operation.side_effect = error
                try:
                    with self.assertRaises(RuntimeError) as raised:
                        search_torrents.search_medias_for_web("Example", ident_flag=identify)
                finally:
                    operation.side_effect = None
                self.assertIs(error, raised.exception)
                self.progress.start.assert_called_once_with("search")
                self.progress.end.assert_called_once_with("search")

    def test_secondary_name_failure_ends_restarted_progress(self):
        media = Mock(
            tmdb_info={"id": 1}, type=MediaType.MOVIE, begin_season=None,
            cn_name="示例", en_name="Example", year="2026"
        )
        media.get_episode_list.return_value = []
        self.media.get_media_info.return_value = media
        self._patch("Config").return_value.get_config.return_value = {}
        self.searcher.search_medias.side_effect = [[], RuntimeError("retry failed")]

        with self.assertRaisesRegex(RuntimeError, "retry failed"):
            search_torrents.search_medias_for_web("Example")

        self.assertEqual([call("search"), call("search")], self.progress.start.call_args_list)
        self.progress.end.assert_called_once_with("search")
        self.database.delete_all_search_torrents.assert_not_called()


class RemoteSearchLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.searcher = Searcher.__new__(Searcher)
        self.searcher.progress = Mock()
        self.searcher.dbhelper = Mock()
        self.searcher.downloader = Mock()
        self.searcher.message = Mock()
        self.searcher.message.get_search_types.return_value = [SearchType.TG]
        self.searcher._search_auto = True
        self.media = Mock(
            title="Example", keyword="Example", type=MediaType.MOVIE,
            year="2026", begin_season=None, res_order=1, site_order=1, seeders=1
        )
        self.media.get_episode_list.return_value = []
        self.searcher.search_medias = Mock(return_value=[self.media])
        self.searcher.downloader.batch_download.return_value = ([self.media], {})
        patcher = patch("app.searcher.log")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _search(self):
        return self.searcher.search_one_media(
            self.media, in_from=SearchType.TG, no_exists={}
        )

    def _assert_progress_ended(self):
        self.searcher.progress.start.assert_called_once_with("search")
        self.searcher.progress.end.assert_called_once_with("search")

    def test_missing_media_does_not_touch_another_search_progress(self):
        result = self.searcher.search_one_media(
            None, in_from=SearchType.TG, no_exists={}
        )

        self.assertEqual((None, {}, 0, 0), result)
        self.searcher.progress.start.assert_not_called()
        self.searcher.progress.end.assert_not_called()

    def test_empty_results_end_progress(self):
        self.searcher.search_medias.return_value = []

        self.assertEqual((None, {}, 0, 0), self._search())

        self._assert_progress_ended()
        self.searcher.downloader.batch_download.assert_not_called()

    def test_success_ends_progress_after_download_finishes(self):
        events = Mock()
        events.attach_mock(self.searcher.downloader.batch_download, "download")
        events.attach_mock(self.searcher.progress.end, "end")

        self.assertEqual((self.media, {}, 1, 1), self._search())

        self._assert_progress_ended()
        self.assertEqual([
            call.download(in_from=SearchType.TG, media_list=[self.media],
                          need_tvs={}, user_name=None),
            call.end("search"),
        ], events.mock_calls)

    def test_auto_download_disabled_ends_progress_after_saving(self):
        self.searcher._search_auto = False

        self.assertEqual((None, {}, 1, None), self._search())

        self._assert_progress_ended()
        self.searcher.dbhelper.insert_search_results.assert_called_once_with([self.media])
        self.searcher.downloader.batch_download.assert_not_called()

    def test_failures_end_progress_and_preserve_original_exception(self):
        operations = (
            self.media.get_episode_list,
            self.searcher.search_medias,
            self.searcher.dbhelper.insert_search_results,
            self.searcher.downloader.batch_download,
        )
        for operation in operations:
            with self.subTest(operation=operation):
                self.searcher.progress.reset_mock()
                error = RuntimeError("search operation failed")
                operation.side_effect = error
                try:
                    with self.assertRaises(RuntimeError) as raised:
                        self._search()
                finally:
                    operation.side_effect = None
                self.assertIs(error, raised.exception)
                self._assert_progress_ended()


if __name__ == "__main__":
    unittest.main()
