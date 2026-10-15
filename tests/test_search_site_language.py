import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.indexer import Indexer
from app.indexer.client.builtin import BuiltinIndexer
from app.searcher import Searcher
from app.utils.types import MediaType, SearchType
from web.backend import search_torrents


class SearchSiteLanguageTest(unittest.TestCase):
    def setUp(self):
        self.client = BuiltinIndexer.__new__(BuiltinIndexer)
        self.client.progress = Mock()
        self.client.filter_search_results = Mock(side_effect=lambda **kwargs: kwargs["result_array"])
        self.client._BuiltinIndexer__spider_search = Mock(
            side_effect=lambda **kwargs: [SimpleNamespace(
                title=kwargs["keyword"], res_order=1, site_order=1, seeders=1
            )]
        )
        self.site = SimpleNamespace(id="english", name="English", pri=0, language="en", parser=None)
        self.media = SimpleNamespace(
            en_name="Example", original_title="Original", original_language="en",
            type=MediaType.MOVIE
        )
        patcher = patch("app.indexer.client.builtin.Config")
        patcher.start().return_value.get_config.return_value = {}
        self.addCleanup(patcher.stop)
        patcher = patch("app.indexer.client.builtin.log")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _search(self, keyword="示例", media=True):
        self.client.search(1, self.site, keyword, {}, self.media if media else None, SearchType.WEB)
        return self.client._BuiltinIndexer__spider_search.call_args

    def test_english_site_uses_existing_english_name(self):
        self.assertEqual("Example", self._search().kwargs["keyword"])

    def test_non_chinese_original_name_is_fallback(self):
        self.media.en_name = "示例"
        self.assertEqual("Original", self._search().kwargs["keyword"])

    def test_non_english_site_preserves_chinese_keyword(self):
        self.site.language = None
        self.assertEqual("示例", self._search().kwargs["keyword"])

    def test_explicit_english_keyword_is_preserved(self):
        self.assertEqual("Chosen Query", self._search("Chosen Query").kwargs["keyword"])

    def test_explicit_media_keyword_is_not_replaced_with_title(self):
        self.media.keyword = "自定义 中文关键词"
        self.assertIsNone(self._search(self.media.keyword))
        self.client._BuiltinIndexer__spider_search.assert_not_called()

    def test_missing_searchable_name_keeps_english_site_skipped(self):
        for english_name, original in ((None, None), (" ", "示例"), ("示例", "原名")):
            with self.subTest(english_name=english_name, original=original):
                self.media.en_name = english_name
                self.media.original_title = original
                self.assertIsNone(self._search())
        self.client._BuiltinIndexer__spider_search.assert_not_called()

    def test_unidentified_chinese_keyword_keeps_english_site_skipped(self):
        self.assertIsNone(self._search(media=False))
        self.client._BuiltinIndexer__spider_search.assert_not_called()

    def _prepare_searcher(self):
        indexer = Indexer()
        sites = [
            SimpleNamespace(id="chinese", name="Chinese", pri=0, language=None, parser=None),
            self.site,
            SimpleNamespace(id="english2", name="English2", pri=0, language="en", parser=None),
        ]
        for attribute, value in (("_client", self.client), ("progress", Mock()),
                                 ("get_indexers", Mock(return_value=sites))):
            patcher = patch.object(indexer, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        searcher = Searcher.__new__(Searcher)
        searcher.indexer = indexer
        searcher.progress = Mock()
        searcher.message = Mock()
        searcher.message.get_search_types.return_value = [SearchType.TG]
        searcher.dbhelper = Mock()
        searcher._search_auto = False
        self.media = SimpleNamespace(
            en_name=None, original_title="原名", original_language="ja",
            type=MediaType.MOVIE, tmdb_info={"id": 1}, tmdb_id=1,
            keyword=None, cn_name="示例", title="示例", year="2026", begin_season=None,
            get_episode_list=Mock(return_value=[]), get_title_string=Mock(return_value="示例")
        )
        return searcher

    def _assert_both_languages_searched_once(self):
        calls = self.client._BuiltinIndexer__spider_search.call_args_list
        self.assertEqual(3, len(calls))
        self.assertEqual({"Chinese": "示例", "English": "Example", "English2": "Example"}, {
            item.kwargs["indexer"].name: item.kwargs["keyword"] for item in calls
        })
        self.assertIsNone(self.media.en_name)

    @patch("app.searcher.Config")
    @patch("app.searcher.Media")
    def test_remote_search_prepares_title_once_for_all_sites(self, media_service, config):
        searcher = self._prepare_searcher()
        config.return_value.get_config.return_value = {}
        media_service.return_value.get_tmdb_en_title.return_value = "Example"

        result = searcher.search_one_media(self.media, in_from=SearchType.TG, no_exists={})

        self.assertEqual((None, {}, 3, None), result)
        media_service.return_value.get_tmdb_en_title.assert_called_once_with(self.media)
        self._assert_both_languages_searched_once()

    @patch.object(search_torrents, "DbHelper")
    @patch.object(search_torrents, "ProgressHelper")
    @patch.object(search_torrents, "Config")
    @patch.object(search_torrents, "Media")
    @patch.object(search_torrents, "Searcher")
    def test_web_first_round_includes_english_sites_after_chinese_match(
            self, searcher_class, media_service, config, progress, database):
        searcher_class.return_value = self._prepare_searcher()
        config.return_value.get_config.return_value = {}
        media_service.return_value.get_media_info.return_value = self.media
        media_service.return_value.get_tmdb_en_title.return_value = "Example"

        self.assertEqual((0, ""), search_torrents.search_medias_for_web("示例"))

        media_service.return_value.get_tmdb_en_title.assert_called_once_with(self.media)
        self._assert_both_languages_searched_once()
        self.assertEqual(3, len(database.return_value.insert_search_results.call_args.kwargs["media_items"]))


if __name__ == "__main__":
    unittest.main()
