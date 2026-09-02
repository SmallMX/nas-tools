import pickle
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.helper.meta_helper import (
    CACHE_EXPIRE_TIMESTAMP_STR,
    MetaHelper,
)


def meta_helper_instance(cache_path, meta_data=None, expire_enabled=False):
    helper_class = MetaHelper.__closure__[0].cell_contents
    helper = helper_class.__new__(helper_class)
    helper._meta_path = str(cache_path)
    helper._meta_data = meta_data or {}
    helper._tmdb_cache_expire = expire_enabled
    return helper


class MetaHelperTest(unittest.TestCase):
    def test_save_more_than_25_items_on_python_314(self):
        with tempfile.TemporaryDirectory(prefix="nastool-meta-tests-") as temp_dir:
            cache_path = Path(temp_dir) / "tmdb.dat"
            future_expiry = int(time.time()) + 3600
            meta_data = {
                f"item-{index}": {
                    "id": index + 1,
                    "title": f"Title {index}",
                    CACHE_EXPIRE_TIMESTAMP_STR: future_expiry,
                }
                for index in range(30)
            }
            helper = meta_helper_instance(cache_path, meta_data)

            helper.save_meta_data()

            with cache_path.open("rb") as cache_file:
                saved_data = pickle.load(cache_file)
            self.assertEqual(30, len(saved_data))
            self.assertEqual(0o600, stat.S_IMODE(cache_path.stat().st_mode))

    def test_expired_item_is_deleted_and_returns_empty_when_expiry_enabled(self):
        helper = meta_helper_instance(
            Path("unused-tmdb.dat"),
            {
                "expired": {
                    "id": 1,
                    "title": "Expired",
                    CACHE_EXPIRE_TIMESTAMP_STR: 999,
                }
            },
            expire_enabled=True,
        )

        with patch("app.helper.meta_helper.time.time", return_value=1000):
            result = helper.get_meta_data_by_key("expired")

        self.assertEqual({}, result)
        self.assertNotIn("expired", helper._meta_data)

    def test_atomic_save_failure_preserves_old_file_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory(prefix="nastool-meta-tests-") as temp_dir:
            cache_dir = Path(temp_dir)
            cache_path = cache_dir / "tmdb.dat"
            old_data = {"old": {"id": 1, "title": "Old"}}
            with cache_path.open("wb") as cache_file:
                pickle.dump(old_data, cache_file, pickle.HIGHEST_PROTOCOL)

            helper = meta_helper_instance(
                cache_path,
                {"new": {"id": 2, "title": "New"}},
            )

            with patch("app.helper.meta_helper.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    helper.save_meta_data(force=True)

            with cache_path.open("rb") as cache_file:
                self.assertEqual(old_data, pickle.load(cache_file))
            self.assertEqual([], list(cache_dir.glob(".tmdb-*.tmp")))


if __name__ == "__main__":
    unittest.main()
