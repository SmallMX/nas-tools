import base64
import datetime
import hmac
from functools import wraps
from threading import Lock

from flask import Flask, request, json, render_template, session, send_from_directory, redirect, url_for
from flask_compress import Compress
from flask_login import LoginManager, login_user, login_required, current_user
from sqlalchemy import text

import log
from app.brushtask import BrushTask
from app.conf import ModuleConf, SystemConfig
from app.db import MainDb, remove_db_session
from app.downloader import Downloader
from app.helper import SecurityHelper, MetaHelper, ChromeHelper
from app.indexer import Indexer
from app.message import Message
from app.sites import Sites, SiteUserInfo
from app.torrentremover import TorrentRemover
from app.utils import SystemUtils, ExceptionUtils, StringUtils
from app.utils.types import *
from config import Config
from web.action import WebAction
from web.apiv1 import apiv1_bp
from web.routes import system_files_bp, tool_pages_bp

from web.backend.user import User
from web.backend.wallpaper import get_login_wallpaper
from web.backend.web_utils import WebUtils
from web.security import (
    desensitize_config_dict,
    sanitize_brush_task,
    sanitize_downloader,
    sanitize_message_client,
)

# 配置文件锁
ConfigLock = Lock()

# ===== 1. Flask Web 框架初始化 =====
# 初学者注意：整个 Web 后端网站都是靠 Flask 跑起来的。
# 所有的页面加载、按钮点击，最终都会送到这里来处理。

# 实例化一个 Flask 应用程序对象，__name__ 代表当前模块名
App = Flask(__name__)
# 配置 JSON 数据返回时支持中文显示，而不是显示一堆 \u4e2d\u6587
App.json.ensure_ascii = False
App.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
SecurityConfig = Config().get_config("security") or {}
FlaskSecretKey = SecurityConfig.get("flask_secret_key")
if not FlaskSecretKey:
    raise RuntimeError("security.flask_secret_key 未配置，拒绝使用易失 Session 密钥启动")
App.secret_key = str(FlaskSecretKey)
CookieSecureConfig = SecurityConfig.get("session_cookie_secure", False)
CookieSecure = str(CookieSecureConfig).strip().lower() in {"1", "true", "yes", "on"}
App.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=CookieSecure,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_SECURE=CookieSecure,
)
# 用户如果勾选了“记住我”，登录状态可以保持 30 天
App.permanent_session_lifetime = datetime.timedelta(days=30)

# 启用网页压缩：让用户打开网页的速度更快
Compress(App)

# 登录管理模块：专门用来校验用户密码、记录是谁在访问
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

# API注册：注册一个蓝图（Blueprint）
# 蓝图是 Flask 分离代码的一种方式。意思是：只要网址是以 /api/v1 开头的，都交给 apiv1_bp 那个模块去处理
App.register_blueprint(apiv1_bp, url_prefix="/api/v1")
App.register_blueprint(system_files_bp)
App.register_blueprint(tool_pages_bp)


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


# 定义获取登录用户的方法
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


# 页面不存在
@App.errorhandler(404)
def page_not_found(error):
    return render_template("404.html", error=error), 404


# 服务错误
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


def current_user_can(permission):
    """返回当前 Session 用户是否具备指定权限，管理员始终允许。"""
    if not current_user.is_authenticated:
        return False
    user_info = User().get_user(current_user.username)
    if not user_info:
        return False
    permissions = set(str(user_info.pris).split(",")) if user_info.pris else set()
    return user_info.id == 0 or permission in permissions


# 主页面路由：如果用户访问项目的根域名 (如 http://localhost:3000/)，就会触发这里
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


# 资源搜索页面
@App.route('/search', methods=['POST', 'GET'])
@login_required
def search():
    # 权限
    if current_user.is_authenticated:
        username = current_user.username
        pris = User().get_user(username).pris
    else:
        pris = ""
    # 结果
    res = WebAction().get_search_result()
    SearchResults = res.get("result")
    Count = res.get("total")
    return render_template("search.html",
                           UserPris=str(pris).split(","),
                           Count=Count,
                           Results=SearchResults,
                           SiteDict=Indexer().get_indexer_hash_dict(),
                           UPCHAR=chr(8593))


