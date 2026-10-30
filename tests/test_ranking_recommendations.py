import unittest
from unittest.mock import Mock, patch

from app.media.bangumi import Bangumi, BangumiRecommendationError
from app.media.doubanapi import DoubanRecommendationError
from app.media.tmdbv3api import TMDbException
from app.utils.types import MediaType
from web.actions.search import SearchActions
from web.backend.web_utils import WebUtils


class RankingActionsTest(unittest.TestCase):
    def setUp(self):
        self.actions = SearchActions(Mock(), Mock())

    def test_latest_movie_tv_and_coming_soon_keep_distinct_sources(self):
        with patch("web.actions.search.DouBan") as factory:
            for subtype, method in (("dbnewmovie", "get_douban_latest_movie"),
                                    ("dbnewtv", "get_douban_latest_tv"),
                                    ("dbnm", "get_douban_new_movie")):
                with self.subTest(subtype=subtype):
                    factory.return_value.reset_mock()
                    getattr(factory.return_value, method).return_value = [{"id": "DB:1"}]
                    result = self.actions.get_recommend({"type": "MOV", "subtype": subtype, "page": "2"})
                    self.assertEqual({"code": 0, "Items": [{"id": "DB:1"}]}, result)
                    getattr(factory.return_value, method).assert_called_once_with(2)

    def test_douban_unavailable_is_not_a_successful_empty_chart(self):
        with patch("web.actions.search.DouBan") as factory:
            factory.return_value.get_douban_hot_movie.side_effect = DoubanRecommendationError("豆瓣暂不可用")
            self.assertEqual({"code": 1, "msg": "豆瓣暂不可用", "Items": []},
                             self.actions.get_recommend({"type": "MOV", "subtype": "dbhm"}))

    def test_tmdb_missing_configuration_and_upstream_failure_are_recoverable(self):
        with patch("web.actions.search.Media") as factory:
            factory.return_value.movie = None
            result = self.actions.get_recommend({"type": "MOV", "subtype": "hm"})
            self.assertEqual(1, result["code"])
            self.assertIn("TMDB API Key", result["msg"])
            factory.return_value.get_tmdb_hot_movies.assert_not_called()
            factory.return_value.movie = Mock()
            factory.return_value.get_tmdb_hot_movies.side_effect = TMDbException("private upstream URL")
            result = self.actions.get_recommend({"type": "MOV", "subtype": "hm"})
            self.assertEqual(1, result["code"])
            self.assertNotIn("private", result["msg"])
            factory.return_value.tmdb.cache_clear.assert_called_once_with()
            factory.return_value.get_tmdb_hot_movies.side_effect = None
            factory.return_value.get_tmdb_hot_movies.return_value = [{"id": 1}]
            self.assertEqual(0, self.actions.get_recommend({"type": "MOV", "subtype": "hm"})["code"])

    def test_tmdb_popular_and_trending_preserve_the_requested_page(self):
        with patch("web.actions.search.Media") as factory:
            for media_type, subtype, method in (("MOV", "hm", "get_tmdb_hot_movies"),
                                               ("TV", "ht", "get_tmdb_hot_tvs"),
                                               ("TRENDING", "tmdb", "get_tmdb_trending_all_week")):
                with self.subTest(subtype=subtype):
                    getattr(factory.return_value, method).return_value = [{"id": 1}]
                    result = self.actions.get_recommend({"type": media_type, "subtype": subtype, "page": 3})
                    self.assertEqual({"code": 0, "Items": [{"id": 1}]}, result)
                    getattr(factory.return_value, method).assert_called_once_with(3)

    def test_invalid_page_is_reported_before_loading_a_source(self):
        with patch("web.actions.search.DouBan") as source:
            for page in ("bad", -1, 10001):
                self.assertEqual(1, self.actions.get_recommend({"type": "MOV", "subtype": "dbhm", "page": page})["code"])
            source.assert_not_called()

    def test_douban_card_without_a_tmdb_match_can_fall_back_to_keyword_search(self):
        with patch("web.backend.web_utils.DouBan") as douban, patch("web.backend.web_utils.Media") as media:
            douban.return_value.get_douban_detail.return_value = {
                "title": "示例电影", "original_title": "Example Movie", "year": "2026"}
            media.return_value.get_media_info.return_value = None
            self.assertIsNone(WebUtils.get_mediainfo_from_id(MediaType.MOVIE, "DB:123"))
            self.assertEqual(2, media.return_value.get_media_info.call_count)


class BangumiRankingTest(unittest.TestCase):
    def setUp(self):
        Bangumi._calendar_cache.clear()
        self.addCleanup(Bangumi._calendar_cache.clear)
        self.service = Bangumi()

    def test_calendar_paginates_across_weekdays_without_overlap(self):
        calendar = [{"weekday": {"id": day, "cn": f"星期{day}"}, "items": [
            {"id": day * 100 + index, "name_cn": "", "name": f"Anime {day}-{index}"}
            for index in range(10)]} for day in range(1, 8)]
        with patch.object(self.service, "calendar", return_value=calendar):
            pages = [self.service.get_bangumi_calendar(page=page) for page in range(1, 5)]
            self.assertEqual([30, 30, 10, 0], [len(page) for page in pages])
            ids = [item["id"] for page in pages for item in page]
            self.assertEqual(70, len(set(ids)))
            self.assertEqual("Anime 1-0", pages[0][0]["title"])
            weekday = self.service.get_bangumi_calendar(week="3")
            self.assertEqual(10, len(weekday))
            self.assertTrue(all(item["weekday"] == "星期3" for item in weekday))

    def test_failed_and_empty_calendars_are_not_cached(self):
        empty = Mock(status_code=200)
        empty.json.return_value = []
        valid = Mock(status_code=200)
        valid.json.return_value = [{"weekday": {"id": 1}, "items": [{"id": 1, "name": "Anime"}]}]
        with patch.object(Bangumi._req, "get_res", side_effect=[None, empty, valid]) as request:
            with self.assertRaises(BangumiRecommendationError):
                self.service.calendar()
            self.assertEqual([], self.service.calendar())
            self.assertEqual(1, len(self.service.calendar()))
            self.assertEqual(1, len(self.service.calendar()))
            self.assertEqual(3, request.call_count)

    def test_invalid_calendar_and_week_are_explicit_errors(self):
        response = Mock(status_code=200)
        response.json.return_value = {"error": "unavailable"}
        with patch.object(Bangumi._req, "get_res", return_value=response):
            with self.assertRaises(BangumiRecommendationError):
                self.service.calendar()
        with patch.object(self.service, "calendar") as request:
            with self.assertRaises(BangumiRecommendationError):
                self.service.get_bangumi_calendar(week="8")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
