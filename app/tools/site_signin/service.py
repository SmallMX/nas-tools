import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from multiprocessing.dummy import Pool as ThreadPool
from threading import Lock
from urllib.parse import urljoin, urlparse

from lxml import etree
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as es
from selenium.webdriver.support.wait import WebDriverWait

import log
from app.helper import ChromeHelper, DbHelper, SiteHelper
from app.message import Message
from app.sites.sites import Sites
from app.tools.site_signin.config import get_site_signin_config
from app.tools.site_signin.constants import DEFAULT_RETRY_KEYWORD, SITE_CHECKIN_XPATH
from app.tools.site_signin.handlers import SITE_SIGNIN_HANDLERS
from app.utils import ExceptionUtils, RequestUtils, StringUtils
from app.utils.commons import singleton
from config import Config


@dataclass(frozen=True)
class SiteSigninResult:
    site_id: int
    site: str
    action: str
    success: bool
    message: str
    duration: int = 0
    created_at: str = ""

    def as_dict(self):
        result = asdict(self)
        result["action_name"] = "签到" if self.action == "signin" else "保号登录"
        return result


@singleton
class SiteSignin:
    """内置站点自动签到工具。

    在原有签到能力上增加按日去重、失败重试、保号登录、历史记录和运行状态。
    """

    _run_lock = Lock()
    _chrome_lock = Lock()

    def __init__(self):
        self._site_schema = list(SITE_SIGNIN_HANDLERS)
        self._running = False
        self.init_config()
        log.debug(f"【SiteSignin】加载站点签到处理器：{self._site_schema}")

    def init_config(self):
        self.sites = Sites()
        self.dbhelper = DbHelper()
        self.message = Message()
        signin_config = get_site_signin_config()
        self._concurrency = self._bounded_int(signin_config.get("concurrency"), 5, 1, 10)
        self._retry_keyword = str(
            signin_config.get("retry_keyword") or DEFAULT_RETRY_KEYWORD
        ).strip()
        self._notify = StringUtils.to_bool(signin_config.get("notify", True), True)
        self._history_days = self._bounded_int(signin_config.get("history_days"), 30, 7, 365)

    @property
    def is_running(self):
        return self._running

    def signin(self, force=False, site_ids=None, notify=None):
        """执行已配置站点的签到和保号登录。

        非强制运行时，同一天已经成功的站点会跳过，失败记录仅在命中重试关键词时重试。
        """
        if not self._run_lock.acquire(blocking=False):
            return {"code": 1, "msg": "站点签到任务正在运行", "results": []}

        self._running = True
        try:
            self.init_config()
            tasks = self._build_tasks(site_ids)
            latest = self.dbhelper.get_latest_site_signin_history(datetime.now().strftime("%Y-%m-%d"))
            retry_pattern = self._compile_retry_pattern()
            pending_tasks = [
                task for task in tasks
                if force or self._should_run(task, latest, retry_pattern)
            ]

            if not pending_tasks:
                log.info("【SiteSignin】今日站点签到已完成，没有需要重试的站点")
                return {
                    "code": 0,
                    "msg": "今日签到已完成，没有需要重试的站点",
                    "results": [],
                    "skipped": len(tasks),
                }

            log.info(
                f"【SiteSignin】开始执行站点自动签到：任务数={len(pending_tasks)}，"
                f"并发数={min(len(pending_tasks), self._concurrency)}"
            )
            with ThreadPool(min(len(pending_tasks), self._concurrency)) as pool:
                results = pool.map(self._execute_task, pending_tasks)

            self.dbhelper.cleanup_site_signin_history(self._history_days)
            should_notify = self._notify if notify is None else bool(notify)
            if should_notify and results:
                self.message.send_site_signin_message([
                    f"【{result.site}】{result.message}" for result in results
                ])

            success_count = sum(1 for result in results if result.success)
            return {
                "code": 0,
                "msg": f"站点签到完成：成功 {success_count}，失败 {len(results) - success_count}",
                "results": [result.as_dict() for result in results],
                "skipped": len(tasks) - len(pending_tasks),
            }
        finally:
            self._running = False
            self._run_lock.release()

    def get_status(self, history_limit=100):
        """返回今日站点状态和最近执行历史，供 Web 页面展示。"""
        self.init_config()
        tasks = self._build_tasks()
        today = datetime.now().strftime("%Y-%m-%d")
        latest = self.dbhelper.get_latest_site_signin_history(today)
        items = []
        for action, site_info in tasks:
            record = latest.get((int(site_info.get("id")), action))
            items.append({
                "site_id": int(site_info.get("id")),
                "site": site_info.get("name"),
                "action": action,
                "action_name": "签到" if action == "signin" else "保号登录",
                "success": bool(record.success) if record else None,
                "message": record.message if record else "今日尚未执行",
                "created_at": record.created_at if record else "",
                "duration": int(record.duration or 0) if record else 0,
            })

        history = [self._history_to_dict(item) for item in self.dbhelper.get_site_signin_history(
            limit=history_limit
        )]
        success_count = sum(1 for item in items if item["success"] is True)
        failed_count = sum(1 for item in items if item["success"] is False)
        return {
            "running": self._running,
            "items": items,
            "history": history,
            "summary": {
                "total": len(items),
                "success": success_count,
                "failed": failed_count,
                "pending": len(items) - success_count - failed_count,
            },
        }

    def _build_tasks(self, site_ids=None):
        selected_ids = self._normalize_site_ids(site_ids)
        tasks = []
        for action, sites in (
            ("signin", self.sites.get_sites(signin=True)),
            ("login", self.sites.get_sites(login=True)),
        ):
            for site_info in sites:
                site_id = int(site_info.get("id"))
                if selected_ids and site_id not in selected_ids:
                    continue
                tasks.append((action, site_info))
        return tasks

    @staticmethod
    def _normalize_site_ids(site_ids):
        if site_ids in (None, "", []):
            return set()
        if not isinstance(site_ids, (list, tuple, set)):
            site_ids = [site_ids]
        normalized = set()
        for site_id in site_ids:
            try:
                normalized.add(int(site_id))
            except (TypeError, ValueError):
                continue
        return normalized

    def _compile_retry_pattern(self):
        if not self._retry_keyword:
            return None
        try:
            return re.compile(self._retry_keyword, re.IGNORECASE)
        except re.error as error:
            log.error(f"【SiteSignin】重试关键词格式错误：{type(error).__name__}")
            return re.compile(DEFAULT_RETRY_KEYWORD, re.IGNORECASE)

    @staticmethod
    def _should_run(task, latest, retry_pattern):
        action, site_info = task
        record = latest.get((int(site_info.get("id")), action))
        if not record:
            return True
        if bool(record.success):
            return False
        return True if retry_pattern is None else bool(retry_pattern.search(record.message or ""))

    def _execute_task(self, task):
        action, site_info = task
        started_at = time.monotonic()
        try:
            if action == "signin":
                success, message = self._signin_site(site_info)
            else:
                success, message = self._login_site(site_info)
        except Exception as error:
            ExceptionUtils.exception_traceback(error)
            success = False
            message = f"{self._action_name(action)}出错，请检查系统日志"

        duration = int((time.monotonic() - started_at) * 1000)
        result = SiteSigninResult(
            site_id=int(site_info.get("id")),
            site=str(site_info.get("name") or "未知站点"),
            action=action,
            success=bool(success),
            message=str(message or f"{self._action_name(action)}失败"),
            duration=duration,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.dbhelper.insert_site_signin_history(
            site_id=result.site_id,
            site=result.site,
            action=result.action,
            success=result.success,
            message=result.message,
            duration=result.duration,
        )
        log_method = log.info if result.success else log.warn
        log_method(f"【SiteSignin】{result.site} {result.message}")
        return result

    def _signin_site(self, site_info):
        site_module = self._build_class(site_info.get("signurl"))
        if site_module:
            handler = site_module() if isinstance(site_module, type) else site_module
            return self._normalize_result(handler.signin(site_info), "签到")
        return self._signin_base(site_info)

    def _login_site(self, site_info):
        site_module = self._build_class(site_info.get("signurl"))
        if site_module and hasattr(site_module, "login"):
            handler = site_module() if isinstance(site_module, type) else site_module
            return self._normalize_result(handler.login(site_info), "保号登录")
        return self._login_base(site_info)

    def _build_class(self, url):
        for site_schema in self._site_schema:
            try:
                if site_schema.match(url):
                    return site_schema
            except Exception as error:
                log.error(f"【SiteSignin】签到处理器匹配失败：{type(error).__name__}")
        return None

    def _signin_base(self, site_info):
        site = site_info.get("name")
        site_url = site_info.get("signurl")
        site_cookie = site_info.get("cookie")
        if not site_url or not site_cookie:
            return False, "未配置站点地址或 Cookie"

        if site_info.get("chrome") and ChromeHelper().get_status():
            return self._chrome_signin(site_info)

        request = RequestUtils(
            cookies=site_cookie,
            headers=site_info.get("ua"),
            proxies=Config().get_proxies() if site_info.get("proxy") else None,
            timeout=20,
        )
        last_message = "签到失败，无法打开网站"
        urls = self._signin_urls(site_url)
        for index, checkin_url in enumerate(urls):
            response = request.get_res(url=checkin_url)
            if response is None:
                continue
            if response.status_code == 404 and index < len(urls) - 1:
                continue
            html_text = response.text or ""
            if self._is_cloudflare(html_text):
                return False, "签到失败，站点受 Cloudflare 防护，请开启浏览器仿真"
            if re.search(r"已签|签到成功|签到已得", html_text, re.IGNORECASE):
                return True, "今日已签到"
            if response.status_code not in (200, 403, 500):
                last_message = f"签到失败，状态码：{response.status_code}"
                continue
            if not SiteHelper.is_logged_in(html_text):
                last_message = "签到失败，Cookie 已失效"
                continue
            if checkin_url != site_url or "attendance" in checkin_url:
                return True, "签到成功"
            return True, "模拟登录成功"
        log.warn(f"【SiteSignin】{site} {last_message}")
        return False, last_message

    def _login_base(self, site_info):
        site_url = site_info.get("signurl")
        site_cookie = site_info.get("cookie")
        if not site_url or not site_cookie:
            return False, "未配置站点地址或 Cookie"
        home_url = StringUtils.get_base_url(site_url)

        if site_info.get("chrome") and ChromeHelper().get_status():
            with self._chrome_lock:
                chrome = ChromeHelper()
                if not chrome.visit(url=home_url, ua=site_info.get("ua"), cookie=site_cookie):
                    return False, "保号登录失败，无法打开网站"
                if not chrome.pass_cloudflare():
                    return False, "保号登录失败，无法通过 Cloudflare"
                html_text = chrome.get_html()
                if SiteHelper.is_logged_in(html_text):
                    return True, "保号登录成功"
                return False, "保号登录失败，Cookie 已失效"

        response = RequestUtils(
            cookies=site_cookie,
            headers=site_info.get("ua"),
            proxies=Config().get_proxies() if site_info.get("proxy") else None,
            timeout=20,
        ).get_res(url=home_url)
        if response is None:
            return False, "保号登录失败，无法打开网站"
        if self._is_cloudflare(response.text or ""):
            return False, "保号登录失败，站点受 Cloudflare 防护，请开启浏览器仿真"
        if response.status_code not in (200, 403, 500):
            return False, f"保号登录失败，状态码：{response.status_code}"
        if SiteHelper.is_logged_in(response.text or ""):
            return True, "保号登录成功"
        return False, "保号登录失败，Cookie 已失效"

    def _chrome_signin(self, site_info):
        site = site_info.get("name")
        site_url = site_info.get("signurl")
        with self._chrome_lock:
            chrome = ChromeHelper()
            home_url = StringUtils.get_base_url(site_url)
            if not chrome.visit(url=home_url, ua=site_info.get("ua"), cookie=site_info.get("cookie")):
                return False, "仿真签到失败，无法打开网站"
            if not chrome.pass_cloudflare():
                return False, "仿真签到失败，无法通过 Cloudflare"
            html_text = chrome.get_html()
            if not html_text:
                return False, "仿真签到失败，无法获取页面"

            html = etree.HTML(html_text)
            xpath_str = next((xpath for xpath in SITE_CHECKIN_XPATH if html.xpath(xpath)), None)
            if re.search(r"已签|签到已得", html_text, re.IGNORECASE) and not xpath_str:
                return True, "今日已签到"
            if not xpath_str:
                if SiteHelper.is_logged_in(html_text):
                    return True, "模拟登录成功"
                return False, "仿真签到失败，Cookie 已失效"
            try:
                checkin_obj = WebDriverWait(driver=chrome.browser, timeout=6).until(
                    es.element_to_be_clickable((By.XPATH, xpath_str))
                )
                checkin_obj.click()
                return True, "仿真签到成功"
            except Exception as error:
                log.warn(f"【SiteSignin】{site} 仿真签到失败：{type(error).__name__}")
                return False, "仿真签到失败，请检查系统日志"

    @staticmethod
    def _signin_urls(site_url):
        parsed = urlparse(site_url)
        if parsed.path in ("", "/"):
            attendance_url = urljoin(site_url.rstrip("/") + "/", "attendance.php")
            return [attendance_url, site_url]
        return [site_url]

    @staticmethod
    def _is_cloudflare(html_text):
        text = str(html_text or "").lower()
        return any(marker in text for marker in ("just a moment", "cf-chl-", "challenge-platform"))

    @staticmethod
    def _normalize_result(result, action_name):
        if isinstance(result, tuple) and len(result) >= 2:
            return bool(result[0]), str(result[1])
        message = str(result or f"{action_name}失败")
        success = not re.search(r"失败|错误|失效|无法|超时", message, re.IGNORECASE)
        return success, message

    @staticmethod
    def _history_to_dict(item):
        return {
            "id": item.id,
            "site_id": item.site_id,
            "site": item.site,
            "action": item.action,
            "action_name": "签到" if item.action == "signin" else "保号登录",
            "success": bool(item.success),
            "message": item.message,
            "duration": int(item.duration or 0),
            "date": item.date,
            "created_at": item.created_at,
        }

    @staticmethod
    def _action_name(action):
        return "签到" if action == "signin" else "保号登录"

    @staticmethod
    def _bounded_int(value, default, minimum, maximum):
        try:
            return max(minimum, min(int(value), maximum))
        except (TypeError, ValueError):
            return default
