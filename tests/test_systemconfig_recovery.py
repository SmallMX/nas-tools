import unittest
from unittest.mock import patch

from app.conf.systemconfig import SystemConfig


class SystemConfigRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.config_class = SystemConfig.__closure__[0].cell_contents
        self.records = {}
        self.helper_patch = patch("app.conf.systemconfig.DictHelper")
        self.helper = self.helper_patch.start().return_value
        self.addCleanup(self.helper_patch.stop)
        self.helper.get.side_effect = lambda dtype, key: self.records.get(key, "")

    def test_bad_json_does_not_block_other_records_or_overwrite_database(self):
        self.records.update({
            "DefaultDownloadSetting": "17",
            "CookieCloud": '{"password":"sensitive-value",',
            "CookieUserInfo": '{"username":"test-user"}',
            "CustomScript": '{"css":"body {}"}',
        })

        with patch("app.conf.systemconfig.log.warn") as warn:
            config = self.config_class()

        self.assertEqual({}, config.get_system_config("CookieCloud"))
        self.assertEqual("17", config.get_system_config("DefaultDownloadSetting"))
        self.assertEqual({"username": "test-user"}, config.get_system_config("CookieUserInfo"))
        self.assertEqual({"css": "body {}"}, config.get_system_config("CustomScript"))
        self.assertEqual('{"password":"sensitive-value",', self.records["CookieCloud"])
        self.helper.set.assert_not_called()
        self.helper.delete.assert_not_called()
        warn.assert_called_once()
        self.assertIn("CookieCloud", warn.call_args.args[0])
        self.assertNotIn("sensitive-value", warn.call_args.args[0])

    def test_invalid_json_types_use_stable_dictionary_defaults(self):
        for raw in ("[]", "null", "true", "17", '"secret-value"', b"\xff", {"key": "value"}):
            with self.subTest(raw=raw), patch("app.conf.systemconfig.log.warn"):
                self.records["CookieCloud"] = raw
                config = self.config_class()
                self.assertEqual({}, config.get_system_config("CookieCloud"))
                self.records["CookieCloud"] = '{"server":"https://cloud.example"}'
                config.init_config("CookieCloud")
                self.assertEqual(
                    {"server": "https://cloud.example"},
                    config.get_system_config("CookieCloud"),
                )

    def test_reload_uses_declared_type_instead_of_mutated_cache_type(self):
        config = self.config_class()
        config.systemconfig["CookieCloud"] = "old-invalid-value"
        self.records["CookieCloud"] = '{"server":"https://cloud.example"}'

        config.init_config("CookieCloud")

        self.assertEqual({"server": "https://cloud.example"}, config.get_system_config("CookieCloud"))

    def test_missing_values_restore_independent_defaults(self):
        first = self.config_class()
        second = self.config_class()
        first.get_system_config("CookieCloud")["server"] = "https://first.example"

        self.assertEqual({}, second.get_system_config("CookieCloud"))
        self.assertEqual({}, first.get_system_config("CustomScript"))
        self.assertEqual({}, self.config_class._DEFAULTS["CookieCloud"])
        self.assertIsNone(first.get_system_config("DefaultDownloadSetting"))
        first.init_config("CookieCloud")
        self.assertEqual({}, first.get_system_config("CookieCloud"))

    def test_reloading_one_bad_record_preserves_other_cached_values(self):
        self.records["CustomScript"] = '{"css":"body {}"}'
        config = self.config_class()
        self.records["CookieCloud"] = "invalid"
        self.records["CustomScript"] = '{"css":"changed"}'

        with patch("app.conf.systemconfig.log.warn"):
            config.init_config("CookieCloud")

        self.assertEqual({}, config.get_system_config("CookieCloud"))
        self.assertEqual({"css": "body {}"}, config.get_system_config("CustomScript"))

    def test_saved_configuration_can_replace_a_corrupt_record(self):
        self.records["CookieCloud"] = "invalid"
        with patch("app.conf.systemconfig.log.warn"):
            config = self.config_class()

        def save(dtype, key, value):
            self.records[key] = value
            return True

        self.helper.set.side_effect = save
        self.assertTrue(config.set_system_config("CookieCloud", {"server": "https://cloud.example"}))
        self.assertEqual({"server": "https://cloud.example"}, config.get_system_config("CookieCloud"))


if __name__ == "__main__":
    unittest.main()
