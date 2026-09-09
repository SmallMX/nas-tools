import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


_test_config_dir = None
if not os.environ.get("NASTOOL_CONFIG"):
    _test_config_dir = tempfile.TemporaryDirectory(prefix="nastool-filter-tests-")
    os.environ["NASTOOL_CONFIG"] = str(Path(_test_config_dir.name) / "config.yaml")

from app.filter import Filter


class FilterTest(unittest.TestCase):
    def setUp(self):
        filter_class = Filter.__closure__[0].cell_contents
        self.service = filter_class.__new__(filter_class)
        self.media = SimpleNamespace(org_string="Movie.2026.1080p.WEB-DL")

    def test_promotion_options_match_only_the_selected_factors(self):
        promotions = [
            (1.0, 1.0),
            (1.0, 0.0),
            (2.0, 1.0),
            (2.0, 0.0),
            (1.0, 0.5),
            (2.0, 0.5),
            (1.0, 0.7),
            (1.0, 0.3),
        ]
        for selected in promotions:
            for actual in promotions:
                with self.subTest(selected=selected, actual=actual):
                    matched, priority, message = self.service.check_torrent_filter(
                        self.media,
                        {"sp_state": f"{selected[0]} {selected[1]}"},
                        uploadvolumefactor=actual[0],
                        downloadvolumefactor=actual[1],
                    )

                    self.assertEqual(selected == actual, matched)
                    self.assertEqual(0, priority)
                    self.assertEqual(
                        "" if matched else f"{self.media.org_string} 不符合促销要求",
                        message,
                    )

    def test_zero_upload_factor_is_not_treated_as_missing(self):
        self.assertFalse(self.service.check_torrent_filter(
            self.media, {"sp_state": "1.0 *"}, uploadvolumefactor=0.0,
        )[0])
        self.assertTrue(self.service.check_torrent_filter(
            self.media, {"sp_state": "0.0 *"}, uploadvolumefactor=0.0,
        )[0])

    def test_wildcard_factors_allow_zero_and_other_promotions(self):
        for promotion, upload, download in (
                ("* *", 0.0, 0.0),
                ("* 0.0", 2.0, 0.0),
                ("2.0 *", 2.0, 0.0),
                ("* *", 1.0, 0.5)):
            with self.subTest(promotion=promotion, upload=upload, download=download):
                self.assertTrue(self.service.check_torrent_filter(
                    self.media, {"sp_state": promotion}, upload, download,
                )[0])

    def test_missing_factors_skip_only_the_missing_dimension(self):
        for upload, download, expected in (
                (None, None, True),
                (None, 0.0, True),
                (None, 1.0, False),
                (2.0, None, True),
                (1.0, None, False)):
            with self.subTest(upload=upload, download=download):
                self.assertEqual(expected, self.service.check_torrent_filter(
                    self.media, {"sp_state": "2.0 0.0"}, upload, download,
                )[0])

    def test_no_promotion_filter_accepts_zero_factors(self):
        self.assertTrue(self.service.check_torrent_filter(
            self.media, {}, uploadvolumefactor=0.0, downloadvolumefactor=0.0,
        )[0])


if __name__ == "__main__":
    unittest.main()
