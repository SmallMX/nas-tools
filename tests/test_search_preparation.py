import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.searcher import Searcher
from app.utils.types import MediaType, SearchType
from web.backend import search_torrents


class SearchPreparationTest(unittest.TestCase):
    """从现有 Web/TG 入口核对搜索准备契约，不依赖内部辅助方法。"""

    def setUp(self):
        self.searcher = Searcher.__new__(Searcher)
        self.searcher.progress = Mock()
        self.searcher.dbhelper = Mock()
        self.searcher.downloader = Mock()
        self.searcher.message = Mock()
        self.searcher.message.get_search_types.return_value = [SearchType.TG]
        self.searcher.search_medias = Mock()
        self.searcher._search_auto = False
        self.media_service = Mock()
        self.searcher.media = self.media_service
        self.config = Mock()
        self.config.get_config.return_value = {"search_en_title": False}
        for module in ("app.searcher", "web.backend.search_torrents"):
            self._patch(f"{module}.Media", Mock(return_value=self.media_service))
            # 两个旧入口都可能读取配置；共用实现后允许入口移除直接导入。
            self._patch(f"{module}.Config", Mock(return_value=self.config), create=True)
            self._patch(f"{module}.log")
        self._patch("web.backend.search_torrents.Searcher", Mock(return_value=self.searcher))
        self.web_database = self._patch("web.backend.search_torrents.DbHelper").return_value
        self._patch("web.backend.search_torrents.ProgressHelper", Mock(return_value=self.searcher.progress))
        self.parse_keyword = self._patch("web.backend.search_torrents.StringUtils.get_keyword_from_string")
        self.parse_keyword.return_value = (MediaType.MOVIE, "输入标题", None, None, "2024", "规范输入标题")
        self.result = SimpleNamespace(title="结果", res_order=1, site_order=1, seeders=1)

    def _patch(self, target, value=None, **kwargs):
        patcher = patch(target, value, **kwargs) if value is not None else patch(target, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    @staticmethod
    def _media(**overrides):
        values = dict(
            title="识别标题", cn_name="中文标题", en_name="English Title", keyword=None,
            original_title="原始标题", original_language="ja", year="2026",
            type=MediaType.TV, begin_season=None, begin_episode=None,
            tmdb_info={"id": 1}, tmdb_id=1,
        )
        values.update(overrides)
        media = SimpleNamespace(**values)
        media.get_season_list = lambda: [media.begin_season] if media.begin_season is not None else []
        media.get_episode_list = lambda: [media.begin_episode] if media.begin_episode is not None else []
        media.get_title_string = lambda: media.title
        return media

    def _responses(self, *rounds):
        self.searcher.search_medias.reset_mock()
        self.searcher.search_medias.side_effect = rounds
        self.media_service.reset_mock()
        self.searcher.dbhelper.reset_mock()
        self.web_database.reset_mock()
        self.searcher.downloader.reset_mock()

    def _run(self, channel, media, **kwargs):
        if channel == "web":
            self.media_service.get_media_info.return_value = media
            return search_torrents.search_medias_for_web("原始输入", **kwargs)
        return self.searcher.search_one_media(media, in_from=SearchType.TG, no_exists={}, **kwargs)

    def _keywords(self):
        return [item.kwargs["key_word"] for item in self.searcher.search_medias.call_args_list]

    def test_language_preference_retries_only_after_empty_first_round(self):
        for channel in ("web", "tg"):
            for prefer_english in (False, True):
                for first_matches in (False, True):
                    with self.subTest(channel=channel, english=prefer_english, first_matches=first_matches):
                        self.config.get_config.return_value = {"search_en_title": prefer_english}
                        self._responses([self.result] if first_matches else [], [self.result])
                        result = self._run(channel, self._media())
                        names = ["English Title", "中文标题"] if prefer_english else ["中文标题", "English Title"]
                        self.assertEqual(names[:1] if first_matches else names, self._keywords())
                        self.assertEqual((0, "") if channel == "web" else (None, {}, 1, None), result)
                        self.media_service.get_tmdb_en_title.assert_not_called()

    def test_same_or_missing_alternate_name_is_searched_once(self):
        for channel in ("web", "tg"):
            for english_name in ("中文标题", None):
                with self.subTest(channel=channel, english_name=english_name):
                    self._responses([])
                    self.media_service.get_tmdb_en_title.return_value = None
                    result = self._run(channel, self._media(en_name=english_name))
                    self.assertEqual(["中文标题"], self._keywords())
                    if channel == "web":
                        self.assertEqual(1, result[0])
                        self.web_database.delete_all_search_torrents.assert_called_once_with()
                    else:
                        self.assertEqual((None, {}, 0, 0), result)
                        self.searcher.dbhelper.delete_all_search_torrents.assert_not_called()
                    self.searcher.downloader.batch_download.assert_not_called()

    def test_missing_chinese_name_uses_recognized_title(self):
        for channel in ("web", "tg"):
            with self.subTest(channel=channel):
                self._responses([self.result])
                self._run(channel, self._media(cn_name=None))
                self.assertEqual(["识别标题"], self._keywords())

    def test_explicit_keyword_is_remote_only_and_has_no_fallback(self):
        for channel in ("web", "tg"):
            with self.subTest(channel=channel):
                self.config.get_config.return_value = {"search_en_title": True}
                self._responses([], [])
                self.media_service.get_tmdb_en_title.return_value = "English Lookup"
                media = self._media(keyword="自定义关键词", en_name=None)
                self._run(channel, media)
                self.assertEqual(["English Lookup", "中文标题"] if channel == "web" else ["自定义关键词"], self._keywords())
                if channel == "web":
                    self.media_service.get_tmdb_en_title.assert_called_once_with(media)
                else:
                    self.media_service.get_tmdb_en_title.assert_not_called()

    def test_english_name_is_resolved_once_without_mutating_original_media(self):
        for channel in ("web", "tg"):
            for language in ("ja", "en"):
                with self.subTest(channel=channel, language=language):
                    self._responses([], [self.result])
                    self.media_service.get_tmdb_en_title.return_value = "English Lookup"
                    media = self._media(en_name=None, original_language=language, original_title="Original English")
                    original = vars(media).copy()
                    self._run(channel, media)
                    expected_english = "English Lookup" if language == "ja" else "Original English"
                    self.assertEqual(["中文标题", expected_english], self._keywords())
                    calls = self.searcher.search_medias.call_args_list
                    first_media = calls[0].kwargs["match_media"]
                    self.assertIsNot(media, first_media)
                    self.assertEqual(expected_english, first_media.en_name)
                    self.assertIs(first_media, calls[1].kwargs["match_media"])
                    self.assertEqual(original, vars(media))
                    if language == "ja":
                        self.media_service.get_tmdb_en_title.assert_called_once_with(media)
                    else:
                        self.media_service.get_tmdb_en_title.assert_not_called()

    def test_media_filters_preserve_channel_defaults_and_episode_season_fallback(self):
        for channel in ("web", "tg"):
            for season, episode, expected_season in ((None, 3, [1]), (2, None, [2]), (None, None, None)):
                with self.subTest(channel=channel, season=season, episode=episode):
                    self._responses([self.result])
                    media = self._media(begin_season=season, begin_episode=episode)
                    self._run(channel, media)
                    expected = {"season": expected_season, "episode": [episode] if episode else [],
                                "year": "2026", "type": MediaType.TV}
                    if channel == "tg":
                        expected.update(site=None, seeders=True)
                    args = self.searcher.search_medias.call_args.kwargs
                    self.assertEqual(expected, args["filter_args"])
                    self.assertEqual(SearchType.WEB if channel == "web" else SearchType.TG, args["in_from"])

    def test_explicit_filters_override_media_and_remote_defaults(self):
        filters = {"season": [4], "episode": [7], "year": "2020", "type": MediaType.MOVIE,
                   "site": ["override-site"], "seeders": False, "quality": "2160p"}
        original = filters.copy()
        for channel in ("web", "tg"):
            with self.subTest(channel=channel):
                self._responses([], [self.result])
                kwargs = {"sites": ["initial-site"]} if channel == "tg" else {}
                self._run(channel, self._media(begin_season=2, begin_episode=3), filters=filters, **kwargs)
                self.assertEqual(2, self.searcher.search_medias.call_count)
                for call in self.searcher.search_medias.call_args_list:
                    self.assertEqual(original, call.kwargs["filter_args"])
                self.assertEqual(original, filters)

    def test_web_identification_applies_parsed_episode_and_explicit_media_type(self):
        self.parse_keyword.return_value = (MediaType.TV, "分词", 3, 4, "2025", "规范输入标题")
        self._responses([self.result])
        self._run("web", self._media(type=MediaType.MOVIE), media_type=MediaType.MOVIE)
        self.media_service.get_media_info.assert_called_once_with(mtype=MediaType.MOVIE, title="规范输入标题")
        self.assertEqual({"season": [3], "episode": [4], "year": "2026", "type": MediaType.MOVIE},
                         self.searcher.search_medias.call_args.kwargs["filter_args"])

    def test_web_fast_search_and_failed_identification_use_parsed_filters_without_matching(self):
        self.parse_keyword.return_value = (MediaType.TV, "快速关键词", 2, 4, "2025", "规范输入标题")
        for identify, media in ((False, None), (True, None), (True, self._media(tmdb_info={}))):
            with self.subTest(identify=identify, recognized=media is not None):
                self._responses([self.result])
                result = self._run("web", media, ident_flag=identify, filters={"site": ["manual"]})
                self.assertEqual((0, ""), result)
                self.assertEqual(["快速关键词"], self._keywords())
                args = self.searcher.search_medias.call_args.kwargs
                self.assertIsNone(args["match_media"])
                self.assertEqual({"season": 2, "episode": 4, "year": "2025", "site": ["manual"]}, args["filter_args"])
                self.media_service.get_tmdb_en_title.assert_not_called()
                if not identify:
                    self.media_service.get_media_info.assert_not_called()
                self.web_database.insert_search_results.assert_called_once_with(
                    media_items=[self.result], ident_flag=False, title="规范输入标题")

    def test_web_and_remote_keep_distinct_result_order_and_persistence_contracts(self):
        first = SimpleNamespace(title="A", res_order=3, site_order=1, seeders=2)
        second = SimpleNamespace(title="A", res_order=3, site_order=2, seeders=1)
        third = SimpleNamespace(title="A", res_order=2, site_order=9, seeders=100)
        seeded = SimpleNamespace(title="A", res_order=3, site_order=1, seeders=5)
        last = SimpleNamespace(title="Z", res_order=1, site_order=0, seeders=1)
        items = [first, third, last, seeded, second]
        for channel in ("web", "tg"):
            with self.subTest(channel=channel):
                self._responses(items)
                self.searcher._search_auto = channel == "web"
                result = self._run(channel, self._media())
                if channel == "web":
                    self.assertEqual((0, ""), result)
                    self.web_database.delete_all_search_torrents.assert_called_once_with()
                    self.web_database.insert_search_results.assert_called_once_with(
                        media_items=[second, seeded, first, third, last], ident_flag=True, title="规范输入标题")
                else:
                    self.assertEqual((None, {}, 5, None), result)
                    self.searcher.dbhelper.delete_all_search_torrents.assert_called_once_with()
                    self.searcher.dbhelper.insert_search_results.assert_called_once_with([last, second, seeded, first, third])
                self.searcher.downloader.batch_download.assert_not_called()
                self.assertEqual([first, third, last, seeded, second], items)

    def test_remote_auto_download_keeps_counts_missing_items_and_user_context(self):
        self.searcher._search_auto = True
        requested = {2: [3, 4]}
        remaining = {2: [4]}
        cases = (([], requested, (None, requested, 1, 0)),
                 ([self.result], remaining, (None, remaining, 1, 1)),
                 ([self.result], {}, (self.result, requested, 1, 1)))
        for downloaded, left, expected in cases:
            with self.subTest(downloaded=len(downloaded), left=left):
                self._responses([self.result])
                self.searcher.downloader.batch_download.return_value = (downloaded, left)
                result = self.searcher.search_one_media(self._media(), in_from=SearchType.TG,
                                                       no_exists=requested, user_name="测试用户")
                self.assertEqual(expected, result)
                self.searcher.downloader.batch_download.assert_called_once_with(
                    in_from=SearchType.TG, media_list=[self.result], need_tvs=requested, user_name="测试用户")
                self.searcher.dbhelper.insert_search_results.assert_called_once_with([self.result])


if __name__ == "__main__":
    unittest.main()
