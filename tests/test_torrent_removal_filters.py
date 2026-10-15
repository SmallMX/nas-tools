import copy
import re
import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.downloader.client import Qbittorrent, Transmission


class TorrentDict(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error


class TorrentRemovalFiltersTest(unittest.TestCase):
    GIB = 1024 ** 3
    CLIENTS = {"qb": Qbittorrent, "tr": Transmission}

    def setUp(self):
        self.now = datetime(2026, 10, 15, 12, 0)
        self.timestamp = int(time.mktime(self.now.timetuple()))
        for module in ("qbittorrent", "transmission"):
            patcher = patch(f"app.downloader.client.{module}.datetime")
            patcher.start().now.return_value = self.now
            self.addCleanup(patcher.stop)

    def _time_fields(self, client, age):
        if client == "qb":
            return {"completion_on": self.timestamp - age}
        return {"date_done": datetime.fromtimestamp(self.timestamp - age)}

    def _torrent(self, client, index, **overrides):
        if client == "qb":
            values = dict(hash=f"hash-{index}", name=f"Torrent {index}", ratio=2,
                          size=2 * self.GIB, uploaded=0,
                          completion_on=self.timestamp - 7200, added_on=self.timestamp - 10800,
                          save_path="/data/Movies", tracker=f"https://tracker.site{index}.example/announce",
                          state="uploading", category="Movies", tags="NASTOOL, managed")
            values.update(overrides)
            return TorrentDict(values)
        values = dict(id=index, name=f"Torrent {index}", ratio=2, total_size=2 * self.GIB,
                      uploaded_ever=0, date_done=datetime.fromtimestamp(self.timestamp - 7200),
                      date_added=datetime.fromtimestamp(self.timestamp - 10800),
                      download_dir="/data/Movies", status="seeding", error_string="",
                      trackers=[{"announce": f"https://tracker.site{index}.example/announce", "sitename": f"Site {index}"}],
                      labels=["NASTOOL", "managed"])
        values.update(overrides)
        return SimpleNamespace(**values)

    @staticmethod
    def _id(client, index):
        return f"hash-{index}" if client == "qb" else index

    def _search(self, client, torrents, config):
        instance = self.CLIENTS[client].__new__(self.CLIENTS[client])
        instance.get_torrents = Mock(return_value=(torrents, False))
        result = instance.get_remove_torrents(config)
        instance.get_torrents.assert_called_once_with()
        return result

    def test_numeric_filters_preserve_strict_ratio_time_size_and_upload_boundaries(self):
        for client in self.CLIENTS:
            size_field = "size" if client == "qb" else "total_size"
            upload_rows = []
            for uploaded in (102399, 102400, 102401):
                fields = {**self._time_fields(client, 100), size_field: 102400}
                fields.update({"uploaded": uploaded} if client == "qb" else {"ratio": uploaded / 102400})
                upload_rows.append(fields)
            cases = (
                ("ratio", {"ratio": 2}, [{"ratio": value} for value in (1.999, 2, 2.001)], [3]),
                ("seeding_time", {"seeding_time": 1}, [self._time_fields(client, value) for value in (3599, 3600, 3601)], [3]),
                ("size", {"size": [1, 3]}, [{size_field: value} for value in
                                          (self.GIB - 1, self.GIB, self.GIB + 1, 3 * self.GIB - 1, 3 * self.GIB, 3 * self.GIB + 1)], [3, 4]),
                ("upload_avs", {"upload_avs": 1}, upload_rows, [1]),
            )
            for name, config, fields, expected in cases:
                with self.subTest(client=client, filter=name):
                    torrents = [self._torrent(client, index, **value) for index, value in enumerate(fields, 1)]
                    result = self._search(client, torrents, config)
                    self.assertEqual([self._id(client, index) for index in expected], [row["id"] for row in result])

    def test_zero_thresholds_and_empty_size_disable_their_filters(self):
        for client in self.CLIENTS:
            for size_filter in (0, [], None):
                with self.subTest(client=client, size=size_filter):
                    size_field = "size" if client == "qb" else "total_size"
                    torrent = self._torrent(client, 1, ratio=0, **{size_field: 0}, **self._time_fields(client, 0))
                    result = self._search(client, [torrent],
                                          {"ratio": 0, "seeding_time": 0, "size": size_filter, "upload_avs": 0})
                    self.assertEqual([self._id(client, 1)], [row["id"] for row in result])

    def test_completion_date_precedes_added_date_and_missing_dates_keep_zero_duration(self):
        for client in self.CLIENTS:
            with self.subTest(client=client):
                if client == "qb":
                    fallback = {"completion_on": 0, "added_on": self.timestamp - 3601}
                    missing = {"completion_on": 0, "added_on": 0}
                else:
                    fallback = {"date_done": None, "date_added": datetime.fromtimestamp(self.timestamp - 3601)}
                    missing = {"date_done": None, "date_added": None}
                torrents = [self._torrent(client, 1, **fallback),
                            self._torrent(client, 2, **self._time_fields(client, 300)),
                            self._torrent(client, 3, **missing)]
                result = self._search(client, torrents, {"seeding_time": 1})
                self.assertEqual([self._id(client, 1)], [row["id"] for row in result])
                # 无可用时间时平均速度按 0 计算，不产生除零或改用当前上传速度。
                result = self._search(client, [torrents[2]], {"upload_avs": 1})
                self.assertEqual([self._id(client, 3)], [row["id"] for row in result])

    def test_qb_uses_uploaded_bytes_while_transmission_uses_ratio_times_size(self):
        for ratio, uploaded, expected_qb, expected_tr in ((2, 51200, True, False), (0, 204800, False, True)):
            for client, expected in (("qb", expected_qb), ("tr", expected_tr)):
                with self.subTest(client=client, ratio=ratio, uploaded=uploaded):
                    native = {"size": 102400, "uploaded": uploaded} if client == "qb" else {
                        "total_size": 102400, "uploaded_ever": uploaded}
                    torrent = self._torrent(client, 1, ratio=ratio, **native, **self._time_fields(client, 100))
                    result = self._search(client, [torrent], {"upload_avs": 1})
                    self.assertEqual([self._id(client, 1)] if expected else [], [row["id"] for row in result])

    def test_regex_is_case_insensitive_but_tracker_sources_remain_client_specific(self):
        trackers = [{"announce": "https://primary.example/announce", "sitename": "Primary"},
                    {"announce": "https://TARGET.Example/announce", "sitename": "Target"}]
        qb = [self._torrent("qb", 1, tracker="https://primary.example/announce", trackers=trackers),
              self._torrent("qb", 2, tracker="https://TARGET.Example/announce")]
        tr = [self._torrent("tr", 1, trackers=trackers), self._torrent("tr", 2, trackers=[])]
        config = {"savepath_key": r"/DATA/mov(?:ies|ie)", "tracker_key": r"target\.example"}

        self.assertEqual(["hash-2"], [row["id"] for row in self._search("qb", qb, config)])
        result = self._search("tr", tr, config)
        self.assertEqual([1], [row["id"] for row in result])
        self.assertEqual("Primary", result[0]["site"], "匹配其他 announce 后仍保留首 tracker 的站点展示值")

    def test_client_specific_state_category_and_error_filters_remain_distinct(self):
        qb = [self._torrent("qb", 1, state="pausedUP", category="Movies"),
              self._torrent("qb", 2, state="uploading", category="Movies"),
              self._torrent("qb", 3, state="pausedUP", category="movies")]
        tr = [self._torrent("tr", 1, status="stopped", error_string="Tracker TimEOut"),
              self._torrent("tr", 2, status="seeding", error_string="timeout"),
              self._torrent("tr", 3, status="stopped", error_string="No error")]
        config = {"qb_state": ["pausedUP"], "qb_category": ["Movies"],
                  "tr_state": ["stopped"], "tr_error_key": "TIMEOUT"}

        self.assertEqual(["hash-1"], [row["id"] for row in self._search("qb", qb, config)])
        self.assertEqual([1], [row["id"] for row in self._search("tr", tr, config)])

    def test_all_required_tags_must_match_and_missing_tags_are_rejected(self):
        for client in self.CLIENTS:
            with self.subTest(client=client):
                tag_field = "tags" if client == "qb" else "labels"
                values = [["alpha", "beta", "extra"], ["alpha"], ["beta"], [], None, ["Alpha", "beta"]]
                torrents = [self._torrent(client, index, **{tag_field: value}) for index, value in enumerate(values, 1)]
                missing = self._torrent(client, 7)
                if client == "qb":
                    missing.pop(tag_field)
                    torrents.append(self._torrent(client, 8, tags=" alpha , beta , "))
                else:
                    delattr(missing, tag_field)
                torrents.append(missing)

                result = self._search(client, torrents, {"filter_tags": ["alpha", "beta"]})

                expected = ["hash-1", "hash-8"] if client == "qb" else [1]
                self.assertEqual(expected, [row["id"] for row in result])
                self.assertEqual([self._id(client, 7)], [row["id"] for row in self._search(client, [missing], {"filter_tags": []})])

    def test_samedata_expands_only_equal_name_and_size_without_crossing_tag_boundary(self):
        for client in self.CLIENTS:
            with self.subTest(client=client):
                size_field, tags_field = ("size", "tags") if client == "qb" else ("total_size", "labels")
                base = self._torrent(client, 1, name="same-data", ratio=3)
                native = {"save_path": "/elsewhere", "state": "pausedUP", "category": "Other"} if client == "qb" else {
                    "download_dir": "/elsewhere", "status": "stopped"}
                extra = self._torrent(client, 2, name="same-data", ratio=0, **native)
                missing_tag = self._torrent(client, 3, name="same-data", ratio=0, **{tags_field: ["NASTOOL"]})
                other_size = self._torrent(client, 4, name="same-data", ratio=0, **{size_field: self.GIB})
                other_name = self._torrent(client, 5, name="different-data", ratio=0)
                torrents = [missing_tag, other_size, extra, other_name, base]
                config = {"ratio": 2, "savepath_key": "movies", "filter_tags": ["NASTOOL", "managed"], "samedata": 1}
                original_config = copy.deepcopy(config)
                original_torrents = copy.deepcopy(torrents)

                result = self._search(client, torrents, config)

                self.assertEqual([self._id(client, 2), self._id(client, 1)], [row["id"] for row in result])
                self.assertEqual(original_config, config)
                self.assertEqual(original_torrents, torrents)

    def test_result_shape_native_ids_order_and_existing_samedata_repeat_order_are_preserved(self):
        for client in self.CLIENTS:
            with self.subTest(client=client):
                first = self._torrent(client, 2, name="same-data", ratio=3)
                second = self._torrent(client, 1, name="same-data", ratio=3)
                extra = self._torrent(client, 3, name="same-data", ratio=0)
                torrents = [first, extra, second]
                result = self._search(client, torrents, {"ratio": 2})
                expected = [{"id": self._id(client, index), "name": "same-data", "size": 2 * self.GIB,
                             "site": f"site{index}" if client == "qb" else f"Site {index}"} for index in (2, 1)]
                self.assertEqual(expected, result)

                expanded = self._search(client, torrents, {"ratio": 2, "samedata": 1})
                # 保持当前逐命中扩展行为：同内容的两个原命中会各自追加同一个扩展项。
                self.assertEqual([self._id(client, index) for index in (3, 3, 2, 1)], [row["id"] for row in expanded])

    def test_missing_config_and_client_api_failures_return_empty_results(self):
        for client, cls in self.CLIENTS.items():
            with self.subTest(client=client):
                instance = cls.__new__(cls)
                api = Mock()
                if client == "qb":
                    instance.qbc = api
                    api.torrents_info.side_effect = RuntimeError("api unavailable")
                else:
                    instance.trc = api
                    api.get_torrents.side_effect = RuntimeError("api unavailable")
                self.assertEqual([], instance.get_remove_torrents(None))
                self.assertEqual([], instance.get_remove_torrents({}))
                self.assertEqual([], api.mock_calls)
                module = "qbittorrent" if client == "qb" else "transmission"
                with patch(f"app.downloader.client.{module}.ExceptionUtils.exception_traceback"):
                    self.assertEqual([], instance.get_remove_torrents({"ratio": 1}))
                self.assertEqual(1, len(api.mock_calls))

    def test_invalid_regex_is_evaluated_only_after_numeric_filters_pass(self):
        for client in self.CLIENTS:
            rules = ["savepath_key", "tracker_key"]
            if client == "tr":
                rules.append("tr_error_key")
            for rule in rules:
                with self.subTest(client=client, rule=rule):
                    config = {"ratio": 1, rule: "["}
                    rejected = self._torrent(client, 1, ratio=0)
                    accepted = self._torrent(client, 2, ratio=2)

                    self.assertEqual([], self._search(client, [rejected], config))
                    with self.assertRaises(re.error) as raised:
                        self._search(client, [accepted], config)
                    self.assertEqual("[", raised.exception.pattern)

    def test_absent_required_tags_preserve_client_specific_lazy_label_access(self):
        for tags_rule in ({}, {"filter_tags": []}):
            with self.subTest(tags_rule=tags_rule):
                qb = self._torrent("qb", 1, ratio=3, tags=123)
                self.assertEqual(["hash-1"], [row["id"] for row in self._search(
                    "qb", [qb], {"ratio": 2, **tags_rule})])

                base = self._torrent("tr", 1, name="same-data", ratio=3)
                extra = self._torrent("tr", 2, name="same-data", ratio=0, labels=123)
                result = self._search("tr", [base, extra], {"ratio": 2, "samedata": 1, **tags_rule})
                self.assertEqual([2, 1], [row["id"] for row in result])

                # TR 主选阶段一直会构造 labels 集合，不能随本轮共用逻辑改变其异常契约。
                invalid_main = self._torrent("tr", 3, ratio=3, labels=123)
                with self.assertRaises(TypeError):
                    self._search("tr", [invalid_main], {"ratio": 2, **tags_rule})


if __name__ == "__main__":
    unittest.main()
