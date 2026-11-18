import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from web.actions.download import DownloadActions
from web.routes.system_files import system_files_bp


class SystemFileLifecycleTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        config = self.enterContext(patch("web.routes.system_files.Config")).return_value
        config.get_config_path.return_value = directory.name
        config.get_config.return_value = {}
        config.get_temp_path.return_value = self.root / "temp"
        app = Flask(__name__)
        app.config["LOGIN_DISABLED"] = True
        app.register_blueprint(system_files_bp)
        self.client = app.test_client()

    def test_same_chinese_filename_has_distinct_contents_and_original_title(self):
        uploads = []
        for content in (b"first", b"second"):
            response = self.client.post("/upload", data={"file": (io.BytesIO(content), "流浪地球.torrent")})
            item = response.get_json()
            self.assertEqual(0, item["code"])
            self.assertEqual("流浪地球.torrent", item["original_filename"])
            self.assertEqual(content, (self.root / "temp" / item["filename"]).read_bytes())
            uploads.append({"upload": item})
        self.assertEqual([b"first", b"second"], sorted(p.read_bytes() for p in (self.root / "temp").iterdir()))

        received = []

        def submit(media_info, torrent_file, **_kwargs):
            received.append((media_info.org_string, Path(torrent_file).read_bytes()))
            return True, ""

        with patch("web.actions.download.Config") as config, patch("web.actions.download.Media") as media, \
                patch("web.actions.download.Downloader") as downloader, patch("web.actions.download.Message"):
            config.return_value.get_temp_path.return_value = self.root / "temp"
            media.return_value.get_media_info.return_value = None
            downloader.return_value.download.side_effect = submit
            result = DownloadActions.download_torrent({"files": uploads})
        self.assertEqual({"code": 0, "msg": "成功添加 2 个下载任务"}, result)
        self.assertEqual([("流浪地球.torrent", b"first"), ("流浪地球.torrent", b"second")], received)
        self.assertEqual([], list((self.root / "temp").iterdir()))

    def test_each_streamed_backup_is_cleaned_on_completion_or_disconnect(self):
        (self.root / "config.yaml").write_text("app: {}")
        connection = sqlite3.connect(self.root / "user.db")
        connection.close()
        first = self.client.post("/backup", buffered=False)
        second = self.client.post("/backup", buffered=False)
        try:
            self.assertEqual((200, 200), (first.status_code, second.status_code))
            self.assertEqual(2, len(list(self.root.rglob("*.zip"))))
            with zipfile.ZipFile(io.BytesIO(first.get_data())) as archive:
                self.assertEqual(["config.yaml", "user.db"], sorted(archive.namelist()))
            first.close()
            self.assertEqual(1, len(list(self.root.rglob("*.zip"))))
        finally:
            first.close()
            second.close()
        self.assertEqual({"user.db", "config.yaml"}, {p.name for p in self.root.iterdir()})
