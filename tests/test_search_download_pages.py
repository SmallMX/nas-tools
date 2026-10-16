import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.conf import ModuleConf
from web.routes import download_pages, search_pages


class SearchDownloadPageContractTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.register_blueprint(search_pages.search_pages_bp)
        app.register_blueprint(download_pages.download_pages_bp)
        self.client = app.test_client()
        self.user = SimpleNamespace(id=1, username="reader", pris="资源搜索", is_authenticated=True)
        self._patch("flask_login.utils._get_user", return_value=self.user)
        self.users = self._patch("web.routes.search_pages.User").return_value
        self.users.get_user.return_value = self.user
        self.search_actions = self._patch("web.routes.search_pages.WebAction").return_value
        self.indexer = self._patch("web.routes.search_pages.Indexer").return_value
        self.download_actions = self._patch("web.routes.download_pages.WebAction").return_value
        self.config = self._patch("web.routes.download_pages.Config").return_value
        self.remover = self._patch("web.routes.download_pages.TorrentRemover").return_value
        self.search_render = self._patch("web.routes.search_pages.render_template", return_value="rendered")
        self.download_render = self._patch("web.routes.download_pages.render_template", return_value="rendered")
        self.filters = {
            "tmdb_movie": {"genre": ["movie"]},
            "tmdb_tv": {"genre": ["tv"]},
            "custom": {"language": ["zh"]},
        }
        self._patch("web.routes.search_pages.ModuleConf.DISCOVER_FILTER_CONF", self.filters)

    def _patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def assert_render(self, path, method, render, template, expected, query=None, body=None):
        render.reset_mock()
        response = self.client.open(path, method=method, query_string=query, data=body)
        self.assertEqual(200, response.status_code)
        self.assertEqual("rendered", response.get_data(as_text=True))
        render.assert_called_once_with(template, **expected)

    @staticmethod
    def recommend_context(**changes):
        context = {
            "Type": "", "SubType": "", "Title": "", "CurrentPage": 1,
            "Week": "", "TmdbId": "", "PersonId": "", "SubTitle": "",
            "Keyword": "", "Source": "", "Filter": "", "FilterConf": {}, "Params": {},
        }
        context.update(changes)
        return context

    def test_search_keeps_results_total_indexers_and_raw_permission_list(self):
        results = {"影片": {"key": "media-1", "torrent_dict": []}}
        sites = {"hash": {"public": True, "builtin": True}}
        self.search_actions.get_search_result.return_value = {"result": results, "total": 7}
        self.indexer.get_indexer_hash_dict.return_value = sites
        cases = (
            (1, "资源搜索,下载管理", ["资源搜索", "下载管理"]),
            (1, "资源搜索,, 下载管理 ", ["资源搜索", "", " 下载管理 "]),
            (1, None, ["None"]),
            (0, "", [""]),
        )
        for method in ("GET", "POST"):
            for user_id, permissions, expected in cases:
                with self.subTest(method=method, user_id=user_id, permissions=permissions):
                    self.user.id, self.user.pris = user_id, permissions
                    self.users.get_user.reset_mock()
                    self.search_actions.get_search_result.reset_mock()
                    self.indexer.get_indexer_hash_dict.reset_mock()
                    self.assert_render("/search", method, self.search_render, "search.html", {
                        "UserPris": expected, "Count": 7, "Results": results,
                        "SiteDict": sites, "UPCHAR": "↑",
                    }, query={"page": "99"}, body={"keyword": "ignored"})
                    self.users.get_user.assert_called_once_with("reader")
                    self.search_actions.get_search_result.assert_called_once_with()
                    self.indexer.get_indexer_hash_dict.assert_called_once_with()
                    self.assertIs(results, self.search_render.call_args.kwargs["Results"])

    def test_fixed_exploration_pages_keep_exact_template_arguments(self):
        cases = (
            ("/ranking", "discovery/ranking.html", {"DiscoveryType": "RANKING"}),
            ("/bangumi", "discovery/ranking.html", {"DiscoveryType": "BANGUMI"}),
            ("/tmdb_movie", "discovery/recommend.html", {
                "Type": "DISCOVER", "SubType": "MOV", "Title": "TMDB电影",
                "Filter": "tmdb_movie", "FilterConf": self.filters["tmdb_movie"],
            }),
            ("/tmdb_tv", "discovery/recommend.html", {
                "Type": "DISCOVER", "SubType": "TV", "Title": "TMDB电视剧",
                "Filter": "tmdb_tv", "FilterConf": self.filters["tmdb_tv"],
            }),
        )
        for path, template, expected in cases:
            for method in ("GET", "POST"):
                with self.subTest(path=path, method=method):
                    self.assert_render(path, method, self.search_render, template, expected,
                                       query={"type": "ignored", "page": "9"}, body={"title": "ignored"})

    def test_media_and_person_pages_use_only_query_parameters(self):
        cases = (
            ("/media_detail", "discovery/mediainfo.html", {"id": "007", "type": "MOV"},
             {"TmdbId": "007", "Type": "MOV"}),
            ("/discovery_person", "discovery/person.html",
             {"tmdbid": "008", "type": "TV", "title": "演员<一>", "subtitle": "角色&二"},
             {"TmdbId": "008", "Type": "TV", "Title": "演员<一>", "SubTitle": "角色&二"}),
        )
        body = {"id": "body", "tmdbid": "body", "type": "body", "title": "body", "subtitle": "body"}
        for path, template, query, expected in cases:
            for method in ("GET", "POST"):
                for values, context in ((query, expected), ({}, dict.fromkeys(expected)),
                                        (dict.fromkeys(query, ""), dict.fromkeys(expected, ""))):
                    with self.subTest(path=path, method=method, query=values):
                        self.assert_render(path, method, self.search_render, template, context,
                                           query=values, body=body)

    def test_recommend_defaults_ignore_post_body(self):
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                self.assert_render("/recommend", method, self.search_render, "discovery/recommend.html",
                                   self.recommend_context(), body={
                                       "type": "DISCOVER", "page": "invalid", "params": "{invalid",
                                       "filter": "custom", "title": "body",
                                   })

    def test_recommend_keeps_all_query_fields_and_nested_json(self):
        params = {"genre": [1, 2], "enabled": False, "nested": {"text": '</script>"中文'}}
        query = {
            "type": "SEARCH", "subtype": "MOV", "title": "片名", "page": "002",
            "week": "3", "tmdbid": "007", "personid": "008", "subtitle": "副标题",
            "keyword": "a & b", "source": "tmdb", "filter": "custom", "params": json.dumps(params),
        }
        expected = self.recommend_context(
            Type="SEARCH", SubType="MOV", Title="片名", CurrentPage=2, Week="3", TmdbId="007",
            PersonId="008", SubTitle="副标题", Keyword="a & b", Source="tmdb", Filter="custom",
            FilterConf=self.filters["custom"], Params=params,
        )
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                self.assert_render("/recommend", method, self.search_render, "discovery/recommend.html",
                                   expected, query=query, body={"page": "999", "params": "[]"})

    def test_recommend_keeps_page_boundaries_and_filter_absence_distinction(self):
        cases = (
            ({"page": "1"}, self.recommend_context()),
            ({"page": "10000"}, self.recommend_context(CurrentPage=10000)),
            ({"page": "", "params": "", "filter": ""}, self.recommend_context()),
            ({"filter": "unknown"}, self.recommend_context(Filter="unknown", FilterConf=None)),
        )
        for query, expected in cases:
            for method in ("GET", "POST"):
                with self.subTest(method=method, query=query):
                    self.assert_render("/recommend", method, self.search_render, "discovery/recommend.html",
                                       expected, query=query)

    def test_recommend_rejects_invalid_page_and_json_before_rendering(self):
        cases = [
            ({"page": page}, "页码必须是整数") for page in ("bad", "1.5", " ")
        ] + [
            ({"page": page}, "页码超出允许范围") for page in ("0", "-1", "10001")
        ] + [
            ({"params": value}, "推荐过滤参数不是有效的 JSON") for value in ("{", "undefined")
        ] + [
            ({"params": value}, "推荐过滤参数必须是 JSON 对象")
            for value in ("[]", "null", "7", '"text"', "true")
        ] + [({"page": "invalid", "params": "{"}, "页码必须是整数")]
        for query, message in cases:
            for method in ("GET", "POST"):
                with self.subTest(method=method, query=query):
                    self.search_render.reset_mock()
                    response = self.client.open("/recommend", method=method, query_string=query)
                    self.assertEqual(400, response.status_code)
                    self.assertEqual(message, response.get_data(as_text=True))
                    self.search_render.assert_not_called()

    def test_downloading_passes_original_torrents_and_configured_client(self):
        for torrents, client in (([], None), ([{"id": "hash", "state": "Stoped"}, {"id": "2"}], "transmission")):
            for method in ("GET", "POST"):
                with self.subTest(method=method, client=client):
                    self.download_actions.get_downloading.reset_mock()
                    self.config.get_config.reset_mock()
                    self.download_actions.get_downloading.return_value = {"result": torrents, "total": 999}
                    self.config.get_config.return_value = {"pt_client": client}
                    self.assert_render("/downloading", method, self.download_render, "download/downloading.html", {
                        "DownloadCount": len(torrents), "Torrents": torrents, "Client": client,
                    }, query={"client": "ignored"}, body={"client": "ignored"})
                    self.download_actions.get_downloading.assert_called_once_with()
                    self.config.get_config.assert_called_once_with("pt")
                    self.assertIs(torrents, self.download_render.call_args.kwargs["Torrents"])

    def test_download_history_preserves_original_page_type_and_query_only_input(self):
        for page, expected in ((None, 1), ("", 1), ("002", "002"), ("0", "0"), ("-1", "-1"), ("bad", "bad")):
            for method in ("GET", "POST"):
                with self.subTest(method=method, page=page):
                    self.assert_render("/downloaded", method, self.download_render, "discovery/recommend.html", {
                        "Type": "DOWNLOADED", "Title": "近期下载", "CurrentPage": expected,
                    }, query={} if page is None else {"page": page}, body={"page": "body"})
                    self.assertIs(type(expected), type(self.download_render.call_args.kwargs["CurrentPage"]))

    def test_torrent_remove_keeps_task_mapping_and_downloader_rules(self):
        for tasks in ({}, {7: {"id": 7, "name": "任务", "enabled": False}}):
            for method in ("GET", "POST"):
                with self.subTest(method=method, tasks=tasks):
                    self.remover.get_torrent_remove_tasks.reset_mock()
                    self.remover.get_torrent_remove_tasks.return_value = tasks
                    self.assert_render("/torrent_remove", method, self.download_render, "download/torrent_remove.html", {
                        "DownloaderConfig": ModuleConf.TORRENTREMOVER_DICT,
                        "Count": len(tasks), "TorrentRemoveTasks": tasks,
                    }, query={"tid": "ignored"}, body={"tid": "ignored"})
                    self.remover.get_torrent_remove_tasks.assert_called_once_with()
                    self.assertIs(tasks, self.download_render.call_args.kwargs["TorrentRemoveTasks"])


if __name__ == "__main__":
    unittest.main()
