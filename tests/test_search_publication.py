import unittest
from datetime import date
from unittest.mock import Mock, call, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.main_db import _upgrade_download_history, _upgrade_search_result_ids
from app.db.models import Base, DownloadHistory, SiteStatisticsHistory, SiteUserInfoStats
from app.helper.db_helper import DbHelper
from app.media import Media
from app.media.douban import DouBan
from app.media.meta import MetaInfo
from app.media.tmdbv3api import Search
from web.actions.search import SearchActions
from app.utils.types import MediaType


class SearchPublicationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        session_patch = patch("app.db.main_db._Session", return_value=self.session)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        self.db = DbHelper()

    @staticmethod
    def _torrent(title):
        media = MetaInfo(title=title)
        media.set_torrent_info(size=1024, site="Example")
        media.get_poster_image = Mock(return_value="")
        media.get_backdrop_image = Mock(return_value="")
        return media

    def test_publish_empty_or_new_batch_never_reuses_old_ids_and_rolls_back_failure(self):
        self.assertTrue(self.db.replace_search_results([self._torrent("First.2024")]))
        first = self.db.get_search_results()[0].id
        with patch.object(self.db._db, "insert", side_effect=RuntimeError), \
                patch("app.db.main_db.ExceptionUtils.exception_traceback"):
            self.assertFalse(self.db.replace_search_results([self._torrent("Failed.2024")]))
        self.assertEqual(first, self.db.get_search_results()[0].id)
        self.assertTrue(self.db.replace_search_results([]))
        self.assertTrue(self.db.replace_search_results([self._torrent("Second.2024")]))
        self.assertGreater(self.db.get_search_results()[0].id, first)
        self.assertEqual([], self.db.get_search_result_by_id(first))

    def test_legacy_search_ids_invalidated_only_on_first_upgrade(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE search_result_info")
            connection.exec_driver_sql("CREATE TABLE search_result_info(id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO search_result_info VALUES(1)")
            _upgrade_search_result_ids(connection)
        self.assertEqual([], self.db.get_search_result_by_id(1))
        self.db.replace_search_results([self._torrent("New.2024")])
        new_id = self.db.get_search_results()[0].id
        self.assertGreater(new_id, 1)
        self.assertLess(new_id, 2 ** 53)
        with self.engine.begin() as connection:
            _upgrade_search_result_ids(connection)
        self.assertEqual(new_id, self.db.get_search_results()[0].id)

    def test_distinct_media_and_latest_history_survive_upgrade_and_updates(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("DROP INDEX idx_download_history_identity")
            connection.exec_driver_sql(
                "INSERT INTO download_history(type, tmdbid, title, date) VALUES(?, ?, ?, ?)",
                [("电影", "3", "Old", "2023"), ("电影", "3", "Latest", "2024"),
                 ("电视剧", "3", "Same ID", "2023"), ("电影", "4", "Latest", "2024")],
            )
            _upgrade_download_history(connection)
            _upgrade_download_history(connection)
        self.assertEqual(["Latest", "Same ID", "Latest"],
                         [item.title for item in self.session.query(DownloadHistory).order_by(DownloadHistory.id)])
        movie = self._torrent("Renamed.2026")
        movie.tmdb_id = 3
        movie.title = "Renamed"
        movie.type = MediaType.MOVIE
        self.assertTrue(self.db.insert_download_history(movie))
        self.assertEqual(3, self.session.query(DownloadHistory).count())
        self.assertEqual("Renamed", self.session.query(DownloadHistory).filter_by(type="电影", tmdbid="3").one().title)
        movie.tmdb_id = 5
        self.assertTrue(self.db.insert_download_history(movie))
        self.assertEqual(4, self.session.query(DownloadHistory).count())

    def test_explicit_empty_site_filter_never_returns_disabled_sites(self):
        self.session.add(SiteUserInfoStats(site="disabled", url="stored"))
        self.session.add(SiteStatisticsHistory(site="disabled", url="stored", date=str(date.today()),
                                               upload=1, download=2))
        self.session.commit()
        self.assertTrue(self.db.get_site_user_statistics())
        self.assertTrue(self.db.get_site_statistics_recent_sites()[2])
        self.assertEqual([], self.db.get_site_user_statistics(strict_urls=[]))
        self.assertEqual((0, 0, [], [], []), self.db.get_site_statistics_recent_sites(strict_urls=[]))


class MediaLookupTest(unittest.TestCase):
    def test_second_page_is_fetched_for_each_media_provider(self):
        media = Media.__new__(Media)
        media.tmdb = Mock()
        media.search = Search()
        with patch.object(media.search, "_call", side_effect=[
            {"results": [{"id": 2, "media_type": "movie"}], "total_pages": 2},
            {"results": [{"title": "Title", "id": 3}], "total_pages": 2},
            {"results": [{"name": "Title", "id": 4}], "total_pages": 3},
        ]) as request:
            self.assertEqual(2, media.get_tmdb_infos("Title", page=2)[0]["id"])
            items, has_more = media.get_tmdb_infos_page("Title", year=2024, page=2)
            self.assertEqual({3, 4}, {item["id"] for item in items})
            self.assertTrue(has_more)
        self.assertEqual([
            call("/search/multi", "query=Title&page=2"),
            call("/search/movie", "query=Title&page=2&year=2024"),
            call("/search/tv", "query=Title&page=2&first_air_date_year=2024"),
        ], request.call_args_list)

    def test_filtered_empty_page_can_continue_in_recommendation_ui_for_both_providers(self):
        media = Media.__new__(Media)
        media.tmdb = Mock()
        media.search = Search()
        douban = DouBan.__wrapped__.__new__(DouBan.__wrapped__)
        douban.doubanapi = Mock()
        douban.doubanapi.search.side_effect = [
            {"total": 21, "items": [{"type_name": "人物"}]},
            {"total": 21, "items": [{"type_name": "电影", "target": {
                "id": "42", "title": "Title", "cover_url": "image"}}]},
        ]
        actions = SearchActions(Mock(), Mock())
        with patch.object(media.search, "_call", side_effect=[
            {"total_pages": 2, "results": [{"media_type": "person"}]},
            {"total_pages": 2, "results": [{"media_type": "movie", "id": 42, "title": "Title"}]},
        ]), patch("web.backend.web_utils.Media", return_value=media), \
                patch("web.backend.web_utils.DouBan", return_value=douban):
            for source in ("tmdb", "douban"):
                with self.subTest(source=source):
                    query = {"type": "SEARCH", "source": source, "keyword": "Title"}
                    first = actions.get_recommend({**query, "page": 1})
                    self.assertEqual({"code": 0, "Items": [], "has_more": True}, first)
                    second = actions.get_recommend({**query, "page": 2})
                    self.assertEqual("Title", second["Items"][0]["title"])
                    self.assertFalse(second["has_more"])
        self.assertEqual([call("Title", start=0, count=20), call("Title", start=20, count=20)],
                         douban.doubanapi.search.call_args_list)

    def test_alias_lookup_keeps_movie_type(self):
        media = Media.__new__(Media)
        media.search = Mock()
        media.search.multi.return_value = [{"id": 7, "media_type": "movie", "title": "Canonical"}]
        media.get_tmdb_info = Mock(return_value={
            "id": 7, "title": "Canonical", "media_type": MediaType.MOVIE,
            "alternative_titles": {"titles": [{"title": "Alias"}]},
        })
        self.assertEqual(MediaType.MOVIE, media._Media__search_multi_tmdb("Alias")["media_type"])


if __name__ == "__main__":
    unittest.main()