# 站点维护页面
@App.route('/site', methods=['POST', 'GET'])
@login_required
def sites():
    CfgSites = Sites().get_sites()
    DownloadSettings = {did: attr["name"] for did, attr in Downloader().get_download_setting().items()}
    ChromeOk = ChromeHelper().get_status()
    can_system_settings = current_user_can("系统设置")
    CookieCloudCfg = {}
    CookieUserInfoCfg = {}
    if can_system_settings:
        cookie_cloud_cfg = SystemConfig().get_system_config('CookieCloud') or {}
        cookie_user_info_cfg = SystemConfig().get_system_config('CookieUserInfo') or {}
        # 长期凭据不回填到 HTML；需要执行敏感操作时由管理员重新输入。
        CookieCloudCfg = {
            "server": cookie_cloud_cfg.get("server") or "",
            "key": "",
            "password": "",
        }
        CookieUserInfoCfg = {
            "username": cookie_user_info_cfg.get("username") or "",
            "password": "",
            "two_step_code": "",
        }
    ocr_server = Config().get_config('app').get('ocr_server')
    return render_template("site/site.html",
                           Sites=CfgSites,
                           DownloadSettings=DownloadSettings,
                           ChromeOk=ChromeOk,
                           CanSystemSettings=can_system_settings,
                           OcrServerConfigured=isinstance(ocr_server, str) and bool(ocr_server.strip()),
                           CookieCloudCfg=CookieCloudCfg,
                           CookieUserInfoCfg=CookieUserInfoCfg)


# 站点列表页面
@App.route('/sitelist', methods=['POST', 'GET'])
@login_required
def sitelist():
    IndexerSites = Indexer().get_builtin_indexers(check=False, public=False)
    return render_template("site/sitelist.html",
                           Sites=IndexerSites,
                           Count=len(IndexerSites))


# 站点资源页面
@App.route('/resources', methods=['POST', 'GET'])
@login_required
def resources():
    site_id = request.args.get("site")
    site_name = request.args.get("title")
    page = request.args.get("page") or 0
    keyword = request.args.get("keyword")
    Results = WebAction().action("list_site_resources", {"id": site_id, "page": page, "keyword": keyword}).get(
        "data") or []
    return render_template("site/resources.html",
                           Results=Results,
                           SiteId=site_id,
                           Title=site_name,
                           CanDownload=current_user_can("下载管理"),
                           KeyWord=keyword,
                           TotalCount=len(Results),
                           PageRange=range(0, 10),
                           CurrentPage=int(page),
                           TotalPage=10)


# 推荐页面
@App.route('/recommend', methods=['POST', 'GET'])
@login_required
def recommend():
    Type = request.args.get("type") or ""
    SubType = request.args.get("subtype") or ""
    Title = request.args.get("title") or ""
    SubTitle = request.args.get("subtitle") or ""
    try:
        CurrentPage = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        return "页码必须是整数", 400
    if CurrentPage < 1 or CurrentPage > 10000:
        return "页码超出允许范围", 400
    Week = request.args.get("week") or ""
    TmdbId = request.args.get("tmdbid") or ""
    PersonId = request.args.get("personid") or ""
    Keyword = request.args.get("keyword") or ""
    Source = request.args.get("source") or ""
    FilterKey = request.args.get("filter") or ""
    raw_params = request.args.get("params")
    try:
        Params = json.loads(raw_params) if raw_params else {}
    except (TypeError, ValueError):
        return "推荐过滤参数不是有效的 JSON", 400
    if not isinstance(Params, dict):
        return "推荐过滤参数必须是 JSON 对象", 400
    return render_template("discovery/recommend.html",
                           Type=Type,
                           SubType=SubType,
                           Title=Title,
                           CurrentPage=CurrentPage,
                           Week=Week,
                           TmdbId=TmdbId,
                           PersonId=PersonId,
                           SubTitle=SubTitle,
                           Keyword=Keyword,
                           Source=Source,
                           Filter=FilterKey,
                           FilterConf=ModuleConf.DISCOVER_FILTER_CONF.get(FilterKey) if FilterKey else {},
                           Params=Params)


