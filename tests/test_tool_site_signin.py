import unittest
from unittest.mock import patch

from app.helper import DbHelper
from app.tools import SiteSignin


class ToolSiteSigninTest(unittest.TestCase):
    SITE_IDS = (91001, 91002)

    def setUp(self):
        self.service = SiteSignin()
        self.dbhelper = DbHelper()
        self.dbhelper.delete_site_signin_history(self.SITE_IDS)
        self.sign_site = {
            "id": self.SITE_IDS[0],
            "name": "签到站点",
            "signurl": "https://signin.example/",
            "cookie": "session=test",
        }
        self.login_site = {
            "id": self.SITE_IDS[1],
            "name": "保号站点",
            "signurl": "https://login.example/",
            "cookie": "session=test",
        }
        self.sites_patch = patch.object(
            self.service.sites,
            "get_sites",
            side_effect=self._get_sites,
        )
        self.sites_patch.start()

    def tearDown(self):
        self.sites_patch.stop()
        self.dbhelper.delete_site_signin_history(self.SITE_IDS)

    def _get_sites(self, signin=False, login=False, **kwargs):
        if signin:
            return [self.sign_site]
        if login:
            return [self.login_site]
        return []

    def test_successful_tasks_are_recorded_and_skipped_on_same_day(self):
        with patch.object(self.service, "_signin_site", return_value=(True, "签到成功")) as signin_mock, \
                patch.object(self.service, "_login_site", return_value=(True, "保号登录成功")) as login_mock:
            first = self.service.signin(force=True, notify=False)
            second = self.service.signin(force=False, notify=False)

        self.assertEqual(0, first["code"])
        self.assertEqual(2, len(first["results"]))
        self.assertEqual([], second["results"])
        self.assertEqual(2, second["skipped"])
        signin_mock.assert_called_once()
        login_mock.assert_called_once()

        status = self.service.get_status()
        self.assertEqual({"total": 2, "success": 2, "failed": 0, "pending": 0}, status["summary"])

    def test_failed_task_matching_keyword_is_retried(self):
        self.login_site = None

        def signin_only(signin=False, login=False, **kwargs):
            return [self.sign_site] if signin else []

        self.sites_patch.stop()
        self.sites_patch = patch.object(self.service.sites, "get_sites", side_effect=signin_only)
        self.sites_patch.start()

        with patch.object(
                self.service,
                "_signin_site",
                return_value=(False, "签到失败，Cookie 已失效"),
        ) as signin_mock:
            self.service.signin(force=True, notify=False)
            self.service.signin(force=False, notify=False)

        self.assertEqual(2, signin_mock.call_count)
        history = self.dbhelper.get_site_signin_history(limit=10)
        matching = [item for item in history if item.site_id == self.SITE_IDS[0]]
        self.assertEqual(2, len(matching))
        self.assertTrue(all(not item.success for item in matching))


if __name__ == "__main__":
    unittest.main()
