"""Flask 应用装配、全局安全边界与跨页面入口。"""

import base64
import datetime
import hmac
from functools import wraps

from flask import Flask, request, json, render_template, session, send_from_directory, redirect, url_for
from flask_compress import Compress
from flask_login import LoginManager, login_user, current_user
from sqlalchemy import text

import log
from app.conf import ModuleConf, SystemConfig
from app.db import MainDb, remove_db_session
from app.helper import SecurityHelper
from app.indexer import Indexer
from app.message import Message
from app.sites import Sites
from app.utils import SystemUtils, StringUtils
from app.utils.types import SearchType
from config import Config
from web.action import WebAction
from web.apiv1 import apiv1_bp
from web.permissions import PATH_PERMISSIONS
from web.routes import (
    system_files_bp, tool_pages_bp,
    search_pages_bp, download_pages_bp, site_pages_bp, settings_pages_bp,
)
from web.backend.user import User
from web.backend.wallpaper import get_login_wallpaper
from web.backend.web_utils import WebUtils
from web.security import current_user_can  # 保留原有辅助函数导入入口。


App = Flask(__name__)
App.json.ensure_ascii = False
App.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024


def configure_security():
    """应用 Web 安全配置，不重建 Flask 应用或其他服务。"""
    security = Config().get_config("security") or {}
    secret_key = security.get("flask_secret_key")
    if not secret_key:
        raise RuntimeError("security.flask_secret_key 未配置，拒绝使用易失 Session 密钥启动")
    cookie_secure = str(security.get("session_cookie_secure", False)).strip().lower() in {
        "1", "true", "yes", "on"
    }
    App.config.update(
        SECRET_KEY=str(secret_key),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=cookie_secure,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=cookie_secure,
    )


configure_security()
App.permanent_session_lifetime = datetime.timedelta(days=30)
Compress(App)

# 全部页面蓝图共用同一登录管理器和匿名响应策略。
LoginManager = LoginManager()
LoginManager.login_view = "login" # 如果没登录，就把他踢回名为 login 的路由处理函数
LoginManager.init_app(App)


@LoginManager.unauthorized_handler
def handle_unauthorized_request():
    expects_json = request.path in {"/do", "/upload", "/backup", "/dirlist"} \
        or request.path.startswith("/api/") \
        or request.headers.get("X-Requested-With") == "XMLHttpRequest" \
        or request.accept_mimetypes.best == "application/json"
    if expects_json:
        return {
            "code": 401,
            "success": False,
            "msg": "用户未登录",
            "message": "用户未登录",
        }, 401
    next_page = request.full_path.rstrip("?").lstrip("/")
    return redirect(url_for("login", next=next_page))


App.register_blueprint(apiv1_bp, url_prefix="/api/v1")
App.register_blueprint(system_files_bp)
App.register_blueprint(tool_pages_bp)
App.register_blueprint(search_pages_bp)
App.register_blueprint(download_pages_bp)
App.register_blueprint(site_pages_bp)
App.register_blueprint(settings_pages_bp)


@App.teardown_appcontext
def cleanup_database_session(_error=None):
    remove_db_session()


@App.after_request
def add_header(r):
    """
    统一添加Http头，标用缓存，避免Flask多线程+Chrome内核会发生的静态资源加载出错的问题
    r.headers["Cache-Control"] = "no-cache, no-store, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    """
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    r.headers.setdefault("Referrer-Policy", "same-origin")
    r.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    r.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
    if not request.path.startswith("/static/"):
        r.headers["Cache-Control"] = "no-store"
    if request.is_secure:
        r.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return r


@App.before_request
def global_ui_rbac_check():
    """
    全局 Session-based UI 页面与动作 RBAC 拦截器
    """
    path = request.path
    if path.startswith("/static/") or path.startswith("/api/v1/"):
        return
    if path in ["/", "/login", "/telegram", "/robots.txt", "/healthz"]:
        return

    from flask_login import current_user
    if not current_user.is_authenticated:
        return

    from web.security import is_authorized
    username = current_user.username

    if path == "/do":
        cmd = request.form.get("cmd")
        if cmd and not is_authorized(username, path, cmd=cmd):
            return {"code": -1, "msg": "权限不足，拒绝执行动作"}
    else:
        if not is_authorized(username, path):
            return render_template("403.html"), 403


