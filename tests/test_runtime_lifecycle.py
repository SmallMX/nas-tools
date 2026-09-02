import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ruamel.yaml import YAML

from app.helper.thread_helper import ThreadHelper
from app.message import Message
from check_config import is_public_bind_address


class RuntimeLifecycleTest(unittest.TestCase):
    def test_compose_passes_publish_address_to_security_check(self):
        compose_path = Path(__file__).resolve().parents[1] / "docker" / "compose.yml"
        with compose_path.open(encoding="utf-8") as compose_file:
            compose = YAML(typ="safe").load(compose_file)
        service = compose["services"]["nas-tools"]
        self.assertEqual(
            "${NASTOOL_BIND_ADDRESS:-0.0.0.0}",
            service["environment"]["NASTOOL_BIND_ADDRESS"],
        )
        self.assertIn("${NASTOOL_BIND_ADDRESS:-0.0.0.0}", service["ports"][0])

    def test_publish_address_classification(self):
        for address in ("127.0.0.1", "[::1]", "localhost"):
            self.assertFalse(is_public_bind_address(address), address)
        for address in ("0.0.0.0", "::", "192.168.1.10", ""):
            self.assertTrue(is_public_bind_address(address), address)

    def test_gunicorn_worker_exit_runs_application_shutdown(self):
        config_path = Path(__file__).resolve().parents[1] / "docker" / "gunicorn.conf.py"
        spec = importlib.util.spec_from_file_location("nastool_gunicorn_config", config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        shutdown_calls = []
        fake_run = types.SimpleNamespace(shutdown_system=lambda: shutdown_calls.append(True))
        with patch.dict(sys.modules, {"run": fake_run}):
            module.worker_exit(None, None)

        self.assertEqual([True], shutdown_calls)

    def test_thread_pool_can_restart_after_idempotent_shutdown(self):
        helper = ThreadHelper()
        helper.shutdown()
        helper.shutdown()
        helper.init_config()
        future = helper.start_thread(lambda: 7, ())
        self.assertEqual(7, future.result(timeout=2))
        helper.shutdown()

    def test_message_shutdown_is_idempotent_and_stops_all_active_clients(self):
        message_class = Message.__closure__[0].cell_contents
        service = message_class.__new__(message_class)
        first_client = Mock()
        second_client = Mock()
        service._active_clients = [
            {"name": "first", "client": first_client},
            {"name": "second", "client": second_client},
        ]
        service._active_interactive_clients = {"first": service._active_clients[0]}

        service.stop_service()
        service.stop_service()

        first_client.stop_service.assert_called_once_with()
        second_client.stop_service.assert_called_once_with()
        self.assertEqual([], service._active_clients)
        self.assertEqual({}, service._active_interactive_clients)

    def test_message_clients_stop_before_thread_pool_shutdown(self):
        run_path = Path(__file__).resolve().parents[1] / "run.py"
        source = run_path.read_text(encoding="utf-8")

        self.assertLess(source.index("Message().stop_service()"), source.index("ThreadHelper().shutdown()"))


if __name__ == "__main__":
    unittest.main()
