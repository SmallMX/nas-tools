import copy
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from app.media.streaming import StreamingDiscovery, StreamingDiscoveryError
from web.actions.search import SearchActions


def response(payload, status=200):
    result = Mock(status_code=status, ok=200 <= status < 300)
    result.json.return_value = payload
    return result


def tencent_page(items, has_more=True, context=None):
    return {
        "ret": 0,
        "data": {
            "has_next_page": has_more,
            "next_page_context": context or {},
            "module_list_datas": [{"module_datas": [{"item_data_lists": {
                "item_datas": [{"item_type": "2", "item_params": item} for item in items],
            }}]}],
        },
    }


def iqiyi_item(album_id=123, **changes):
    item = {
        "albumId": album_id, "channelId": 2, "name": "示例剧集", "title": "示例剧集",
        "imageUrl": "https://pic1.iqiyipic.com/image/a_poster.jpg", "period": "2026-10-01",
        "description": "故事简介", "score": 8.2, "playUrl": "https://www.iqiyi.com/v_example.html",
    }
    item.update(changes)
    return item


class StreamingDiscoveryTest(unittest.TestCase):
    def setUp(self):
        StreamingDiscovery._cache.clear()
        self.addCleanup(StreamingDiscovery._cache.clear)
        factory = patch("app.media.streaming.RequestUtils")
        self.addCleanup(factory.stop)
        self.request_factory = factory.start()
        self.http = self.request_factory.return_value
        self.discovery = StreamingDiscovery()

    def test_invalid_inputs_are_rejected_before_network_access(self):
        cases = [
            ("unknown", 1, {}),
            ("https://example.com", 1, {}),
            ("iqiyi", 0, {}),
            ("iqiyi", -1, {}),
            ("iqiyi", 11, {}),
            ("iqiyi", "bad", {}),
            ("iqiyi", 1, []),
            ("iqiyi", 1, {"category": "documentary"}),
            ("iqiyi", 1, {"sort": "unknown"}),
            ("iqiyi", 1, {"url": "http://127.0.0.1/"}),
            ("mgtv", 1, {"sort": "score"}),
        ]
        for source, page, params in cases:
            with self.subTest(source=source, page=page, params=params):
                with self.assertRaises(StreamingDiscoveryError):
                    self.discovery.discover(source, page=page, params=params)
        self.http.get_res.assert_not_called()
        self.http.post.assert_not_called()

    def test_tencent_second_page_uses_server_context_and_only_returns_new_page(self):
        first = tencent_page([{"cid": "first", "title": "第一页"}], context={"_ds_cli_feed_page": "1"})
        second = tencent_page([
            {"cid": "second", "title": "第二页", "year": "2026", "new_pic_vt": "https://puui.qpic.cn/poster.jpg"},
            {"cid": "second", "title": "重复条目"},
        ], has_more=False)
        requests = []

        def post(*args, **kwargs):
            requests.append((args, copy.deepcopy(kwargs)))
            return response(first if len(requests) == 1 else second)

        self.http.post.side_effect = post
        result = self.discovery.discover("tencent", page=2)

        self.assertEqual(2, len(requests))
        self.assertNotIn("page_context", requests[0][1]["json"])
        self.assertEqual({"_ds_cli_feed_page": "1"}, requests[1][1]["json"]["page_context"])
        self.assertEqual(["second"], [item["source_id"] for item in result["Items"]])
        self.assertEqual("", result["Items"][0]["id"])
        self.assertEqual("TV", result["Items"][0]["type"])
        self.assertEqual("v.qq.com", urlsplit(result["Items"][0]["detail_url"]).hostname)
        self.assertFalse(result["has_more"])

    def test_tencent_missing_pagination_context_is_not_a_repeated_first_page(self):
        self.http.post.return_value = response(tencent_page([{"cid": "first", "title": "第一页"}]))
        with self.assertRaises(StreamingDiscoveryError):
            self.discovery.discover("tencent", page=2)
        self.http.post.assert_called_once()

    def test_tencent_ignores_stale_next_page_flag_without_results_or_context(self):
        cases = (
            tencent_page([], has_more=True, context={"_ds_cli_feed_page": "1"}),
            tencent_page([{"cid": "last", "title": "最后一页"}], has_more=True),
            tencent_page([{"cid": "next", "title": "还有下一页"}], has_more=True,
                         context={"_ds_cli_feed_page": "1"}),
        )
        for payload, expected in zip(cases, (False, False, True)):
            with self.subTest(expected=expected):
                StreamingDiscovery._cache.clear()
                self.http.post.return_value = response(payload)
                self.assertEqual(expected, self.discovery.discover("tencent")["has_more"])

    def test_tencent_category_specific_sort_values_match_catalog_contract(self):
        cases = (
            ("tv", "new", "100113", "79"),
            ("movie", "new", "100173", "83"),
            ("movie", "score", "100173", "81"),
            ("variety", "new", "100109", "23"),
            ("anime", "new", "100119", "23"),
            ("children", "new", "100150", "76"),
            ("documentary", "new", "100105", "74"),
        )
        self.http.post.return_value = response(tencent_page([], has_more=False))
        for category, sort, channel_id, upstream_sort in cases:
            with self.subTest(category=category, sort=sort):
                self.discovery.discover("tencent", params={"category": category, "sort": sort})
                params = self.http.post.call_args.kwargs["json"]["page_params"]
                self.assertEqual(channel_id, params["channel_id"])
                self.assertEqual([upstream_sort], parse_qs(params["filter_params"])["sort"])

    def test_mgtv_movie_mapping_keeps_platform_id_out_of_tmdb_and_uses_last_page_flag(self):
        self.http.get_res.return_value = response({"code": 200, "data": {
            "hasMore": False, "hitDocs": [{
                "clipId": "567", "title": "示例电影", "year": "2025",
                "img": "//0img.hitv.com/poster.jpg", "story": "故事简介", "zhihuScore": "8.7",
                "playPartId": "789",
            }],
        }})
        result = self.discovery.discover("mgtv", page=3, params={"category": "movie", "sort": "new"})
        request = self.http.get_res.call_args
        self.assertEqual("pianku.api.mgtv.com", urlsplit(request.args[0]).hostname)
        self.assertEqual("3", str(request.kwargs["params"]["channelId"]))
        self.assertEqual("3", str(request.kwargs["params"]["pn"]))
        item = result["Items"][0]
        self.assertEqual("", item["id"])
        self.assertEqual("567", item["source_id"])
        self.assertEqual("MOV", item["type"])
        self.assertEqual("2025", item["year"])
        self.assertEqual("故事简介", item["overview"])
        self.assertEqual("https", urlsplit(item["image"]).scheme)
        self.assertEqual("www.mgtv.com", urlsplit(item["detail_url"]).hostname)
        self.assertFalse(result["has_more"])

    def test_iqiyi_filters_wrong_channels_episode_rows_and_duplicate_albums(self):
        rows = [
            iqiyi_item(), iqiyi_item(name="重复条目"),
            iqiyi_item(124, channelId=1, name="其它频道"),
            iqiyi_item(125, name="单集", title="示例剧集 第 2 集"),
        ]
        self.http.get_res.return_value = response({"code": "A00000", "data": {"list": rows, "has_next": 1}})
        result = self.discovery.discover("iqiyi", page=2, params={"category": "tv", "sort": "score"})
        request = self.http.get_res.call_args
        self.assertEqual("pcw-api.iqiyi.com", urlsplit(request.args[0]).hostname)
        self.assertEqual("2", str(request.kwargs["params"]["page_id"]))
        self.assertEqual("8", str(request.kwargs["params"]["mode"]))
        self.assertEqual(["123"], [item["source_id"] for item in result["Items"]])
        item = result["Items"][0]
        self.assertEqual("示例剧集", item["title"])
        self.assertEqual("2026", item["year"])
        self.assertEqual("", item["id"])
        self.assertEqual("故事简介", item["overview"])
        self.assertTrue(result["has_more"])

    def test_iqiyi_movies_with_video_poster_are_kept(self):
        movie = iqiyi_item(channelId=1, imageUrl="https://pic1.iqiyipic.com/image/v_poster.jpg")
        self.http.get_res.return_value = response({"code": "A00000", "data": {"list": [movie], "has_next": 0}})
        result = self.discovery.discover("iqiyi", params={"category": "movie"})
        self.assertEqual(1, len(result["Items"]))
        self.assertEqual("MOV", result["Items"][0]["type"])
        self.assertFalse(result["has_more"])

    def test_iqiyi_invalid_optional_image_sizes_keep_the_original_image(self):
        row = iqiyi_item(imageSize=7)
        self.http.get_res.return_value = response({"code": "A00000", "data": {"list": [row], "has_next": 0}})
        result = self.discovery.discover("iqiyi")
        self.assertEqual(row["imageUrl"], result["Items"][0]["image"])

    def test_untrusted_media_urls_cannot_produce_executable_or_offsite_links(self):
        for url in ("javascript:alert(1)", "https://www.iqiyi.com.evil.example/", "https://example.com/"):
            with self.subTest(url=url):
                StreamingDiscovery._cache.clear()
                row = iqiyi_item(playUrl=url, imageUrl="javascript:alert(2)")
                self.http.get_res.return_value = response({"code": "A00000", "data": {"list": [row], "has_next": 0}})
                result = self.discovery.discover("iqiyi")
                for item in result["Items"]:
                    self.assertIn(urlsplit(item["detail_url"]).hostname, (None, "www.iqiyi.com", "iqiyi.com", "so.iqiyi.com"))
                    self.assertNotEqual("javascript", urlsplit(item["image"]).scheme)

    def test_valid_empty_last_page_is_successful(self):
        self.http.get_res.return_value = response({"code": 200, "data": {"hitDocs": [], "hasMore": False}})
        self.assertEqual({"Items": [], "has_more": False}, self.discovery.discover("mgtv", page=2))

    def test_broken_nested_tencent_rows_report_a_recoverable_error(self):
        for modules in ([{"module_datas": 7}], [{"module_datas": [{"item_data_lists": {"item_datas": 7}}]}]):
            with self.subTest(modules=modules):
                StreamingDiscovery._cache.clear()
                self.http.post.return_value = response({"ret": 0, "data": {"module_list_datas": modules}})
                with self.assertRaises(StreamingDiscoveryError):
                    self.discovery.discover("tencent")

    def test_network_http_json_and_platform_failures_remain_retryable(self):
        broken_json = response(None)
        broken_json.json.side_effect = ValueError("invalid JSON")
        cases = [None, response({}, status=503), broken_json,
                 response({"code": 500, "msg": "upstream failure"}),
                 response({"code": 200, "data": None}),
                 response({"code": 200, "data": {"hitDocs": "broken"}})]
        for failed_response in cases:
            with self.subTest(response=failed_response):
                StreamingDiscovery._cache.clear()
                self.http.get_res.return_value = failed_response
                with self.assertRaises(StreamingDiscoveryError):
                    self.discovery.discover("mgtv")
                self.http.get_res.return_value = response({"code": 200, "data": {"hitDocs": [], "hasMore": False}})
                self.assertEqual([], self.discovery.discover("mgtv")["Items"])

    def test_cached_pages_do_not_leak_mutations_or_replace_other_filters(self):
        self.http.get_res.return_value = response({"code": "A00000", "data": {
            "list": [iqiyi_item()], "has_next": 0,
        }})
        first = self.discovery.discover("iqiyi")
        first["Items"][0]["title"] = "调用者修改的标题"
        self.assertEqual("示例剧集", self.discovery.discover("iqiyi")["Items"][0]["title"])
        self.http.get_res.assert_called_once()
        self.discovery.discover("iqiyi", params={"sort": "new"})
        self.discovery.discover("iqiyi", page=2)
        self.assertEqual(3, self.http.get_res.call_count)