# 推荐页面
@App.route('/ranking', methods=['POST', 'GET'])
@login_required
def ranking():
    return render_template("discovery/ranking.html",
                           DiscoveryType="RANKING")


# 豆瓣电影


# 豆瓣电视剧


@App.route('/tmdb_movie', methods=['POST', 'GET'])
@login_required
def tmdb_movie():
    return render_template("discovery/recommend.html",
                           Type="DISCOVER",
                           SubType="MOV",
                           Title="TMDB电影",
                           Filter="tmdb_movie",
                           FilterConf=ModuleConf.DISCOVER_FILTER_CONF.get('tmdb_movie'))


@App.route('/tmdb_tv', methods=['POST', 'GET'])
@login_required
def tmdb_tv():
    return render_template("discovery/recommend.html",
                           Type="DISCOVER",
                           SubType="TV",
                           Title="TMDB电视剧",
                           Filter="tmdb_tv",
                           FilterConf=ModuleConf.DISCOVER_FILTER_CONF.get('tmdb_tv'))


# Bangumi每日放送
@App.route('/bangumi', methods=['POST', 'GET'])
@login_required
def discovery_bangumi():
    return render_template("discovery/ranking.html",
                           DiscoveryType="BANGUMI")


# 媒体详情页面
@App.route('/media_detail', methods=['POST', 'GET'])
@login_required
def media_detail():
    TmdbId = request.args.get("id")
    Type = request.args.get("type")
    return render_template("discovery/mediainfo.html",
                           TmdbId=TmdbId,
                           Type=Type)


# 演职人员页面
@App.route('/discovery_person', methods=['POST', 'GET'])
@login_required
def discovery_person():
    TmdbId = request.args.get("tmdbid")
    Title = request.args.get("title")
    SubTitle = request.args.get("subtitle")
    Type = request.args.get("type")
    return render_template("discovery/person.html",
                           TmdbId=TmdbId,
                           Title=Title,
                           SubTitle=SubTitle,
                           Type=Type)


# 正在下载页面
@App.route('/downloading', methods=['POST', 'GET'])
@login_required
def downloading():
    DispTorrents = WebAction().get_downloading().get("result")
    return render_template("download/downloading.html",
                           DownloadCount=len(DispTorrents),
                           Torrents=DispTorrents,
                           Client=Config().get_config("pt").get("pt_client"))


# 近期下载页面
@App.route('/downloaded', methods=['POST', 'GET'])
@login_required
def downloaded():
    CurrentPage = request.args.get("page") or 1
    return render_template("discovery/recommend.html",
                           Type='DOWNLOADED',
                           Title='近期下载',
                           CurrentPage=CurrentPage)


@App.route('/torrent_remove', methods=['POST', 'GET'])
@login_required
def torrent_remove():
    TorrentRemoveTasks = TorrentRemover().get_torrent_remove_tasks()
    return render_template("download/torrent_remove.html",
                           DownloaderConfig=ModuleConf.TORRENTREMOVER_DICT,
                           Count=len(TorrentRemoveTasks),
                           TorrentRemoveTasks=TorrentRemoveTasks)


