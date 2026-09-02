import unittest
from unittest.mock import patch

from app.message.message_center import MessageCenter


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


if __name__ == "__main__":
    unittest.main()
