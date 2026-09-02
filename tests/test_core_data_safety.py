import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


_test_config_dir = None
if not os.environ.get("NASTOOL_CONFIG"):
    _test_config_dir = tempfile.TemporaryDirectory(prefix="nastool-core-tests-")
    os.environ["NASTOOL_CONFIG"] = str(Path(_test_config_dir.name) / "config.yaml")

from app.brushtask import BrushTask
from app.downloader import Downloader
from app.downloader.client import Qbittorrent, Transmission
from app.sites import SiteUserInfo
from app.torrentremover import TorrentRemover
from app.utils import StringUtils, Torrent
from app.utils.types import BrushDeleteType, DownloaderType, MediaType
from config import PT_TAG


def singleton_class(factory):
    return factory.__closure__[0].cell_contents


class AttrDict(dict):
    def __getattr__(self, item):
        return self[item]


class CoreDataSafetyTest(unittest.TestCase):
    def test_torrent_file_parser_accepts_bencoder_byte_keys(self):
        content = b"d4:infod5:filesld4:pathl5:a.mkveed4:pathl5:b.mkveee4:name4:Showee"
        with tempfile.NamedTemporaryFile(suffix=".torrent") as torrent_file:
            torrent_file.write(content)
            torrent_file.flush()

            folder, files, error = Torrent.get_torrent_files(torrent_file.name)

        self.assertEqual("Show", folder)
        self.assertEqual(["a.mkv", "b.mkv"], files)
        self.assertEqual("", error)

    def test_download_directory_uses_first_matching_type_and_category(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service._downloaddir = [
            {"type": "电影", "category": "", "save_path": "/downloads/movie", "label": "movie"},
            {"type": "电视剧", "category": "欧美剧", "save_path": "/downloads/tv", "label": "tv"},
            {"type": "电视剧", "category": "欧美剧", "save_path": "/downloads/fallback", "label": "fallback"},
        ]
        media = SimpleNamespace(
            tmdb_info={"id": 1},
            type=MediaType.TV,
            category="欧美剧",
            size=0,
        )

        result = service._Downloader__get_download_dir_info(media)

        self.assertEqual({"path": "/downloads/tv", "label": "tv"}, result)

    def test_download_directory_requires_tmdb_identification(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service._downloaddir = [
            {"type": "电影", "category": "", "save_path": "/downloads/movie", "label": "movie"},
        ]
        media = SimpleNamespace(
            tmdb_info=None,
            type=MediaType.MOVIE,
            category="",
            size=0,
        )

        result = service._Downloader__get_download_dir_info(media)

        self.assertEqual({"path": None, "label": None}, result)

    def test_download_directory_allows_qb_category_without_explicit_path(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service._downloaddir = [
            {"type": "动漫", "category": "", "save_path": "", "label": "anime"},
        ]
        media = SimpleNamespace(
            tmdb_info={"id": 1},
            type=MediaType.ANIME,
            category="动漫",
            size=0,
        )

        result = service._Downloader__get_download_dir_info(media)

        self.assertEqual({"path": "", "label": "anime"}, result)

    def test_tv_download_requirements_use_requested_season_and_episodes(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service.media = Mock()
        service.media.get_tmdb_tv_seasons.return_value = [
            {"season_number": 1, "episode_count": 8},
        ]
        media = Mock()
        media.type = MediaType.TV
        media.begin_season = 1
        media.tmdb_id = 42
        media.tmdb_info = {"id": 42}
        media.get_season_list.return_value = [1]
        media.get_episode_list.return_value = [3, 4]
        media.get_title_string.return_value = "Show"
        media.get_season_episode_string.return_value = "S01E03-E04"

        pending, messages = service.build_download_requirements(media)

        self.assertEqual([], messages)
        self.assertEqual({
            42: [{"season": 1, "episodes": [3, 4], "total_episodes": 8}],
        }, pending)

    def test_get_torrents_contract_is_always_two_items(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service._default_client_type = None
        service._Downloader__get_client = Mock(return_value=None)

        result = service.get_torrents(["hash"])

        self.assertEqual((None, []), result)

    def test_downloader_clients_return_strict_boolean_for_start_and_stop(self):
        qb_client = Qbittorrent.__new__(Qbittorrent)
        qb_client.qbc = Mock()
        self.assertTrue(qb_client.start_torrents(["hash"]))
        self.assertTrue(qb_client.stop_torrents("hash"))
        self.assertFalse(qb_client.start_torrents([]))
        self.assertFalse(qb_client.start_torrents([object()]))
        self.assertFalse(qb_client.stop_torrents(object()))

        tr_client = Transmission.__new__(Transmission)
        tr_client.trc = Mock()
        self.assertTrue(tr_client.start_torrents([1, "2"]))
        self.assertTrue(tr_client.stop_torrents("3"))
        self.assertFalse(tr_client.start_torrents(["invalid"]))
        self.assertFalse(tr_client.stop_torrents(0))

    def test_downloader_explicit_missing_client_fails_closed(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service._Downloader__get_client = Mock(return_value=None)

        self.assertFalse(service.start_torrents(downloader=DownloaderType.QB, ids=["hash"]))
        self.assertFalse(service.stop_torrents(downloader=DownloaderType.QB, ids=["hash"]))
        self.assertFalse(service.delete_torrents(downloader=DownloaderType.QB, ids=["hash"]))

    def test_downloader_config_reload_discards_cached_clients(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service.clients = {DownloaderType.QB.value: Mock(name="stale-client")}

        with patch("app.downloader.downloader.DbHelper") as db_factory, \
                patch("app.downloader.downloader.Message"), \
                patch("app.downloader.downloader.Media"), \
                patch("app.downloader.downloader.Sites"), \
                patch("app.downloader.downloader.SystemConfig"), \
                patch("app.downloader.downloader.Config") as config_factory:
            db_factory.return_value.get_download_setting.return_value = []
            config_factory.return_value.get_config.side_effect = lambda key: {
                "pt": {"pt_client": "qbittorrent"},
                "downloaddir": [],
            }.get(key)

            service.init_config()

        self.assertEqual({}, service.clients)
        self.assertEqual(DownloaderType.QB, service._default_client_type)

    def test_onlynastool_adds_required_tag_without_mutating_config(self):
        downloader_class = singleton_class(Downloader)
        service = downloader_class.__new__(downloader_class)
        service._pt_monitor_only = False
        client = Mock()
        client.get_remove_torrents.return_value = [{"name": "movie"}]
        service._Downloader__get_client = Mock(return_value=client)
        config = {"tags": [], "onlynastool": 1, "samedata": 1}

        service.get_remove_torrents(downloader=DownloaderType.QB, config=config)

        sent_config = client.get_remove_torrents.call_args.kwargs["config"]
        self.assertEqual([PT_TAG], sent_config["filter_tags"])
        self.assertNotIn("filter_tags", config)

    def test_qb_samedata_does_not_reintroduce_untagged_torrent(self):
        client = Qbittorrent.__new__(Qbittorrent)
        now = int(time.time())
        tagged = AttrDict(
            hash="tagged",
            name="same-data",
            tags=PT_TAG,
            completion_on=now - 3600,
            added_on=now - 7200,
            uploaded=0,
            ratio=0,
            size=1024,
            save_path="/downloads",
            tracker="https://tracker.example/announce",
            state="uploading",
            category="",
        )
        untagged = AttrDict(tagged)
        untagged.update(hash="untagged", tags="")
        client.get_torrents = Mock(return_value=([tagged, untagged], False))

        result = client.get_remove_torrents({"filter_tags": [PT_TAG], "samedata": 1})

        self.assertEqual(["tagged"], [item["id"] for item in result])

    def test_qb_tls_verification_defaults_to_enabled(self):
        client = Qbittorrent.__new__(Qbittorrent)
        client._client_config = {
            "qbhost": "localhost",
            "qbport": 8080,
            "qbusername": "user",
            "qbpassword": "password",
        }
        client.init_config()

        with patch("app.downloader.client.qbittorrent.qbittorrentapi.Client") as client_factory:
            client_factory.return_value.app_version.return_value = "5.0.0"
            client._Qbittorrent__login_qbittorrent()

        self.assertTrue(client._verify_cert)
        self.assertTrue(client_factory.call_args.kwargs["VERIFY_WEBUI_CERTIFICATE"])

        client._client_config["verify_cert"] = False
        client.init_config()
        self.assertFalse(client._verify_cert)

    def test_brush_rule_errors_fail_closed_and_old_items_use_full_age(self):
        brush_class = singleton_class(BrushTask)
        service = brush_class.__new__(brush_class)
        service.sites = Mock()
        service.sites.check_torrent_attr.return_value = {}

        invalid_regex = service._BrushTask__check_rss_rule(
            {"include": "["}, "movie", "https://example/item", 1, None, "", "", False
        )
        old_item = service._BrushTask__check_rss_rule(
            {"pubdate": "lt#2"},
            "movie",
            "https://example/item",
            1,
            datetime.now(timezone.utc) - timedelta(hours=25),
            "",
            "",
            False,
        )

        self.assertFalse(invalid_regex)
        self.assertFalse(old_item)

    def test_brush_rule_parser_accepts_json_and_legacy_dict_without_eval(self):
        brush_class = singleton_class(BrushTask)

        self.assertEqual({"free": "FREE"}, brush_class._BrushTask__parse_rule('{"free": "FREE"}'))
        self.assertEqual({"ratio": "gt#1"}, brush_class._BrushTask__parse_rule("{'ratio': 'gt#1'}"))
        with self.assertRaises(ValueError):
            brush_class._BrushTask__parse_rule("__import__('os').getcwd()")

    def test_brush_task_with_deleted_site_does_not_break_task_listing(self):
        brush_class = singleton_class(BrushTask)
        service = brush_class.__new__(brush_class)
        service.dbhelper = Mock()
        service.sites = Mock()
        service.sites.get_sites.return_value = None
        service.get_downloader_info = Mock(return_value={"name": "client"})
        service.dbhelper.get_brushtasks.return_value = [SimpleNamespace(
            id=1,
            name="orphaned-site",
            site=99,
            inteval=10,
            state="N",
            downloader=1,
            freeleech="",
            rss_rule="{}",
            remove_rule="{}",
            seed_size=0,
            sendmessage="N",
            forceupload="N",
            download_count=0,
            remove_count=0,
            download_size=0,
            upload_size=0,
            lst_mod_date=None,
        )]

        tasks = service.get_brushtask_info()

        self.assertEqual(1, len(tasks))
        self.assertIsNone(tasks[0]["site"])
        self.assertIsNone(tasks[0]["rss_url"])

    def test_brush_database_state_changes_only_after_downloader_delete(self):
        brush_class = singleton_class(BrushTask)
        service = brush_class.__new__(brush_class)
        events = []
        torrent = AttrDict(
            hash="hash",
            name="brush-item",
            added_on=int(time.time()) - 3600,
            completion_on=int(time.time()) - 1800,
            ratio=2,
            uploaded=2048,
            downloaded=1024,
            last_activity=int(time.time()) - 60,
        )
        dbhelper = Mock()
        dbhelper.get_brushtask_torrents.return_value = [SimpleNamespace(download_id="hash")]
        dbhelper.update_brushtask_torrent_state.side_effect = lambda _: events.append("database") or True
        service.dbhelper = dbhelper
        service._brush_tasks = [{
            "state": "Y",
            "id": 1,
            "name": "brush",
            "downloader": 1,
            "remove_rule": {},
            "sendmessage": "N",
        }]
        service.get_downloader_info = Mock(return_value={"type": "qbittorrent"})
        client = Mock()
        client.get_torrents.side_effect = [([torrent], False), ([torrent], False), ([], False)]
        client.delete_torrents.side_effect = lambda **_: events.append("downloader") or True

        with patch("app.brushtask.Qbittorrent", return_value=client), \
                patch.object(brush_class, "_BrushTask__check_remove_rule",
                             return_value=(True, BrushDeleteType.RATIO)):
            service.remove_tasks_torrents()

        self.assertEqual(["downloader", "database"], events)

        events.clear()
        dbhelper.update_brushtask_torrent_state.reset_mock()
        client.get_torrents.side_effect = [([torrent], False), ([torrent], False), ([], False)]
        client.delete_torrents.side_effect = lambda **_: events.append("downloader") or False
        with patch("app.brushtask.Qbittorrent", return_value=client), \
                patch.object(brush_class, "_BrushTask__check_remove_rule",
                             return_value=(True, BrushDeleteType.RATIO)):
            service.remove_tasks_torrents()

        self.assertEqual(["downloader"], events)
        dbhelper.update_brushtask_torrent_state.assert_not_called()

    def test_brush_keeps_database_record_for_existing_paused_torrent(self):
        brush_class = singleton_class(BrushTask)
        service = brush_class.__new__(brush_class)
        dbhelper = Mock()
        dbhelper.get_brushtask_torrents.return_value = [SimpleNamespace(download_id="paused")]
        service.dbhelper = dbhelper
        service._brush_tasks = [{
            "state": "Y",
            "id": 1,
            "name": "brush",
            "downloader": 1,
            "remove_rule": {},
            "sendmessage": "N",
        }]
        service.get_downloader_info = Mock(return_value={"type": "qbittorrent"})
        paused_torrent = AttrDict(hash="paused")
        client = Mock()
        client.get_torrents.side_effect = [([paused_torrent], False), ([], False), ([], False)]

        with patch("app.brushtask.Qbittorrent", return_value=client):
            service.remove_tasks_torrents()

        dbhelper.delete_brushtask_torrent.assert_not_called()
        client.delete_torrents.assert_not_called()

    def test_torrent_remover_reports_only_successful_operations(self):
        remover_class = singleton_class(TorrentRemover)
        for action in (1, 2, 3):
            with self.subTest(action=action):
                service = remover_class.__new__(remover_class)
                service._remove_tasks = {"1": {
                    "id": 1,
                    "name": "cleanup",
                    "downloader": "Qb",
                    "onlynastool": 0,
                    "samedata": 0,
                    "action": action,
                    "config": {},
                    "interval": 10,
                    "enabled": 1,
                }}
                service.downloader = Mock()
                service.message = Mock()
                service.downloader.get_remove_torrents.return_value = [
                    {"id": "ok", "name": "success", "site": "site", "size": 1024},
                    {"id": "failed", "name": "failure", "site": "site", "size": 1024},
                ]
                if action == 1:
                    service.downloader.stop_torrents.side_effect = [True, False]
                else:
                    service.downloader.delete_torrents.side_effect = [True, False]

                service.auto_remove_torrents(taskids=[1])

                message = service.message.send_brushtask_remove_message.call_args.kwargs["text"]
                self.assertIn("1个种子", message)
                self.assertIn("success", message)
                self.assertNotIn("failure", message)

    def test_torrent_remove_task_update_uses_single_database_transaction(self):
        remover_class = singleton_class(TorrentRemover)
        service = remover_class.__new__(remover_class)
        db = Mock()
        db.query.return_value.filter.return_value.update.return_value = 1
        service.dbhelper = SimpleNamespace(_db=db)

        result = service._TorrentRemover__persist_torrent_remove_task(
            tid=1,
            name="cleanup",
            action=2,
            interval=10,
            enabled=1,
            samedata=0,
            onlynastool=1,
            downloader="Qb",
            config={"tags": []},
        )

        self.assertTrue(result)
        db.query.return_value.filter.return_value.update.assert_called_once()
        db.insert.assert_not_called()
        db.commit.assert_called_once()
        db.rollback.assert_not_called()

    def test_scheduler_callbacks_remove_worker_database_sessions(self):
        brush_class = singleton_class(BrushTask)
        remover_class = singleton_class(TorrentRemover)

        with patch("app.brushtask.remove_db_session") as brush_cleanup, \
                patch("app.torrentremover.remove_db_session") as remover_cleanup:
            brush_class._BrushTask__remove_job_db_session(None)
            remover_class._TorrentRemover__remove_job_db_session(None)

        brush_cleanup.assert_called_once_with()
        remover_cleanup.assert_called_once_with()

    def test_site_userinfo_debug_log_never_contains_cookie_value(self):
        site_class = singleton_class(SiteUserInfo)
        service = site_class.__new__(site_class)
        service._site_schema = []
        request = Mock()
        request.get_res.return_value = None

        with patch("app.sites.site_userinfo.log.debug") as debug_log, \
                patch("app.sites.site_userinfo.ChromeHelper"), \
                patch("app.sites.site_userinfo.RequestUtils", return_value=request):
            service.build("https://site.example", "site", site_cookie="secret-cookie", ua="ua")

        log_text = " ".join(str(call) for call in debug_log.call_args_list)
        self.assertNotIn("secret-cookie", log_text)
        self.assertIn("cookie_length=13", log_text)

    def test_file_size_parser_removes_all_case_insensitive_byte_markers(self):
        self.assertEqual("1.0K", StringUtils.str_filesize("1024 BiB"))


if __name__ == "__main__":
    unittest.main()