# 数据统计页面
@App.route('/statistics', methods=['POST', 'GET'])
@login_required
def statistics():
    # 刷新单个site
    refresh_site = request.args.getlist("refresh_site")
    # 强制刷新所有
    refresh_force = True if request.args.get("refresh_force") else False
    # 总上传下载
    TotalUpload = 0
    TotalDownload = 0
    TotalSeedingSize = 0
    TotalSeeding = 0
    # 站点标签及上传下载
    SiteNames = []
    SiteUploads = []
    SiteDownloads = []
    SiteRatios = []
    SiteErrs = {}
    # 站点上传下载
    SiteData = SiteUserInfo().get_pt_date(specify_sites=refresh_site, force=refresh_force)
    if isinstance(SiteData, dict):
        for name, data in SiteData.items():
            if not data:
                continue
            up = data.get("upload", 0)
            dl = data.get("download", 0)
            ratio = data.get("ratio", 0)
            seeding = data.get("seeding", 0)
            seeding_size = data.get("seeding_size", 0)
            err_msg = data.get("err_msg", "")

            SiteErrs.update({name: err_msg})

            if not up and not dl and not ratio:
                continue
            if not str(up).isdigit() or not str(dl).isdigit():
                continue
            if name not in SiteNames:
                SiteNames.append(name)
                TotalUpload += int(up)
                TotalDownload += int(dl)
                TotalSeeding += int(seeding)
                TotalSeedingSize += int(seeding_size)
                SiteUploads.append(int(up))
                SiteDownloads.append(int(dl))
                SiteRatios.append(round(float(ratio), 1))

    # 近期上传下载各站点汇总
    CurrentUpload, CurrentDownload, _, _, _ = SiteUserInfo().get_pt_site_statistics_history(
        days=2)

    # 站点用户数据
    SiteUserStatistics = WebAction().get_site_user_statistics({"encoding": "DICT"}).get("data")

    return render_template("site/statistics.html",
                           CurrentDownload=CurrentDownload,
                           CurrentUpload=CurrentUpload,
                           TotalDownload=TotalDownload,
                           TotalUpload=TotalUpload,
                           TotalSeedingSize=TotalSeedingSize,
                           TotalSeeding=TotalSeeding,
                           SiteDownloads=SiteDownloads,
                           SiteUploads=SiteUploads,
                           SiteRatios=SiteRatios,
                           SiteNames=SiteNames,
                           SiteErr=SiteErrs,
                           SiteUserStatistics=SiteUserStatistics)


# 刷流任务页面
@App.route('/brushtask', methods=['POST', 'GET'])
@login_required
def brushtask():
    # 站点列表
    CfgSites = Sites().get_sites(brush=True)
    # 下载器列表
    Downloaders = [
        sanitize_downloader(downloader)
        for downloader in BrushTask().get_downloader_info()
    ]
    # 任务列表
    Tasks = [
        sanitize_brush_task(task)
        for task in BrushTask().get_brushtask_info()
    ]
    return render_template("site/brushtask.html",
                           Count=len(Tasks),
                           Sites=CfgSites,
                           Tasks=Tasks,
                           Downloaders=Downloaders)


# 自定义下载器页面
@App.route('/userdownloader', methods=['POST', 'GET'])
@login_required
def userdownloader():
    downloaders = [
        sanitize_downloader(downloader)
        for downloader in BrushTask().get_downloader_info()
    ]
    return render_template("download/userdownloader.html",
                           Count=len(downloaders),
                           Downloaders=downloaders)


