import unittest
from unittest.mock import Mock, patch

from app.media.douban import DouBan
from app.media.doubanapi import DoubanApi, DoubanRecommendationError


def response(payload, status=200):
    result = Mock(status_code=status)
    result.json.return_value = payload
    return result


class DoubanRecommendationTest(unittest.TestCase):
    def setUp(self):
        self.api = DoubanApi.__wrapped__()
        self.api._recommend_cache.clear()
        self.api._public_detail_cache.clear()
        self.addCleanup(self.api._recommend_cache.clear)
        self.addCleanup(self.api._public_detail_cache.clear)
        factory = patch("app.media.doubanapi.apiv2.RequestUtils")
        self.addCleanup(factory.stop)
        self.request_factory = factory.start()
        self.http = self.request_factory.return_value
        config = patch("app.media.doubanapi.apiv2.Config", side_effect=AssertionError("Recommendation read credentials"))
        config.start()
        self.addCleanup(config.stop)
        self.douban = object.__new__(DouBan.__wrapped__)
        self.douban.doubanapi = self.api

    def test_public_charts_do_not_require_frodo_credentials(self):
        self.http.get_res.return_value = response({"subject_collection_items": []})
        methods = ["movie_showing", "movie_soon", "movie_hot_gaia", "tv_hot", "tv_animation",
                   "tv_variety_show", "show_hot", "movie_top250", "tv_chinese_best_weekly", "tv_global_best_weekly"]
        for method in methods:
            with self.subTest(method=method):
                self.assertEqual([], getattr(self.api, method)(start=20, count=20)["subject_collection_items"])
                request = self.http.get_res.call_args.kwargs
                self.assertEqual(f"https://m.douban.com/rexxar/api/v2/subject_collection/{method}/items",
                                 request["url"])
                self.assertEqual({"start": 20, "count": 20}, request["params"])
        self.assertEqual(10, self.http.get_res.call_count)

    def test_latest_movies_and_upcoming_movies_use_distinct_endpoints(self):
        movie = {"id": "123", "title": "示例电影", "type": "movie", "year": 2026,
                 "cover": None, "pic": {"large": "https://img.example/poster.jpg"}, "rating": {"value": 8.1}}
        self.http.get_res.side_effect = [response({"items": [movie]}), response({"subject_collection_items": []}),
                                         response({"items": [dict(movie, type="tv")]})]
        result = self.douban.get_douban_latest_movie(page=2)
        self.assertEqual("DB:123", result[0]["id"])
        self.assertEqual("2026", result[0]["year"])
        self.assertEqual("MOV", result[0]["type"])
        latest = self.http.get_res.call_args.kwargs
        self.assertTrue(latest["url"].endswith("/movie/recommend"))
        self.assertEqual({"tags": "", "sort": "R", "start": 20, "count": 20}, latest["params"])
        self.douban.get_douban_new_movie()
        self.assertTrue(self.http.get_res.call_args.kwargs["url"].endswith("/subject_collection/movie_soon/items"))
        self.assertEqual("TV", self.douban.get_douban_latest_tv()[0]["type"])
        self.assertTrue(self.http.get_res.call_args.kwargs["url"].endswith("/tv/recommend"))

    def test_nonempty_success_cache_is_separate_for_pages_and_filters(self):
        self.http.get_res.return_value = response({"items": [{"id": "123"}]})
        first = self.api.movie_recommend(tags="动画", sort="R", start=0, count=20)
        first["items"].clear()
        self.assertEqual([{"id": "123"}], self.api.movie_recommend(tags="动画", sort="R")["items"])
        self.http.get_res.assert_called_once()
        self.api.movie_recommend(tags="动画", sort="R", start=20)
        self.api.movie_recommend(tags="喜剧", sort="R")
        self.api.movie_recommend(tags="动画", sort="T")
        self.assertEqual(4, self.http.get_res.call_count)

    def test_empty_chart_is_valid_but_not_cached(self):
        self.http.get_res.side_effect = [response({"subject_collection_items": []}),
                                         response({"subject_collection_items": [{"id": "new"}]})]
        self.assertEqual([], self.api.movie_showing()["subject_collection_items"])
        self.assertEqual([{"id": "new"}], self.api.movie_showing()["subject_collection_items"])
        self.assertEqual(2, self.http.get_res.call_count)

    def test_failures_are_explicit_and_do_not_poison_retry(self):
        invalid_json = response(None)
        invalid_json.json.side_effect = ValueError("not JSON")
        cases = [None, response({}, status=403), invalid_json, response({"code": 1001, "msg": "denied"}),
                 response({"subject_collection_items": None}), response({"items": []}), response([])]
        for broken in cases:
            with self.subTest(response=broken):
                self.api._recommend_cache.clear()
                self.http.get_res.side_effect = [broken, response({"subject_collection_items": [{"id": "ok"}]})]
                with self.assertRaises(DoubanRecommendationError):
                    self.api.movie_showing()
                self.assertEqual([{"id": "ok"}], self.api.movie_showing()["subject_collection_items"])
                if broken is not None:
                    broken.close.assert_called_once()

    def test_projection_handles_optional_fields_and_skips_non_media(self):
        self.http.get_res.return_value = response({"subject_collection_items": [
            None, "bad", {"title": "Missing ID", "type": "movie"},
            {"id": "book", "title": "书籍", "type": "book"},
            {"id": "123", "title": "剧集", "type": "tv", "rating": {"value": "not scored"},
             "cover": {"url": "https://img.example/s_ratio_poster/a.jpg"}, "pic": None,
             "card_subtitle": "2024 / 中国大陆 / 剧情"},
            {"id": "456", "title": "电影", "type": "movie", "year": 2025,
             "rating": {"value": float("nan")}, "cover": None, "pic": None},
        ]})
        items = self.douban.get_douban_online_movie()
        self.assertEqual(["DB:123", "DB:456"], [item["id"] for item in items])
        self.assertEqual("2024", items[0]["year"])
        self.assertEqual("https://img.example/m_ratio_poster/a.jpg", items[0]["image"])
        self.assertEqual(0, items[0]["vote"])
        self.assertEqual(0, items[1]["vote"])
        self.assertEqual("", items[1]["image"])

    def test_configured_frodo_valid_detail_is_preferred(self):
        payload = {"id": "123", "type": "movie", "title": "已配置来源", "year": "2026"}
        with patch.object(self.api, "_DoubanApi__invoke", return_value=payload) as invoke:
            self.assertEqual(payload, self.api.movie_detail("123"))
            invoke.assert_called_once_with("/movie/123")
        self.http.get_res.assert_not_called()

    def test_public_details_support_movies_and_tv_without_credentials(self):
        with patch("app.media.doubanapi.apiv2.Config") as config:
            config.return_value.get_config.return_value = {}
            for media_type in ("movie", "tv"):
                with self.subTest(media_type=media_type):
                    payload = {"id": "123", "type": media_type, "title": "公开详情", "year": "2026"}
                    self.http.get_res.return_value = response(payload)
                    self.assertEqual(payload, getattr(self.api, f"{media_type}_detail")("123"))
                    self.assertEqual(f"https://m.douban.com/rexxar/api/v2/{media_type}/123",
                                     self.http.get_res.call_args.kwargs["url"])

    def test_public_detail_failures_are_not_cached_and_types_remain_separate(self):
        valid = {"id": "123", "type": "tv", "title": "公开剧集"}
        self.http.get_res.side_effect = [response({}, status=404), response(valid)]
        with patch.object(self.api, "_DoubanApi__invoke", return_value={}):
            self.assertIsNone(self.api.movie_detail("123"))
            returned = self.api.tv_detail("123")
            returned["title"] = "调用方修改"
            self.assertEqual("公开剧集", self.api.tv_detail("123")["title"])
            self.assertEqual(2, self.http.get_res.call_count)
            self.http.get_res.side_effect = [response({}, status=503), response(valid)]
            self.api._public_detail_cache.clear()
            self.assertIsNone(self.api.tv_detail("123"))
            self.assertEqual(valid, self.api.tv_detail("123"))

    def test_public_detail_rejects_other_subjects_and_error_payloads(self):
        invalid_json = response(None)
        invalid_json.json.side_effect = ValueError("invalid")
        with patch.object(self.api, "_DoubanApi__invoke", return_value={}):
            for payload in (None, invalid_json,
                            response({"id": "456", "type": "tv", "title": "其它作品"}),
                            response({"id": "123", "type": "movie", "title": "错误类型"}),
                            response({"id": "123", "type": "tv", "title": "错误", "code": 1001}),
                            response({"id": "123", "type": "tv", "title": ""})):
                with self.subTest(payload=payload):
                    self.http.get_res.return_value = payload
                    self.assertIsNone(self.api.tv_detail("123"))


if __name__ == "__main__":
    unittest.main()
