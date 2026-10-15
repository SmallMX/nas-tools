import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.brushtask import BrushTask
from app.torrentremover import TorrentRemover
from config import BRUSH_REMOVE_TORRENTS_INTERVAL


class BackgroundTaskGroupsTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.groups = []
        self.manager.create_group.side_effect = self._create_group
        self._patch("app.brushtask.SchedulerManager").return_value = self.manager
        self._patch("app.torrentremover.SchedulerManager").return_value = self.manager
        self.brush_database = self._patch("app.brushtask.DbHelper").return_value
        self.brush_database.get_user_downloaders.return_value = []
        self.remover_database = self._patch("app.torrentremover.DbHelper").return_value
        self.remover_database.get_torrent_remove_tasks.return_value = []
        self._patch("app.brushtask.Message")
        self._patch("app.brushtask.Sites")
        self._patch("app.brushtask.log")
        self._patch("app.torrentremover.Message")
        self._patch("app.torrentremover.Downloader")
        self._patch("app.torrentremover.log")
        self.brush = BrushTask.__wrapped__.__new__(BrushTask.__wrapped__)
        self.brush._scheduler = None
        self.brush.get_brushtask_info = Mock(return_value=[])
        self.remover = TorrentRemover.__wrapped__.__new__(TorrentRemover.__wrapped__)
        self.remover._scheduler = None

    def _patch(self, target):
        patcher = patch(target)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _create_group(self, name):
        group = Mock(name=f"{name}-{len(self.groups)}")
        self.groups.append((name, group))
        return group

    @staticmethod
    def _remove_task(task_id, *, enabled=1, interval=10, config=None):
        return SimpleNamespace(
            id=task_id, name=f"remove-{task_id}", downloader="Qb",
            onlynastool=1, samedata=0, action=2, enabled=enabled,
            interval=interval, config=json.dumps({"ratio": 2} if config is None else config),
        )

    def test_brush_group_keeps_existing_filter_intervals_and_arguments(self):
        self.brush.get_brushtask_info.return_value = [
            {"id": 1, "state": "Y", "interval": 10},
            {"id": 2, "state": "Y", "interval": "7"},
            {"id": 3, "state": "N", "interval": 5},
            {"id": 4, "state": "Y", "interval": 0},
            {"id": 5, "state": "Y", "interval": "1.5"},
            {"id": 6, "state": "Y", "interval": None},
        ]

        self.brush.init_config()

        self.manager.create_group.assert_called_once_with("brush")
        group = self.brush._scheduler
        self.assertEqual([
            call(func=self.brush.check_task_rss, args=[1], id="rss:1", trigger="interval", seconds=600),
            call(func=self.brush.check_task_rss, args=[2], id="rss:2", trigger="interval", seconds=420),
            call(func=self.brush.remove_tasks_torrents, id="remove_torrents", trigger="interval",
                 seconds=BRUSH_REMOVE_TORRENTS_INTERVAL),
        ], group.add_job.call_args_list)
        group.start.assert_called_once_with()
        group.print_jobs.assert_called_once_with()

    def test_remover_group_keeps_existing_filter_intervals_and_arguments(self):
        self.remover_database.get_torrent_remove_tasks.return_value = [
            self._remove_task(1, interval=5),
            self._remove_task(2, interval="12"),
            self._remove_task(3, enabled=0),
            self._remove_task(4, interval=0),
            self._remove_task(5, config={}),
        ]

        self.remover.init_config()

        self.manager.create_group.assert_called_once_with("remover")
        group = self.remover._scheduler
        self.assertEqual([
            call(func=self.remover.auto_remove_torrents, args=[1], id="remove:1",
                 trigger="interval", seconds=300),
            call(func=self.remover.auto_remove_torrents, args=[2], id="remove:2",
                 trigger="interval", seconds=720),
        ], group.add_job.call_args_list)
        self.assertEqual(5, len(self.remover.get_torrent_remove_tasks()))
        group.start.assert_called_once_with()

    def test_empty_or_inactive_tasks_do_not_create_groups(self):
        for brush_tasks, remove_tasks in (
            ([], []),
            ([{"id": 1, "state": "N", "interval": 10}], [self._remove_task(1, enabled=0)]),
            ([{"id": 1, "state": "Y", "interval": "invalid"}], [self._remove_task(1, config={})]),
        ):
            with self.subTest(brush_tasks=brush_tasks):
                self.brush.get_brushtask_info.return_value = brush_tasks
                self.remover_database.get_torrent_remove_tasks.return_value = remove_tasks
                self.brush.init_config()
                self.remover.init_config()

                self.assertIsNone(self.brush._scheduler)
                self.assertIsNone(self.remover._scheduler)
                self.manager.create_group.assert_not_called()

    def test_reinitialization_stops_old_group_before_replacing_it(self):
        self.brush.get_brushtask_info.return_value = [{"id": 1, "state": "Y", "interval": 10}]
        self.remover_database.get_torrent_remove_tasks.return_value = [self._remove_task(1)]
        for name, service in (("brush", self.brush), ("remover", self.remover)):
            with self.subTest(group=name):
                service.init_config()
                previous = service._scheduler
                events = Mock()
                events.attach_mock(previous.shutdown, "stop")
                events.attach_mock(self.manager.create_group, "create")

                service.init_config()

                self.assertEqual([call.stop(wait=False), call.create(name)], events.mock_calls)
                self.assertIsNot(previous, service._scheduler)
                self.assertEqual(previous.add_job.call_args_list, service._scheduler.add_job.call_args_list)
                service._scheduler.start.assert_called_once_with()

    def test_disabling_all_tasks_removes_previous_group_without_starting_another(self):
        self.brush.get_brushtask_info.return_value = [{"id": 1, "state": "Y", "interval": 10}]
        self.remover_database.get_torrent_remove_tasks.return_value = [self._remove_task(1)]
        self.brush.init_config()
        self.remover.init_config()
        previous_brush, previous_remover = self.brush._scheduler, self.remover._scheduler
        self.manager.create_group.reset_mock()
        self.brush.get_brushtask_info.return_value = []
        self.remover_database.get_torrent_remove_tasks.return_value = []

        self.brush.init_config()
        self.remover.init_config()

        previous_brush.shutdown.assert_called_once_with(wait=False)
        previous_remover.shutdown.assert_called_once_with(wait=False)
        self.assertIsNone(self.brush._scheduler)
        self.assertIsNone(self.remover._scheduler)
        self.manager.create_group.assert_not_called()

    def test_partial_registration_or_start_failure_closes_group_and_allows_retry(self):
        self.brush.get_brushtask_info.return_value = [
            {"id": 1, "state": "Y", "interval": 10},
            {"id": 2, "state": "Y", "interval": 5},
        ]
        self.remover_database.get_torrent_remove_tasks.return_value = [
            self._remove_task(1), self._remove_task(2),
        ]
        for name, service, expected_ids in (
            ("brush", self.brush, {"rss:1", "rss:2", "remove_torrents"}),
            ("remover", self.remover, {"remove:1", "remove:2"}),
        ):
            for failure_point in ("add_job", "print_jobs", "start"):
                with self.subTest(group=name, failure_point=failure_point):
                    failed, recovered = Mock(), Mock()
                    error = RuntimeError("group initialization failed")
                    if failure_point == "add_job":
                        failed.add_job.side_effect = [None, error]
                    else:
                        getattr(failed, failure_point).side_effect = error
                    with patch.object(self.manager, "create_group", side_effect=[failed, recovered]) as create:
                        with self.assertRaises(RuntimeError) as raised:
                            service.init_config()

                        self.assertIs(error, raised.exception)
                        self.assertIsNone(service._scheduler)
                        failed.shutdown.assert_called_once_with(wait=False)

                        service.init_config()

                        self.assertEqual([call(name), call(name)], create.call_args_list)
                        self.assertIs(recovered, service._scheduler)
                        self.assertEqual(expected_ids, {
                            invocation.kwargs["id"] for invocation in recovered.add_job.call_args_list
                        })
                        recovered.start.assert_called_once_with()
                    service.stop_service()

    def test_group_cleanup_failure_does_not_replace_initialization_error(self):
        self.brush.get_brushtask_info.return_value = [{"id": 1, "state": "Y", "interval": 10}]
        self.remover_database.get_torrent_remove_tasks.return_value = [self._remove_task(1)]
        for module, service in (("brushtask", self.brush), ("torrentremover", self.remover)):
            with self.subTest(module=module):
                group = Mock()
                error = RuntimeError("registration failed")
                cleanup_error = RuntimeError("cleanup failed")
                group.add_job.side_effect = error
                group.shutdown.side_effect = cleanup_error
                with patch.object(self.manager, "create_group", return_value=group), \
                        patch(f"app.{module}.ExceptionUtils.exception_traceback") as report:
                    with self.assertRaises(RuntimeError) as raised:
                        service.init_config()

                self.assertIs(error, raised.exception)
                self.assertIsNone(service._scheduler)
                group.shutdown.assert_called_once_with(wait=False)
                report.assert_called_once_with(cleanup_error)

    def test_stopping_one_service_only_stops_its_group_and_is_idempotent(self):
        self.brush.get_brushtask_info.return_value = [{"id": 1, "state": "Y", "interval": 10}]
        self.remover_database.get_torrent_remove_tasks.return_value = [self._remove_task(1)]
        self.brush.init_config()
        self.remover.init_config()
        brush_group, remover_group = self.brush._scheduler, self.remover._scheduler

        self.brush.stop_service()
        self.brush.stop_service()

        brush_group.shutdown.assert_called_once_with(wait=False)
        remover_group.shutdown.assert_not_called()
        self.manager.shutdown.assert_not_called()
        self.assertIsNone(self.brush._scheduler)
        self.assertIs(remover_group, self.remover._scheduler)

        self.remover.stop_service()
        self.remover.stop_service()
        remover_group.shutdown.assert_called_once_with(wait=False)
        self.manager.shutdown.assert_not_called()

    def test_manual_brush_run_can_still_inspect_a_disabled_task(self):
        self.brush.init_config()
        self.brush.get_brushtask_info.return_value = {
            "id": 1, "state": "N", "name": "manual", "site_id": 1,
            "rss_url": "https://site.example/rss", "rss_rule": {}, "downloader": 1,
        }
        self.brush.sites.get_sites.return_value = {"name": "site", "proxy": False}
        self.brush.get_downloader_info = Mock(return_value={"id": 1})
        self.brush._BrushTask__is_allow_new_torrent = Mock(return_value=True)
        with patch("app.brushtask.RssParser.parse_rssxml", return_value=[]) as parse:
            self.brush.check_task_rss(1)

        parse.assert_called_once_with("https://site.example/rss")
        self.manager.create_group.assert_not_called()

    def test_manual_removal_allows_explicit_disabled_ids_but_default_run_skips_them(self):
        self.remover_database.get_torrent_remove_tasks.return_value = [self._remove_task(1, enabled=0)]
        self.remover.init_config()
        self.remover.downloader.get_remove_torrents.return_value = []

        self.remover.auto_remove_torrents()
        self.remover.downloader.get_remove_torrents.assert_not_called()
        for task_ids in (1, [1]):
            with self.subTest(task_ids=task_ids):
                self.remover.downloader.get_remove_torrents.reset_mock()
                self.remover.auto_remove_torrents(taskids=task_ids)
                self.remover.downloader.get_remove_torrents.assert_called_once()

        self.manager.create_group.assert_not_called()


if __name__ == "__main__":
    unittest.main()
