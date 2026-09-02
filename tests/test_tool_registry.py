import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.tools import ToolSource, get_tool, get_tools
from web.permissions import PATH_PERMISSIONS
from web.tools.site_signin import SiteSigninWebService


class ToolRegistryTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_tools_have_unique_stable_ids_and_deterministic_order(self):
        tools = get_tools()
        tool_ids = [tool.tool_id for tool in tools]

        self.assertEqual(len(tool_ids), len(set(tool_ids)))
        self.assertEqual(tools, tuple(sorted(tools, key=lambda tool: (tool.order, tool.tool_id))))

    def test_site_signin_is_registered_as_native_tool(self):
        tool = get_tool("site_signin")

        self.assertIsNotNone(tool)
        self.assertEqual("tools/site-signin", tool.page)
        self.assertEqual("站点管理", tool.permission)
        self.assertIsNone(tool.source)

    def test_tool_pages_and_icons_match_host_registry(self):
        for tool in get_tools():
            with self.subTest(tool=tool.tool_id):
                self.assertEqual(tool.permission, PATH_PERMISSIONS.get(f"/{tool.page}"))
                self.assertTrue((self.ROOT / "web/static/img" / tool.icon).is_file())

    def test_external_tool_source_requires_complete_audit_metadata(self):
        with self.assertRaises(ValueError):
            ToolSource(
                repository="https://example.invalid/repository",
                path="plugins/example",
                revision="",
                author="upstream",
                license="GPL-3.0",
            )

    def test_site_signin_config_accepts_supported_schedules(self):
        for value in ("", "23.5", "08:00", "08:00-09:00"):
            with self.subTest(value=value):
                self.assertEqual(value, SiteSigninWebService._normalize_cron(value))

        for value in ("0", "24:00", "09:00-08:00", "invalid"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                SiteSigninWebService._normalize_cron(value)

    def test_site_signin_config_rejects_invalid_retry_regex(self):
        with self.assertRaises(ValueError):
            SiteSigninWebService._normalize_retry_keyword("[")

    def test_site_signin_config_is_saved_in_tool_namespace(self):
        config_manager = MagicMock()
        config_manager.get_config.side_effect = lambda node=None: (
            {"site_signin": {}} if node == "tools" else {"pt": {}, "tools": {"site_signin": {}}}
        )
        config_manager.save_config.return_value = True
        service = SiteSigninWebService()

        with patch("app.tools.site_signin.config.Config", return_value=config_manager), \
                patch("web.tools.site_signin.Config", return_value=config_manager), \
                patch.object(service._service, "init_config"):
            response = service.update_config({
                "cron": "08:00-09:00",
                "concurrency": "4",
                "retry_keyword": "失败|超时",
                "notify": False,
                "history_days": "60",
            })

        self.assertEqual(0, response["code"])
        saved = config_manager.save_config.call_args.args[0]
        self.assertNotIn("ptsignin_cron", saved["pt"])
        self.assertEqual(
            {
                "cron": "08:00-09:00",
                "concurrency": 4,
                "retry_keyword": "失败|超时",
                "notify": False,
                "history_days": 60,
            },
            saved["tools"]["site_signin"],
        )


if __name__ == "__main__":
    unittest.main()
