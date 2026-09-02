import copy
import math
import re

import log
from app.helper import ThreadHelper
from app.tools import SiteSignin
from app.tools.site_signin.config import get_site_signin_config
from app.tools.site_signin.constants import DEFAULT_RETRY_KEYWORD
from app.utils import StringUtils
from config import Config


class SiteSigninWebService:
    """将站点自动签到工具适配到现有 `/do` 动作协议。"""

    def __init__(self):
        self._service = SiteSignin()

    def status(self, data=None):
        return {"code": 0, **self._service.get_status()}

    def run(self, data=None):
        if self._service.is_running:
            return {"code": 1, "msg": "站点签到任务正在运行"}
        payload = data or {}
        force = StringUtils.to_bool(payload.get("force"), False)
        site_ids = payload.get("site_ids")
        ThreadHelper().start_thread(self._service.signin, (force, site_ids, None))
        return {"code": 0, "msg": "站点签到任务已启动"}

    def update_config(self, data=None):
        """校验并保存站点自动签到工具配置。"""
        if not isinstance(data, dict):
            return {"code": 1, "msg": "工具配置格式不合法"}

        current = get_site_signin_config()
        try:
            normalized = {
                "cron": self._normalize_cron(data.get("cron", current.get("cron", ""))),
                "concurrency": self._normalize_int(
                    data.get("concurrency", current.get("concurrency", 5)), 1, 10, "签到并发数"
                ),
                "retry_keyword": self._normalize_retry_keyword(
                    data.get("retry_keyword", current.get("retry_keyword"))
                ),
                "notify": StringUtils.to_bool(
                    data.get("notify", current.get("notify", True)), True
                ),
                "history_days": self._normalize_int(
                    data.get("history_days", current.get("history_days", 30)), 7, 365, "历史保留天数"
                ),
            }
        except ValueError as error:
            return {"code": 1, "msg": str(error)}

        config = copy.deepcopy(Config().get_config())
        if not isinstance(config.get("tools"), dict):
            config["tools"] = {}
        config["tools"]["site_signin"] = normalized
        try:
            if not Config().save_config(config):
                raise RuntimeError("配置写入未完成")
            self._service.init_config()
        except Exception as error:
            log.error(f"【SiteSignin】保存工具配置失败：{type(error).__name__}")
            return {"code": 1, "msg": "工具配置保存失败，请检查系统日志"}
        return {"code": 0, "msg": "工具设置已保存"}

    @staticmethod
    def _normalize_cron(value):
        cron = str(value or "").strip()
        if not cron:
            return ""
        if len(cron) > 32:
            raise ValueError("执行周期格式不合法")

        def parse_time(raw_time):
            parts = raw_time.split(":")
            if len(parts) != 2:
                raise ValueError("执行周期格式不合法")
            try:
                hour, minute = (int(part) for part in parts)
            except ValueError as error:
                raise ValueError("执行周期格式不合法") from error
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                raise ValueError("执行周期时间无效")
            return hour * 60 + minute

        if "-" in cron:
            ranges = cron.split("-")
            if len(ranges) != 2 or parse_time(ranges[0]) > parse_time(ranges[1]):
                raise ValueError("执行周期时间范围无效")
        elif ":" in cron:
            parse_time(cron)
        else:
            try:
                hours = float(cron)
            except ValueError as error:
                raise ValueError("执行周期格式不合法") from error
            if not math.isfinite(hours) or hours <= 0:
                raise ValueError("执行周期间隔必须大于 0 小时")
        return cron

    @staticmethod
    def _normalize_int(value, minimum, maximum, label):
        try:
            normalized = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label}必须是整数") from error
        if not minimum <= normalized <= maximum:
            raise ValueError(f"{label}范围为 {minimum}-{maximum}")
        return normalized

    @staticmethod
    def _normalize_retry_keyword(value):
        keyword = str(value or DEFAULT_RETRY_KEYWORD).strip()
        if len(keyword) > 512:
            raise ValueError("失败重试关键词不能超过 512 个字符")
        try:
            re.compile(keyword, re.IGNORECASE)
        except re.error as error:
            raise ValueError("失败重试关键词不是有效的正则表达式") from error
        return keyword
