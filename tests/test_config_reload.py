import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock, call, patch

from ruamel.yaml import YAML
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from app.config_reload import ConfigFileEventHandler, ConfigReloader
from config import Config


class ConfigReloadTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="nastool-config-reload-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "config.yaml"
        # 使用真实读写实现，但不替换测试套件的全局配置或环境变量。
        config_class = type(Config())
        self.config = config_class.__new__(config_class)
        self.config._config_path = str(self.path)
        self.initial = {"app": {"name": "initial"}, "tools": {"site_signin": {"cron": "08:00"}}}
        self.config.save_config(self.initial)
        self.apply = Mock(return_value=None)
        self.reloader = ConfigReloader(self.config, self.apply)

    def _changed(self, name="updated"):
        updated = copy.deepcopy(self.initial)
        updated["app"]["name"] = name
        return updated

    def _write_external(self, config):
        with self.path.open("w", encoding="utf-8") as output:
            YAML().dump(config, output)

    def test_unchanged_content_does_not_apply_for_any_entry(self):
        self.reloader.apply_current()
        self.reloader.reload()
        self.reloader.save(copy.deepcopy(self.initial))

        self.apply.assert_not_called()
        self.assertEqual(self.initial, self.config.get_config())

    def test_manual_save_and_following_file_events_apply_once(self):
        updated = self._changed()
        self.assertTrue(self.reloader.save(updated))
        handler = ConfigFileEventHandler(str(self.path), self.reloader.reload)

        handler.dispatch(FileModifiedEvent(str(self.path)))
        handler.dispatch(FileCreatedEvent(str(self.path)))
        handler.dispatch(FileMovedEvent(str(self.path.parent / ".config-new.tmp"), str(self.path)))

        self.apply.assert_called_once_with(self.initial, updated)
        self.assertEqual(updated, self.config.get_config())

    def test_consecutive_different_saves_are_both_applied_without_delay(self):
        first = self._changed("first")
        second = self._changed("second")

        self.assertTrue(self.reloader.save(first))
        self.assertTrue(self.reloader.save(second))

        self.assertEqual([call(self.initial, first), call(first, second)], self.apply.call_args_list)
        self.assertEqual(second, self.config.get_config())
        self.reloader.reload()
        self.assertEqual(2, self.apply.call_count)

    def test_false_or_exception_from_apply_can_retry_same_configuration(self):
        updated = self._changed()
        for failure in (False, RuntimeError("apply failed")):
            with self.subTest(failure=type(failure).__name__):
                self.config.save_config(self.initial)
                apply = Mock(side_effect=[failure, True])
                reloader = ConfigReloader(self.config, apply)

                self.assertFalse(reloader.save(updated))
                self.assertEqual(updated, self.config.get_config())
                self.assertTrue(reloader.apply_current())

                self.assertEqual([
                    call(self.initial, updated),
                    call(self.initial, updated, retry_paths=frozenset({"app.name"})),
                ], apply.call_args_list)
                reloader.reload()
                self.assertEqual(2, apply.call_count)

    def test_restoring_previous_config_repairs_partially_applied_runtime(self):
        updated = self._changed()
        updated["tools"]["site_signin"]["cron"] = "09:00"
        runtime = {"app.name": "initial", "tools.site_signin.cron": "08:00"}
        original_runtime = runtime.copy()
        attempts = []

        def values(config):
            return {"app.name": config["app"]["name"],
                    "tools.site_signin.cron": config["tools"]["site_signin"]["cron"]}

        def apply(previous, current, retry_paths=()):
            attempts.append(frozenset(retry_paths))
            before, after = values(previous), values(current)
            for path in runtime:
                if before[path] != after[path] or path in retry_paths:
                    runtime[path] = after[path]
                if path == "app.name" and len(attempts) == 1:
                    # 第一项已生效，但后续服务失败，整体应用未成功。
                    return False
            return True

        reloader = ConfigReloader(self.config, apply)
        self.assertFalse(reloader.save(updated))
        self.assertEqual({"app.name": "updated", "tools.site_signin.cron": "08:00"}, runtime)

        self.assertTrue(reloader.save(copy.deepcopy(self.initial)))

        self.assertEqual(original_runtime, runtime)
        self.assertEqual(2, len(attempts))
        reloader.reload()
        self.assertEqual(2, len(attempts), "恢复成功后应清除待重试状态")

    def test_multiple_failed_changes_accumulate_paths_until_runtime_is_restored(self):
        first = self._changed("first")
        second = copy.deepcopy(self.initial)
        second["tools"]["site_signin"]["cron"] = "10:00"
        runtime = {"app.name": "initial", "tools.site_signin.cron": "08:00"}
        original_runtime = runtime.copy()
        attempts = []

        def values(config):
            return {"app.name": config["app"]["name"],
                    "tools.site_signin.cron": config["tools"]["site_signin"]["cron"]}

        def apply(previous, current, retry_paths=()):
            attempts.append(frozenset(retry_paths))
            before, after = values(previous), values(current)
            # 两轮失败分别只来得及更新不同服务；剩余服务仍保留旧运行值。
            paths = (["app.name"] if len(attempts) == 1 else ["tools.site_signin.cron"]
                     if len(attempts) == 2 else list(runtime))
            for path in paths:
                if before[path] != after[path] or path in retry_paths:
                    runtime[path] = after[path]
            return len(attempts) >= 3

        reloader = ConfigReloader(self.config, apply)
        self.assertFalse(reloader.save(first))
        self.assertFalse(reloader.save(second))
        self.assertEqual({"app.name": "first", "tools.site_signin.cron": "10:00"}, runtime)

        self.assertTrue(reloader.save(copy.deepcopy(self.initial)))

        self.assertEqual(original_runtime, runtime)
        self.assertEqual(frozenset({"app.name", "tools.site_signin.cron"}), attempts[-1])
        self.assertEqual(3, len(attempts))
        reloader.apply_current()
        self.assertEqual(3, len(attempts), "全部恢复后不应继续强制刷新")

    def test_failed_save_does_not_apply_or_advance_snapshot(self):
        updated = self._changed()
        original_bytes = self.path.read_bytes()
        with patch.object(self.config, "save_config", return_value=False):
            self.assertFalse(self.reloader.save(updated))

        self.apply.assert_not_called()
        self.assertEqual(original_bytes, self.path.read_bytes())
        self.assertEqual(self.initial, self.config.get_config())
        self.assertTrue(self.reloader.save(updated))
        self.apply.assert_called_once_with(self.initial, updated)

    def test_save_exception_is_preserved_without_applying_configuration(self):
        error = OSError("configuration write failed")
        with patch.object(self.config, "save_config", side_effect=error):
            with self.assertRaises(OSError) as raised:
                self.reloader.save(self._changed())

        self.assertIs(error, raised.exception)
        self.apply.assert_not_called()
        self.assertEqual(self.initial, self.config.get_config())

    def test_invalid_external_file_keeps_previous_config_and_immediate_fix_is_loaded(self):
        updated = self._changed()
        for invalid_yaml in ("app: [\n", "- not-a-mapping\n", ""):
            with self.subTest(content=invalid_yaml):
                self.config.save_config(self.initial)
                apply = Mock(return_value=None)
                reloader = ConfigReloader(self.config, apply)
                self.path.write_text(invalid_yaml, encoding="utf-8")

                self.assertFalse(reloader.reload())
                self.assertEqual(self.initial, self.config.get_config())
                self.assertEqual(invalid_yaml, self.path.read_text(encoding="utf-8"))
                apply.assert_not_called()

                self._write_external(updated)
                self.assertTrue(reloader.reload())
                apply.assert_called_once_with(self.initial, updated)
                self.assertEqual(updated, self.config.get_config())

    def test_applied_snapshot_is_independent_of_nested_live_config_changes(self):
        self.config.get_config()["tools"]["site_signin"]["cron"] = "09:00"
        updated = copy.deepcopy(self.config.get_config())

        self.assertTrue(self.reloader.apply_current())

        self.apply.assert_called_once_with(self.initial, updated)
        self.assertEqual("08:00", self.initial["tools"]["site_signin"]["cron"])
        self.reloader.apply_current()
        self.assertEqual(1, self.apply.call_count)

    def test_save_does_not_mutate_or_retain_the_callers_configuration(self):
        updated = self._changed()
        expected = copy.deepcopy(updated)

        self.assertTrue(self.reloader.save(updated))

        self.assertEqual(expected, updated)
        updated["tools"]["site_signin"]["cron"] = "11:00"
        self.assertEqual(expected, self.config.get_config())
        self.reloader.apply_current()
        self.apply.assert_called_once_with(self.initial, expected)

    def test_reload_waits_until_in_progress_save_application_finishes(self):
        first = self._changed("first")
        second = self._changed("second")
        applying_first = Event()
        release_first = Event()
        reload_started = Event()
        read_started = Event()
        applications = []

        def apply(previous, current):
            applications.append((copy.deepcopy(previous), copy.deepcopy(current)))
            if current == first:
                applying_first.set()
                if not release_first.wait(timeout=3):
                    raise TimeoutError("test did not release first application")
                self.assertEqual(first, self.config.get_config())

        def read_config():
            read_started.set()
            return original_read()

        def reload_config():
            reload_started.set()
            return reloader.reload()

        reloader = ConfigReloader(self.config, apply)
        original_read = self.config.init_config
        with patch.object(self.config, "init_config", side_effect=read_config), ThreadPoolExecutor(max_workers=2) as pool:
            first_result = pool.submit(reloader.save, first)
            try:
                self.assertTrue(applying_first.wait(timeout=2))
                self._write_external(second)
                second_result = pool.submit(reload_config)
                self.assertTrue(reload_started.wait(timeout=2))
                self.assertFalse(read_started.wait(timeout=0.05), "文件读取不得穿插正在进行的配置应用")
            finally:
                release_first.set()
            self.assertTrue(first_result.result(timeout=2))
            self.assertTrue(second_result.result(timeout=2))

        self.assertEqual([(self.initial, first), (first, second)], applications)
        self.assertEqual(second, self.config.get_config())