# 服务页面
@App.route('/service', methods=['POST', 'GET'])
@login_required
def service():
    scheduler_cfg_list = []
    can_service = current_user_can("服务")
    can_system_settings = current_user_can("系统设置")
    if can_service:
        scheduler_cfg_list.append({
            'name': '名称识别测试',
            'time': '',
            'state': 'OFF',
            'id': 'nametest',
            'color': 'blue',
            'svg': '''
            <svg xmlns="http://www.w3.org/2000/svg" class="icon" width="40" height="40"
                 viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none">
              <path d="M4 6h16M4 12h10M4 18h7"></path>
            </svg>
            ''',
        })
    # 网络连通性测试
    svg = '''
    <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-network" width="40" height="40" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
       <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
       <circle cx="12" cy="9" r="6"></circle>
       <path d="M12 3c1.333 .333 2 2.333 2 6s-.667 5.667 -2 6"></path>
       <path d="M12 3c-1.333 .333 -2 2.333 -2 6s.667 5.667 2 6"></path>
       <path d="M6 9h12"></path>
       <path d="M3 19h7"></path>
       <path d="M14 19h7"></path>
       <circle cx="12" cy="19" r="2"></circle>
       <path d="M12 15v2"></path>
    </svg>
    '''
    targets = ModuleConf.NETTEST_TARGETS
    if can_system_settings:
        scheduler_cfg_list.append(
            {'name': '网络连通性测试', 'time': '', 'state': 'OFF', 'id': 'nettest', 'svg': svg,
             'color': 'cyan'})

    # 备份
    svg = '''
    <svg t="1660720525544" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="1559" width="16" height="16">
    <path d="M646 1024H100A100 100 0 0 1 0 924V258a100 100 0 0 1 100-100h546a100 100 0 0 1 100 100v31a40 40 0 1 1-80 0v-31a20 20 0 0 0-20-20H100a20 20 0 0 0-20 20v666a20 20 0 0 0 20 20h546a20 20 0 0 0 20-20V713a40 40 0 0 1 80 0v211a100 100 0 0 1-100 100z" fill="#ffffff" p-id="1560"></path>
    <path d="M924 866H806a40 40 0 0 1 0-80h118a20 20 0 0 0 20-20V100a20 20 0 0 0-20-20H378a20 20 0 0 0-20 20v8a40 40 0 0 1-80 0v-8A100 100 0 0 1 378 0h546a100 100 0 0 1 100 100v666a100 100 0 0 1-100 100z" fill="#ffffff" p-id="1561"></path>
    <path d="M469 887a40 40 0 0 1-27-10L152 618a40 40 0 0 1 1-60l290-248a40 40 0 0 1 66 30v128a367 367 0 0 0 241-128l94-111a40 40 0 0 1 70 35l-26 109a430 430 0 0 1-379 332v142a40 40 0 0 1-40 40zM240 589l189 169v-91a40 40 0 0 1 40-40c144 0 269-85 323-214a447 447 0 0 1-323 137 40 40 0 0 1-40-40v-83z" fill="#ffffff" p-id="1562"></path>
    </svg>
    '''
    if can_system_settings:
        scheduler_cfg_list.append(
            {'name': '配置备份', 'time': '', 'state': 'OFF', 'id': 'backup', 'svg': svg, 'color': 'green'})
    return render_template("service.html",
                           Count=len(scheduler_cfg_list),
                           SchedulerTasks=scheduler_cfg_list,
                           NettestTargets=targets,
                           CanSystemSettings=can_system_settings)


# TMDB缓存页面
@App.route('/tmdbcache', methods=['POST', 'GET'])
@login_required
def tmdbcache():
    page_num = request.args.get("pagenum")
    if not page_num:
        page_num = 30
    else:
        page_num = int(page_num)
    search_str = request.args.get("s")
    if not search_str:
        search_str = ""
    current_page = request.args.get("page")
    if not current_page:
        current_page = 1
    else:
        current_page = int(current_page)
    total_count, tmdb_caches = MetaHelper().dump_meta_data(search_str, current_page, page_num)

    from math import ceil
    total_page = ceil(total_count / page_num) if page_num > 0 else 1

    if total_page <= 5:
        start_page = 1
        end_page = total_page
    else:
        if current_page <= 3:
            start_page = 1
            end_page = 5
        else:
            start_page = current_page - 3
            if total_page > current_page + 3:
                end_page = current_page + 3
            else:
                end_page = total_page

    page_range = range(start_page, end_page + 1)

    return render_template("rename/tmdbcache.html",
                           TotalCount=total_count,
                           Count=len(tmdb_caches),
                           TmdbCaches=tmdb_caches,
                           Search=search_str,
                           CurrentPage=current_page,
                           TotalPage=total_page,
                           PageRange=page_range,
                           PageNum=page_num)


