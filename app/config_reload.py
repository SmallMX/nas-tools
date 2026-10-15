"""配置持久化与运行时应用的边界；导入本模块不会启动服务。"""

import copy
import os
from threading import RLock

from watchdog.events import FileSystemEventHandler

import log
from config import Config


def changed_config_paths(previous, current, prefix=""):
    """记录失败尝试涉及的字段，后续恢复旧配置也必须重新应用这些字段。"""
    paths = set()
    for key in previous.keys() | current.keys():
        path = f"{prefix}.{key}" if prefix else str(key)
        before, after = previous.get(key), current.get(key)
        if isinstance(before, dict) and isinstance(after, dict):
            paths.update(changed_config_paths(before, after, path))
        elif key not in previous or key not in current or before != after:
            paths.add(path)
    return paths


class ConfigReloader:
    def __init__(self, config, apply_changes):
        self.config = config
        self._apply_changes = apply_changes
        self._applied_config = copy.deepcopy(config.get_config())
        self._pending_paths = set()
        self._lock = RLock()

    def reload(self):
        """读取外部修改；坏文件保留原配置，等待后续修改事件重试。"""
        with self._lock:
            if not self.config.init_config():
                return False
            return self.apply_current()

    def save(self, new_config):
        """保持原子保存契约，成功落盘后应用相关配置。"""
        with self._lock:
            if not self.config.save_config(new_config):
                return False
            return self.apply_current()

    def apply_current(self):
        with self._lock:
            current = copy.deepcopy(self.config.get_config())
            if current == self._applied_config and not self._pending_paths:
                return True
            retry_paths = frozenset(self._pending_paths)
            self._pending_paths.update(changed_config_paths(self._applied_config, current))
            try:
                kwargs = {"retry_paths": retry_paths} if retry_paths else {}
                applied = self._apply_changes(copy.deepcopy(self._applied_config), current, **kwargs)
            except Exception as error:
                # 不记录可能包含凭据的配置值或异常详情。
                log.error(f"【Config】应用配置失败，可在下次更新时重试：{type(error).__name__}")
                return False
            if applied is False:
                return False
            self._applied_config = copy.deepcopy(current)
            self._pending_paths.clear()
            return True


class ConfigFileEventHandler(FileSystemEventHandler):
    def __init__(self, config_path, reload_callback):
        super().__init__()
        self._config_path = os.path.abspath(config_path)
        self._reload_callback = reload_callback

    def _reload(self, event, path):
        if event.is_directory or os.path.abspath(path) != self._config_path:
            return
        try:
            self._reload_callback()
        except Exception as error:
            log.error(f"【Config】重新加载配置失败：{type(error).__name__}")

    def on_modified(self, event):
        self._reload(event, event.src_path)

    def on_created(self, event):
        self._reload(event, event.src_path)

    def on_moved(self, event):
        self._reload(event, event.dest_path)


_runtime_reloader = None


def initialize_config_reload():
    """在后台服务启动后记录已生效基线，保存和文件事件共用同一协调器。"""
    global _runtime_reloader
    _runtime_reloader = ConfigReloader(Config(), apply_config_changes)
    return _runtime_reloader


def save_config_and_apply(new_config):
    if _runtime_reloader is None:
        # 初始化/迁移阶段只持久化配置，不提前创建业务服务。
        return Config().save_config(new_config)
    return _runtime_reloader.save(new_config)


def apply_config_changes(previous, current, retry_paths=()):
    """只刷新缓存了变更字段的现有服务；请求时读取的配置无需额外动作。"""
    from app.downloader import Downloader
    from app.helper import MetaHelper
    from app.indexer import Indexer
    from app.media import Media, DouBan
    from app.media.category import Category
    from app.media.fanart import Fanart
    from app.message import Message
    from app.scheduler import Scheduler
    from app.sites.site_cookie import SiteCookie
    from app.tools import SiteSignin
    from app.utils.commons import get_singleton_instance
    from app.utils.types import DownloaderType

    def value(config, path):
        for key in path.split("."):
            if not isinstance(config, dict):
                return None
            config = config.get(key)
        return config

    def changed(*paths):
        return any(
            value(previous, path) != value(current, path)
            or any(path == pending or path.startswith(pending + ".") or pending.startswith(path + ".")
                   for pending in retry_paths)
            for path in paths
        )

    success = True

    def apply(name, callback):
        nonlocal success
        try:
            if callback() is False:
                success = False
                log.error(f"【Config】{name}配置未能应用，将在下次更新时重试")
        except Exception as error:
            success = False
            log.error(f"【Config】{name}配置应用失败：{type(error).__name__}")

    def refresh(factory, method="reload_runtime_config", *args):
        instance = get_singleton_instance(factory)
        if instance is not None:
            apply(factory.__name__, lambda: getattr(instance, method)(*args))

    if changed("pt.pt_client", "pt.pt_monitor_only", "pt.download_order", "downloaddir"):
        refresh(Downloader)
    if changed("qbittorrent"):
        refresh(Downloader, "reset_client", DownloaderType.QB)
    if changed("transmission"):
        refresh(Downloader, "reset_client", DownloaderType.TR)

    if changed("app.rmt_tmdbkey", "app.tmdb_domain", "app.rmt_match_mode", "app.proxies",
               "laboratory.tmdb_proxy", "laboratory.search_keyword", "laboratory.search_tmdbweb"):
        downloader = get_singleton_instance(Downloader)
        if downloader is not None:
            apply("下载媒体识别", lambda: setattr(downloader, "media", Media()))
        indexer = get_singleton_instance(Indexer)
        if indexer is not None:
            client = indexer.get_client()
            if client is not None:
                apply("搜索媒体识别", lambda: setattr(client, "media", Media()))
            else:
                apply("搜索媒体识别", indexer.init_config)

    if changed("media.category"):
        refresh(Category, "init_config")
    if changed("laboratory.tmdb_cache_expire"):
        refresh(MetaHelper)
    if changed("douban.cookie"):
        refresh(DouBan, "init_config")
    if changed("app.proxies"):
        apply("Fanart", Fanart.reload_runtime_config)
    if changed("app.user_agent"):
        refresh(SiteCookie)
    if changed("app.domain", "security.telegram_webhook_secret"):
        refresh(Message)
    if changed("tools.site_signin"):
        refresh(SiteSignin, "init_config")
    if changed("tools.site_signin.cron"):
        refresh(Scheduler)

    if changed("app.wallpaper", "app.rmt_tmdbkey", "app.tmdb_domain", "app.proxies",
               "laboratory.tmdb_proxy"):
        from web.backend.wallpaper import _get_login_wallpaper_for_date
        apply("登录壁纸", _get_login_wallpaper_for_date.cache_clear)
    if changed("security.flask_secret_key", "security.session_cookie_secure"):
        from web.main import configure_security
        apply("Web安全", configure_security)
    if changed("app.logtype", "app.logpath", "app.logserver", "app.loglevel"):
        apply("日志", log.Logger.reload_config)
    return success