class ConfigFileEventHandlerTest(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.gettempdir()) / "nastool-event-target" / "config.yaml")
        self.reload = Mock()
        self.handler = ConfigFileEventHandler(self.path, self.reload)

    def test_target_modified_created_and_moved_in_trigger_reload(self):
        events = (FileModifiedEvent(self.path), FileCreatedEvent(self.path),
                  FileMovedEvent(str(Path(self.path).parent / "new.tmp"), self.path))
        for event in events:
            with self.subTest(event=type(event).__name__):
                self.reload.reset_mock()
                self.handler.dispatch(event)
                self.reload.assert_called_once_with()

    def test_directories_unrelated_files_and_move_out_are_ignored(self):
        other_path = str(Path(self.path).parent.parent / "other" / "config.yaml")
        events = (
            DirModifiedEvent(self.path), DirCreatedEvent(self.path), DirMovedEvent(other_path, self.path),
            FileModifiedEvent(other_path), FileCreatedEvent(self.path + ".tmp"),
            FileMovedEvent(other_path, self.path + ".bak"), FileMovedEvent(self.path, other_path),
        )
        for event in events:
            with self.subTest(event=type(event).__name__, path=event.src_path):
                self.handler.dispatch(event)
                self.reload.assert_not_called()

    def test_callback_failure_does_not_prevent_next_file_event(self):
        self.reload.side_effect = [OSError("temporary read failure"), True]

        self.handler.dispatch(FileModifiedEvent(self.path))
        self.handler.dispatch(FileModifiedEvent(self.path))

        self.assertEqual([call(), call()], self.reload.call_args_list)


if __name__ == "__main__":
    unittest.main()
