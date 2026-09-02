import atexit
import os
import sys
import time
from threading import Lock

# 从 watchdog 库导入文件系统事件处理器和观察者，用于监控配置文件是否被修改
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# 导入项目内的各个核心模块
from config import Config
from check_config import initialize_config, check_config, is_public_bind_address

# Web 层创建 Flask App 前必须先持久化 Session/Webhook 等首次启动密钥。
initialize_config()

import log
from web.main import App
from app.utils import ConfigLoadCache
from app.utils.commons import INSTANCES
from app.db import init_db, remove_db_session
from app.helper import IndexerHelper, DisplayHelper, ChromeHelper, ThreadHelper
from app.brushtask import BrushTask
from app.message import Message
from app.scheduler import run_scheduler, restart_scheduler, stop_scheduler
from app.torrentremover import TorrentRemover
from version import APP_VERSION


_config_observer = None
_shutdown_lock = Lock()
_shutdown_started = False


def validate_run_security():
    """拒绝默认凭据通过非回环宿主地址对外发布。"""
    app_conf = Config().get_config('app')
    from werkzeug.security import check_password_hash
    is_default_password = False
    _login_password = app_conf.get('login_password', '') if app_conf else ''
    if not _login_password:
        is_default_password = True
    elif _login_password.startswith('[hash]'):
        if check_password_hash(_login_password[6:], 'password'):
            is_default_password = True
    elif _login_password == 'password':
        is_default_password = True

    _api_key = Config().get_config('security').get('api_key', '')
    is_default_api_key = (_api_key == 'asrWyexWYYEkxni1')

    publish_address = os.environ.get("NASTOOL_BIND_ADDRESS", "0.0.0.0").strip("[]")
    is_public_listen = is_public_bind_address(publish_address)

    if (is_default_password or is_default_api_key) and is_public_listen:
        log.error("【安全防范】检测到默认管理员密码或 API Key，且 Web 服务发布到非回环地址。请修改凭据，或将 NASTOOL_BIND_ADDRESS 设置为 127.0.0.1。")
        sys.exit("【安全防范】检测到默认凭据且监听在公网接口，拒绝启动。")


def init_system():
    """
    系统初始化阶段。在启动具体业务服务前，先做好基础环境准备。
    """
    # 打印版本号
    log.console('NAStool 当前版本号：%s' % APP_VERSION)

    # Gunicorn 不调用 Flask App.run()，这里显式保留启动前安全校验。
    validate_run_security()

    # 初始化本地 SQLite 数据库表结构
    init_db()
    # 检查用户的配置是否合法（比如缺少必须配置项时会提醒）
    check_config()


def start_service():
    """
    启动核心业务后台服务。
    NAS-Tools 是一个包含 Web 服务器和多个常驻后台任务的系统，这里集中启动后台任务。
    """
    log.console("开始启动服务...")
    
    # 加载 BT 站点的索引器配置（用于搜索种子）
    IndexerHelper()
    # 启动虚拟显示屏环境（某些签到爬虫需要用到无头浏览器）
    DisplayHelper()
    
    # 启动定时任务调度器 (APScheduler)，执行日常签到、缓存保存等操作
    run_scheduler()
    # 启动刷流服务模块（按策略自动下载免费资源赚取上传量）
    BrushTask()
    
    # 启动自动删种服务（当做种时间或分享率达标后自动从 qBittorrent 清理任务）
    TorrentRemover()

    # 初始化浏览器驱动 (ChromeDriver)，供爬虫模块抓取使用
    ChromeHelper().init_driver()


def monitor_config():
    """
    监听配置文件 (config.yaml) 的变化。
    如果用户修改了配置，系统可以在不重启的情况下自动热加载部分配置并应用。
    """
    global _config_observer

    class _ConfigHandler(FileSystemEventHandler):
        """
        内部类：继承自 watchdog 的事件处理器，专门用来处理文件被修改的事件
        """
        def __init__(self):
            FileSystemEventHandler.__init__(self)

        @staticmethod
        def _reload_config(path):
            if os.path.basename(path) != "config.yaml":
                return
            if ConfigLoadCache.get(path):
                return
            ConfigLoadCache.set(path, True)

            log.console("进程 %s 检测到配置文件已修改，正在重新加载..." % os.getpid())
            time.sleep(1)
            if not Config().init_config():
                return

            for instance in INSTANCES.values():
                if hasattr(instance, "init_config"):
                    instance.init_config()
            restart_scheduler()

        def on_modified(self, event):
            if not event.is_directory:
                self._reload_config(event.src_path)

        def on_created(self, event):
            if not event.is_directory:
                self._reload_config(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._reload_config(event.dest_path)

    # 创建一个文件观察者对象
    _config_observer = Observer(timeout=10)
    # 给观察者安排任务，监听 config.yaml 所在的文件夹，且不递归监控子文件夹
    _config_observer.schedule(_ConfigHandler(), path=Config().get_config_path(), recursive=False)
    # 设置为守护线程（主线程退出时自动关闭）
    _config_observer.daemon = True
    # 启动观察者后台线程
    _config_observer.start()


def shutdown_system():
    """由 Python atexit 在 Gunicorn worker 正常退出时释放后台资源。"""
    global _shutdown_started
    with _shutdown_lock:
        if _shutdown_started:
            return
        _shutdown_started = True

    log.warn('Web worker 正在退出，开始停止后台服务...')
    if _config_observer:
        _config_observer.stop()
        _config_observer.join(timeout=10)
    stop_scheduler()
    BrushTask().stop_service()
    TorrentRemover().stop_service()
    Message().stop_service()
    ThreadHelper().shutdown()
    ChromeHelper().quit()
    DisplayHelper().quit()
    remove_db_session()


# 程序执行主流程：

# 第一步：系统环境与数据库初始化
init_system()

# 第二步：拉起所有的后台独立服务和定时任务
start_service()

# 第三步：开启后台线程监控配置文件变动
monitor_config()

atexit.register(shutdown_system)

# Web 请求由 Docker 入口中的单 worker Gunicorn 承载。
