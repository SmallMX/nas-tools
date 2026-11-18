import unittest
from collections import deque
from unittest.mock import patch

import log
from app.message.message_center import MessageCenter
from web.actions.system import SystemActions


class MessageCenterTest(unittest.TestCase):
    def setUp(self):
        self.center = MessageCenter()
        self.center._message_queue.clear()

    def tearDown(self):
        self.center._message_queue.clear()

    def test_returns_newest_messages_and_filters_by_timestamp(self):
        with patch(
            "app.message.message_center.time.strftime",
            side_effect=[
                "2026-09-01 12:00:01",
                "2026-09-01 12:00:02",
                "2026-09-01 12:00:03",
            ],
        ):
            self.center.insert_system_message("INFO", "first")
            self.center.insert_system_message("INFO", "second")
            self.center.insert_system_message("INFO", "third")

        newest = self.center.get_system_messages(num=2)
        after_second = self.center.get_system_messages(lst_time="2026-09-01 12:00:02")

        self.assertEqual(["third", "second"], [item["title"] for item in newest])
        self.assertEqual(["third"], [item["title"] for item in after_second])

    def test_title_split_preserves_additional_colons(self):
        self.center.insert_system_message("INFO", "下载失败：站点：超时")

        message = self.center.get_system_messages(num=1)[0]

        self.assertEqual("下载失败", message["title"])
        self.assertEqual("站点：超时", message["content"])

    def test_cursor_delivers_same_second_bursts_to_each_reader(self):
        with patch("app.message.message_center.time.strftime", return_value="2026-09-01 12:00:00"):
            self.center.insert_system_message("INFO", "initial")
            cursor = SystemActions.get_system_message(None)["cursor"]
            for i in range(22):
                self.center.insert_system_message("INFO", str(i))
            first = SystemActions.get_system_message(cursor)
            self.assertEqual(first, SystemActions.get_system_message(cursor))
            second = SystemActions.get_system_message(first["cursor"])
            titles = [m["title"] for page in (first, second) for m in reversed(page["message"])]
            self.assertEqual(list(map(str, range(22))), titles)
            self.assertEqual([], SystemActions.get_system_message(second["cursor"])["message"])

    def test_log_cursor_is_independent_of_other_readers_and_sources(self):
        with patch.object(log, "LOG_QUEUE", deque(maxlen=3)), patch.object(log, "LOG_INDEX", 100):
            log.info("【A】first")
            first = SystemActions.logging({"cursor": 0})
            log.info("【B】second")
            log.info("【A】third")
            for _ in range(2):
                delta = SystemActions.logging({"cursor": first["cursor"]})
                self.assertEqual(["second", "third"], [entry["text"] for entry in delta["loglist"]])
            filtered = SystemActions.logging({"cursor": first["cursor"], "source": "A"})
            self.assertEqual(["third"], [entry["text"] for entry in filtered["loglist"]])


if __name__ == "__main__":
    unittest.main()