@LoginManager.user_loader
def load_user(user_id):
    return User().get(user_id)


@App.route('/healthz', methods=['GET'])
def healthz():
    """不触发外部服务的进程与数据库存活检查。"""
    try:
        if MainDb().session.execute(text("SELECT 1")).scalar() != 1:
            raise RuntimeError("数据库存活检查返回异常")
    except Exception as error:
        log.error(f"【Health】数据库存活检查失败：{error}")
        return {"status": "unhealthy"}, 503
    return {"status": "ok"}, 200


@App.errorhandler(404)
def page_not_found(error):
    return render_template("404.html", error=error), 404


@App.errorhandler(500)
def page_server_error(error):
    if request.path == "/do" or request.path.startswith("/api/") \
            or request.accept_mimetypes.best == "application/json":
        return {
            "code": 500,
            "success": False,
            "msg": "服务器内部错误",
            "message": "服务器内部错误",
        }, 500
    return render_template("500.html", error=error), 500


@App.errorhandler(413)
def request_entity_too_large(_error):
    if request.path == "/upload" or request.path.startswith("/api/"):
        return {
            "code": 413,
            "success": False,
            "msg": "请求内容超过 20MB 限制",
            "message": "请求内容超过 20MB 限制",
        }, 413
    return "请求内容超过 20MB 限制", 413


def action_login_check(func):
    """
    Action安全认证：这是一个装饰器（Decorator）。
    你可以把它当作安保大爷，用来套在特定的接口函数外面。
    只要前端请求这个接口，就会先被大爷拦截：
    1. 查你的证件（看看 session 里有没有登录信息）。
    2. 如果没登录，直接打回 `{"code": -1, "msg": "用户未登录"}`。
    3. 如果登录了，才放行让你进入真正的函数逻辑。
    """

    @wraps(func)
    def login_check(*args, **kwargs):
        if not current_user.is_authenticated:
            return {
                "code": 401,
                "success": False,
                "msg": "用户未登录",
                "message": "用户未登录",
            }, 401
        return func(*args, **kwargs)

    return login_check


@App.route('/', methods=['GET', 'POST'])
def login():
    def redirect_to_navigation(userinfo):
        """
        内部辅助函数：用来渲染（拼装）导航页的 HTML 模板。
        如果用户登录成功，会调用这个函数，并把系统状态和页面配置传给 navigation.html。
        """
        # 判断当前的运营环境
        SystemFlag = SystemUtils.get_system()
        TMDBFlag = 1 if Config().get_config('app').get('rmt_tmdbkey') else 0
        RestypeDict = ModuleConf.TORRENT_SEARCH_PARAMS.get("restype")
        PixDict = ModuleConf.TORRENT_SEARCH_PARAMS.get("pix")
        SiteFavicons = Sites().get_site_favicon()
        Indexers = Indexer().get_indexers()
        SearchSource = "tmdb"
        CustomScriptCfg = SystemConfig().get_system_config("CustomScript")
        return render_template('navigation.html',
                               GoPage=GoPage,
                               UserName=userinfo.username,
                               UserPris=str(userinfo.pris).split(","),
                               PagePermissions=PATH_PERMISSIONS,
                               SystemFlag=SystemFlag.value,
                               TMDBFlag=TMDBFlag,
                               AppVersion=WebUtils.get_current_version(),
                               RestypeDict=RestypeDict,
                               PixDict=PixDict,
                               SiteFavicons=SiteFavicons,
                               Indexers=Indexers,
                               SearchSource=SearchSource,
                               CustomScriptCfg=CustomScriptCfg)

    def redirect_to_login(errmsg=''):
        """
        跳转到登录页面
        """
        return render_template('login.html',
                               GoPage=GoPage,
                               LoginWallpaper=get_login_wallpaper(),
                               err_msg=errmsg)

    # 登录认证
    if request.method == 'GET':
        GoPage = request.args.get("next") or ""
        if GoPage.startswith('/'):
            GoPage = GoPage[1:]
        if current_user.is_authenticated:
            userid = current_user.id
            username = current_user.username
            if userid is None or username is None:
                return redirect_to_login()
            else:
                # 登录成功
                return redirect_to_navigation(User().get_user(username))
        else:
            return redirect_to_login()

    else:
        GoPage = request.form.get('next') or ""
        if GoPage.startswith('/'):
            GoPage = GoPage[1:]
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember')
        if not username:
            return redirect_to_login('请输入用户名')
        user_info = User().get_user(username)
        if not user_info:
            return redirect_to_login('用户名或密码错误')
        # 校验密码
        if user_info.verify_password(password):
            # 创建用户 Session
            login_user(user_info)
            session.permanent = True if remember else False
            # 登录成功
            return redirect_to_navigation(user_info)
        else:
            return redirect_to_login('用户名或密码错误')