class StreamingRecommendationActionTest(unittest.TestCase):
    def test_streaming_errors_are_returned_to_the_existing_retry_ui(self):
        actions = SearchActions(Mock(), Mock())
        with patch("web.actions.search.StreamingDiscovery") as factory:
            service = factory.return_value
            service.discover.side_effect = StreamingDiscoveryError("平台暂不可用，请稍后重试")
            self.assertEqual({"code": 1, "msg": "平台暂不可用，请稍后重试", "Items": []},
                             actions.get_recommend({"type": "STREAMING", "subtype": "iqiyi", "page": "2"}))
            service.discover.assert_called_once_with("iqiyi", page="2", params=None)

    def test_streaming_results_preserve_the_explicit_pagination_flag(self):
        actions = SearchActions(Mock(), Mock())
        page = {"Items": [{"id": "", "source_id": "123", "title": "示例剧集"}], "has_more": False}
        with patch("web.actions.search.StreamingDiscovery") as factory:
            factory.return_value.discover.return_value = page
            self.assertEqual({"code": 0, **page}, actions.get_recommend({
                "type": "STREAMING", "subtype": "tencent", "params": {"category": "tv"},
            }))
            factory.return_value.discover.assert_called_once_with("tencent", page=1, params={"category": "tv"})


if __name__ == "__main__":
    unittest.main()
