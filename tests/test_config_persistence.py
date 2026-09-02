import copy
import json
import sqlite3
import stat
import unittest
from contextlib import closing
from pathlib import Path

import ruamel.yaml

from check_config import initialize_config
from app.db import MainDb, init_db, remove_db_session
from app.db.models import ConfigSite
from app.db.main_db import (
    RETIRED_DATABASE_COLUMNS,
    RETIRED_DATABASE_FILES,
    RETIRED_DATABASE_TABLES,
    SUPPORTED_MESSAGE_SWITCHES,
)
from config import Config


class ConfigPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config_path = Path(self.config.get_config_path()) / "config.yaml"
        self.database_path = Path(self.config.get_config_path()) / "user.db"
        self.credentials_path = Path(self.config.get_config_path()) / "initial-credentials.txt"
        self.original_config = copy.deepcopy(self.config.get_config())

    def tearDown(self):
        self.config.save_config(self.original_config)

    def test_sensitive_files_are_private(self):
        self.assertEqual(0o700, stat.S_IMODE(self.config_path.parent.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(self.config_path.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(self.database_path.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(self.credentials_path.stat().st_mode))
        for sidecar_path in self.database_path.parent.glob("user.db-*"):
            self.assertEqual(0o600, stat.S_IMODE(sidecar_path.stat().st_mode))

        security_config = self.config.get_config("security")
        self.assertGreaterEqual(len(security_config["telegram_webhook_secret"]), 32)
        self.assertGreaterEqual(len(security_config["flask_secret_key"]), 48)

    def test_save_config_is_valid_and_atomic(self):
        updated_config = copy.deepcopy(self.original_config)
        updated_config["test_persistence"] = {"enabled": True}

        self.assertTrue(self.config.save_config(updated_config))

        with self.config_path.open(mode="r", encoding="utf-8") as config_file:
            persisted = ruamel.yaml.YAML(typ="safe").load(config_file)
        self.assertEqual({"enabled": True}, persisted["test_persistence"])
        self.assertEqual([], list(self.config_path.parent.glob(".config-*.tmp")))

    def test_failed_serialization_keeps_previous_file(self):
        original_contents = self.config_path.read_bytes()
        invalid_config = copy.deepcopy(self.original_config)
        invalid_config["not_yaml_serializable"] = object()

        with self.assertRaises(Exception):
            self.config.save_config(invalid_config)

        self.assertEqual(original_contents, self.config_path.read_bytes())
        self.assertEqual([], list(self.config_path.parent.glob(".config-*.tmp")))

    def test_invalid_external_config_is_not_loaded_or_overwritten(self):
        self.config_path.write_text("app: [\n", encoding="utf-8")

        self.assertFalse(self.config.init_config())
        self.assertEqual(self.original_config, self.config.get_config())
        self.assertEqual("app: [\n", self.config_path.read_text(encoding="utf-8"))

    def test_initialize_config_removes_retired_feature_keys(self):
        retired_sections = (
            "jackett", "prowlarr", "client115", "aria2", "pikpak",
            "emby", "jellyfin", "plex", "scraper_nfo", "scraper_pic",
            "sync", "subtitle", "message",
        )
        retired_pt_keys = (
            "search_indexer", "pt_check_interval", "search_rss_interval",
            "search_no_result_rss", "pt_monitor", "rmt_mode",
        )
        config_with_retired_keys = copy.deepcopy(self.original_config)
        for section in retired_sections:
            config_with_retired_keys[section] = {"secret": "retired"}
        config_with_retired_keys.setdefault("pt", {}).update({
            key: "retired" for key in retired_pt_keys
        })
        config_with_retired_keys["pt"]["pt_client"] = "client115"
        config_with_retired_keys["media"] = {
            "category": "default-category",
            "movie_path": "/retired",
            "refresh_mediaserver": True,
        }
        config_with_retired_keys["douban"] = {
            "cookie": "preserved",
            "users": ["retired"],
            "auto_rss": True,
        }
        config_with_retired_keys.setdefault("security", {})[
            "media_server_webhook_allow_ip"
        ] = "retired"
        config_with_retired_keys["security"]["synology_webhook_allow_ip"] = "retired"
        config_with_retired_keys.setdefault("app", {})["init_files"] = ["retired.sql"]
        config_with_retired_keys.setdefault("qbittorrent", {})["force_upload"] = True
        self.config.save_config(config_with_retired_keys)

        initialize_config()

        cleaned_config = self.config.get_config()
        for section in retired_sections:
            self.assertNotIn(section, cleaned_config)
        for key in retired_pt_keys:
            self.assertNotIn(key, cleaned_config["pt"])
        self.assertEqual("qbittorrent", cleaned_config["pt"]["pt_client"])
        self.assertEqual({"category": "default-category"}, cleaned_config["media"])
        self.assertEqual({"cookie": "preserved"}, cleaned_config["douban"])
        self.assertNotIn("media_server_webhook_allow_ip", cleaned_config["security"])
        self.assertNotIn("synology_webhook_allow_ip", cleaned_config["security"])
        self.assertNotIn("init_files", cleaned_config["app"])
        self.assertNotIn("force_upload", cleaned_config["qbittorrent"])

    def test_example_config_uses_empty_external_service_defaults(self):
        template_path = Path(self.config.get_inner_config_path()) / "config.example.yaml"
        template_contents = template_path.read_text(encoding="utf-8")
        template_config = ruamel.yaml.YAML(typ="safe").load(template_contents)

        self.assertNotIn("nastool.cn", template_contents)
        self.assertEqual("", template_config["app"]["ocr_server"])
        self.assertEqual("", template_config["laboratory"]["tmdb_proxy"])
        self.assertFalse(any(str(key).startswith("ptsignin") for key in template_config["pt"]))
        self.assertEqual(5, template_config["tools"]["site_signin"]["concurrency"])

    def test_database_initialization_removes_retired_feature_storage(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            for table in RETIRED_DATABASE_TABLES:
                physical_table = table.upper() if table == "rss_history" else table
                connection.execute(
                    f'CREATE TABLE IF NOT EXISTS "{physical_table}" (id INTEGER PRIMARY KEY)'
                )
            for table, columns in RETIRED_DATABASE_COLUMNS.items():
                existing_columns = {
                    str(row[1]).lower()
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                for column in columns.difference(existing_columns):
                    connection.execute(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column.upper()}" TEXT'
                    )
            connection.execute(
                'INSERT INTO system_dict(type, "key", value) VALUES (?, ?, ?)',
                ("SystemConfig", "SpeedLimit", "retired"),
            )
            connection.execute(
                'INSERT INTO download_setting(name, downloader) VALUES (?, ?)',
                ("retired", "PikPak"),
            )
            connection.execute(
                'INSERT INTO message_client(name, type, config, switchs, enabled) '
                'VALUES (?, ?, ?, ?, ?)',
                ("retired-client", "bark", "{}", "[]", 0),
            )
            connection.execute(
                'INSERT INTO message_client(name, type, config, switchs, enabled) '
                'VALUES (?, ?, ?, ?, ?)',
                (
                    "telegram-migration",
                    "telegram",
                    "{}",
                    '["download_start", "rss_added", "transfer_finished", {}]',
                    0,
                ),
            )
            connection.execute(
                'INSERT INTO config_site(name, note) VALUES (?, ?)',
                ("site-migration", '{"rule": "retired", "subtitle": "Y", "message": "Y"}'),
            )
            connection.execute(
                'INSERT INTO config_users(name, password, pris) VALUES (?, ?, ?)',
                ("user-migration", "legacy-hash", "资源搜索,订阅管理,媒体整理,系统设置"),
            )
            connection.commit()

        for filename in RETIRED_DATABASE_FILES:
            (self.database_path.parent / filename).write_bytes(b"retired")

        init_db()

        with closing(sqlite3.connect(self.database_path)) as connection:
            existing_tables = {
                str(row[0]).lower()
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue(RETIRED_DATABASE_TABLES.isdisjoint(existing_tables))
            for table, columns in RETIRED_DATABASE_COLUMNS.items():
                existing_columns = {
                    str(row[1]).lower()
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                self.assertTrue(columns.isdisjoint(existing_columns))
            speed_limit_rows = connection.execute(
                'SELECT COUNT(*) FROM system_dict WHERE type = ? AND "key" = ?',
                ("SystemConfig", "SpeedLimit"),
            ).fetchone()[0]
            self.assertEqual(0, speed_limit_rows)
            retired_downloader = connection.execute(
                'SELECT downloader FROM download_setting WHERE name = ?',
                ("retired",),
            ).fetchone()[0]
            self.assertIsNone(retired_downloader)
            self.assertEqual(
                0,
                connection.execute(
                    'SELECT COUNT(*) FROM message_client WHERE name = ?',
                    ("retired-client",),
                ).fetchone()[0],
            )
            telegram_switches = connection.execute(
                'SELECT switchs FROM message_client WHERE name = ?',
                ("telegram-migration",),
            ).fetchone()[0]
            self.assertEqual('["download_start"]', telegram_switches)
            self.assertTrue(set(json.loads(telegram_switches)).issubset(SUPPORTED_MESSAGE_SWITCHES))
            site_note = connection.execute(
                'SELECT note FROM config_site WHERE name = ?',
                ("site-migration",),
            ).fetchone()[0]
            self.assertEqual({"message": "Y"}, json.loads(site_note))
            permissions = connection.execute(
                'SELECT pris FROM config_users WHERE name = ?',
                ("user-migration",),
            ).fetchone()[0]
            self.assertEqual("资源搜索,系统设置", permissions)
            connection.execute('DELETE FROM download_setting WHERE name = ?', ("retired",))
            connection.execute('DELETE FROM message_client WHERE name = ?', ("telegram-migration",))
            connection.execute('DELETE FROM config_site WHERE name = ?', ("site-migration",))
            connection.execute('DELETE FROM config_users WHERE name = ?', ("user-migration",))
            connection.commit()

        try:
            self.assertEqual(
                [],
                MainDb().query(ConfigSite).filter(ConfigSite.name == "site-migration").all(),
            )
        finally:
            remove_db_session()
        for filename in RETIRED_DATABASE_FILES:
            self.assertFalse((self.database_path.parent / filename).exists())


if __name__ == "__main__":
    unittest.main()