@App.route('/do', methods=['POST'])
@action_login_check # 只有通过安保大爷（登录认证）的请求才能进来
def do():
    # 接收前端传过来的两个重要参数：
    # cmd: 动作指令名称 (如 'restart_system')
    # data: 动作可能需要的附加参数 (如 {'id': 123})
    cmd = request.form.get("cmd")
    raw_data = request.form.get("data")
    if not cmd:
        return {"code": 400, "success": False, "msg": "缺少动作名称"}, 400
    data = None
    if raw_data:
        try:
            data = json.loads(raw_data)
        except (TypeError, ValueError):
            return {"code": 400, "success": False, "msg": "data 不是有效的 JSON"}, 400
    return WebAction().action(cmd, data)


@App.route('/robots.txt', methods=['GET'])
def robots():
    return send_from_directory("", "robots.txt")


@App.route('/telegram', methods=['POST'])
def telegram():
    """
    {
        'update_id': ,
        'message': {
            'message_id': ,
            'from': {
                'id': ,
                'is_bot': False,
                'first_name': '',
                'username': '',
                'language_code': 'zh-hans'
            },
            'chat': {
                'id': ,
                'first_name': '',
                'username': '',
                'type': 'private'
            },
            'date': ,
            'text': ''
        }
    }
    """
    expected_secret = str((Config().get_config("security") or {}).get("telegram_webhook_secret") or "")
    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected_secret:
        log.error("Telegram Webhook 密钥未配置，已拒绝请求")
        return "Webhook未配置", 503
    if not hmac.compare_digest(provided_secret, expected_secret):
        return "安全认证未通过", 403

    # 当前在用的交互渠道
    interactive_client = Message().get_interactive_client(SearchType.TG)
    if not interactive_client:
        return 'NAStool未启用Telegram交互'
    msg_json = request.get_json(silent=True) or {}
    if not SecurityHelper().check_telegram_ip(request.remote_addr):
        log.error("收到来自 %s 的非法Telegram消息：%s" % (request.remote_addr, msg_json))
        return '不允许的IP地址请求'
    if msg_json:
        message = msg_json.get("message", {})
        text = message.get("text")
        user_id = message.get("from", {}).get("id")
        log.info("收到Telegram消息：from=%s, text=%s" % (user_id, text))
        # 获取用户名
        user_name = message.get("from", {}).get("username")
        if text:
            # 检查权限
            if text.startswith("/"):
                if str(user_id) not in interactive_client.get("client").get_admin():
                    Message().send_channel_msg(channel=SearchType.TG,
                                               title="只有管理员才有权限执行此命令",
                                               user_id=user_id)
                    return '只有管理员才有权限执行此命令'
            else:
                if not str(user_id) in interactive_client.get("client").get_users():
                    Message().send_channel_msg(channel=SearchType.TG,
                                               title="你不在用户白名单中，无法使用此机器人",
                                               user_id=user_id)
                    return '你不在用户白名单中，无法使用此机器人'
            WebAction().handle_message_job(msg=text,
                                           in_from=SearchType.TG,
                                           user_id=user_id,
                                           user_name=user_name)
    return 'Ok'


@App.template_filter('b64encode')
def b64encode(s):
    return base64.b64encode(s.encode()).decode()


@App.template_filter('split')
def split(string, char, pos):
    return string.split(char)[pos]


@App.template_filter('brush_rule_string')
def brush_rule_string(rules):
    return WebAction.parse_brush_rule_string(rules)


@App.template_filter('str_filesize')
def str_filesize(size):
    return StringUtils.str_filesize(size, pre=1)


@App.template_filter('hash')
def md5_hash(text):
    return StringUtils.md5_hash(text)
