import datetime
import time
from collections import deque
from threading import Lock

from app.utils.commons import singleton


@singleton
class MessageCenter:
    def __init__(self):
        self._message_queue = deque(maxlen=50)
        self._message_index = time.time_ns() // 1000
        self._lock = Lock()

    def insert_system_message(self, level, title, content=None):
        """
        新增系统消息
        :param level: 级别
        :param title: 标题
        :param content: 内容
        """
        if not level or not title:
            return
        if not content and title.find("：") != -1:
            strings = title.split("：", 1)
            if strings and len(strings) > 1:
                title = strings[0]
                content = strings[1]
        title = title.replace("\n", "<br>").strip() if title else ""
        content = content.replace("\n", "<br>").strip() if content else ""
        self.__append_message_queue(level, title, content)

    def __append_message_queue(self, level, title, content):
        """
        将消息增加到队列
        """
        with self._lock:
            self._message_index += 1
            self._message_queue.appendleft({
                "id": self._message_index, "level": level, "title": title, "content": content,
                "time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
            })

    def get_system_messages(self, num=20, lst_time=None):
        """
        查询系统消息
        :param num:条数
        :param lst_time: 最后时间
        """
        with self._lock:
            messages = list(self._message_queue)
        if isinstance(lst_time, int):
            # 突发消息超过一页时先返回最早未读的一页，下一次从这一页继续。
            return [message for message in messages if message["id"] > lst_time][-num:]
        if not lst_time:
            return messages[:num]
        try:
            last_time = datetime.datetime.strptime(lst_time, '%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            return messages[:num]

        ret_messages = []
        for message in messages:
            message_time = datetime.datetime.strptime(message.get("time"), '%Y-%m-%d %H:%M:%S')
            if message_time <= last_time:
                break
            ret_messages.append(message)
        return ret_messages[:num]