def render_basic_setting(section, title):
    context = {
        "SettingSection": section,
        "SettingTitle": title,
        "Config": desensitize_config_dict(Config().get_config())
    }
    if section == "system":
        proxy = context["Config"].get("app", {}).get("proxies", {}).get("http")
        context["Proxy"] = proxy.replace("http://", "") if proxy else None
        context["CustomScriptCfg"] = SystemConfig().get_system_config("CustomScript")
    return render_template("setting/basic.html", **context)


# 基础设置页面
@App.route('/basic', methods=['POST', 'GET'])
@login_required
def basic():
    return render_basic_setting("system", "基础设置")


# 媒体设置页面
@App.route('/media_setting', methods=['POST', 'GET'])
@login_required
def media_setting():
    return render_basic_setting("media", "媒体设置")


# 服务设置页面
@App.route('/service_setting', methods=['POST', 'GET'])
@login_required
def service_setting():
    return render_basic_setting("service", "服务设置")


# 安全设置页面
@App.route('/security_setting', methods=['POST', 'GET'])
@login_required
def security_setting():
    return render_basic_setting("security", "安全设置")


# 实验室页面
@App.route('/laboratory_setting', methods=['POST', 'GET'])
@login_required
def laboratory_setting():
    return render_basic_setting("laboratory", "实验室")


# 豆瓣页面


# 下载器页面
@App.route('/downloader', methods=['POST', 'GET'])
@login_required
def downloader():
    return render_template("setting/downloader.html",
                           Config=Config().get_config(),
                           DownloaderConf=ModuleConf.DOWNLOADER_CONF)


# 下载设置页面
@App.route('/download_setting', methods=['POST', 'GET'])
@login_required
def download_setting():
    DownloadSetting = Downloader().get_download_setting()
    DefaultDownloadSetting = Downloader().get_default_download_setting()
    Count = len(DownloadSetting)
    return render_template("setting/download_setting.html",
                           DownloadSetting=DownloadSetting,
                           DefaultDownloadSetting=DefaultDownloadSetting,
                           DownloaderTypes=DownloaderType,
                           Count=Count)


# 通知消息页面
@App.route('/notification', methods=['POST', 'GET'])
@login_required
def notification():
    MessageClients = {
        client_id: sanitize_message_client(client)
        for client_id, client in Message().get_message_client_info().items()
    }
    Channels = ModuleConf.MESSAGE_CONF.get("client")
    Switchs = ModuleConf.MESSAGE_CONF.get("switch")
    return render_template("setting/notification.html",
                           Channels=Channels,
                           Switchs=Switchs,
                           ClientCount=len(MessageClients),
                           MessageClients=MessageClients)


# 用户管理页面
@App.route('/users', methods=['POST', 'GET'])
@login_required
def users():
    Users = WebAction().get_users().get("result")
    return render_template("setting/users.html", Users=Users, UserCount=len(Users))


# 事件响应核心路由！极其重要！
# 这是整个 Web 前端和后台业务互动的交通枢纽。页面上的按钮操作（如“删种”、“重启”），
# 都是给 `/do` 这个接口发送 POST 请求。
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


# 禁止搜索引擎
@App.route('/robots.txt', methods=['GET'])
def robots():
    return send_from_directory("", "robots.txt")






# Telegram消息响应
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




# base64模板过滤器
@App.template_filter('b64encode')
def b64encode(s):
    return base64.b64encode(s.encode()).decode()


# split模板过滤器
@App.template_filter('split')
def split(string, char, pos):
    return string.split(char)[pos]


# 刷流规则过滤器
@App.template_filter('brush_rule_string')
def brush_rule_string(rules):
    return WebAction.parse_brush_rule_string(rules)


# 大小格式化过滤器
@App.template_filter('str_filesize')
def str_filesize(size):
    return StringUtils.str_filesize(size, pre=1)


# MD5 HASH过滤器
@App.template_filter('hash')
def md5_hash(text):
    return StringUtils.md5_hash(text)
