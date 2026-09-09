#!/usr/bin/env python3
"""只读 UI 预览：真实模板 + 内存示例，不加载业务模块、配置或数据库。

运行：.venv/bin/python scripts/preview_ui.py --port 5108
检查：.venv/bin/python scripts/preview_ui.py --check
入口：http://127.0.0.1:5108/preview
"""

from __future__ import annotations

import argparse
import ast
import base64
from enum import Enum
import hashlib
import html
import json
from pathlib import Path
import sys
from urllib.parse import quote

from flask import Flask, Response, abort, jsonify, render_template, request
from flask_restx import Api, Resource
from jinja2 import ChainableUndefined


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PERMISSIONS = ["探索", "资源搜索", "站点管理", "下载管理", "服务", "系统设置"]
GIB = 1024 ** 3
READ_ONLY_MESSAGE = "只读演示模式：此操作不会执行，也不会保存任何配置或任务。"
TITLES = ["远山来信", "深海回声", "城市之外", "星河彼岸", "森林之声", "夏日序章", "长夜微光", "重返旷野"]
PALETTES = [("#203c41", "#c2a77f"), ("#102e49", "#52999e"), ("#544336", "#d2ae79"),
            ("#22283c", "#8297bd"), ("#1c4031", "#9fad7d"), ("#9c705e", "#ead4a0"),
            ("#302b40", "#a18d9d"), ("#385359", "#bac9bb")]


class DownloaderType(Enum):
    QB = "Qbittorrent"
    TR = "Transmission"


def read_public_ui_definitions():
    """只解析公开的控件描述常量，不执行模块，也不读取运行配置。"""
    class EnumNames(ast.NodeTransformer):
        def visit_Attribute(self, node):
            return ast.copy_location(ast.Constant(node.attr), node)

    tree = ast.parse((ROOT / "app/conf/moduleconf.py").read_text())
    module_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ModuleConf")
    requested = {"DOWNLOADER_CONF", "TORRENTREMOVER_DICT", "DISCOVER_FILTER_CONF", "MESSAGE_CONF", "TORRENT_SEARCH_PARAMS"}
    result = {}
    for node in module_class.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in requested:
            result[node.targets[0].id] = ast.literal_eval(EnumNames().visit(node.value))
    return result


DEFINITIONS = read_public_ui_definitions()
CONFIG = {
    "app": {"logtype": "console", "loglevel": "info", "logpath": "/demo/logs", "logserver": "",
            "wallpaper": "themoviedb", "login_user": "demo", "login_password": "", "domain": "",
            "proxies": {}, "user_agent": "NAS-Tools UI Preview", "rmt_tmdbkey": "demo-key",
            "tmdb_domain": "api.themoviedb.org", "rmt_match_mode": "normal", "ocr_server": ""},
    "pt": {"pt_client": "qbittorrent", "site_search_concurrency": 5, "pt_monitor_only": True,
           "search_auto": False, "download_order": "site"},
    "media": {"category": "default-category"},
    "security": {"api_key": "demo-only", "session_cookie_secure": False,
                 "telegram_webhook_allow_ip": {"ipv4": "127.0.0.1/32", "ipv6": "::1/128"}},
    "laboratory": {"search_keyword": True, "search_tmdbweb": False, "tmdb_cache_expire": True,
                   "use_douban_titles": True, "search_en_title": False, "release_groups": "", "tmdb_proxy": ""},
    "qbittorrent": {"qbhost": "demo-downloader.local", "qbport": "8080", "qbusername": "demo",
                    "qbpassword": "", "verify_cert": True, "auto_management": False},
    "transmission": {"trhost": "", "trport": "9091", "trusername": "", "trpassword": ""},
    "downloaddir": [{"type": "电影", "category": "", "path": "/demo/downloads/movies", "minfreespace": "50"}],
}
MEDIA = [{"id": i + 1, "title": title, "type": "MOV" if i % 3 else "TV", "year": 2026 - i % 3,
          "vote": round(8.1 + (i % 5) / 5, 1), "image": f"/preview/art/{i}/poster.svg",
          "overview": "这是一段用于检查排版与信息层级的示例简介，所有内容均为本地演示数据。",
          "media_type": "剧情" if i % 2 else "冒险", "date": "2026-09-09", "site": "示例站点"}
         for i, title in enumerate(TITLES)]
SITES = [{"id": i + 1, "name": name, "pri": i + 1, "signurl": f"https://site-{i + 1}.example/",
          "domain": f"site-{i + 1}.example", "cookie": "已配置（示例）", "rssurl": "已配置（示例）",
          "download_setting": 1, "signin_enable": True, "login_enable": i == 1, "rss_enable": True,
          "brush_enable": i < 2, "statistic_enable": True, "parse": True, "unread_msg_notify": True,
          "chrome": False, "proxy": False, "builtin": True, "public": False}
         for i, name in enumerate(["松林影站", "云海资源", "北辰影库", "光影档案"])]
DOWNLOADERS = [{"id": 1, "name": "主下载器（示例）", "type": "qbittorrent", "host": "demo-downloader.local",
                "port": "8080", "username": "demo", "password": "", "save_dir": "/demo/downloads"}]
TORRENTS = [{"id": str(i + 1), "title": f"{item['title']}.{item['year']}.2160p.WEB-DL.H265",
             "image": item["image"], "speed": speed, "progress": progress, "state": state,
             "noprogress": False, "nomenu": False}
            for i, (item, speed, progress, state) in enumerate(zip(MEDIA[:4],
                ["↓ 12.5 MB/s · ↑ 256 KB/s", "↓ 8.4 MB/s · ↑ 120 KB/s", "↑ 3.2 MB/s · 做种中", "已暂停"],
                [62, 35, 100, 0], ["Downloading", "Downloading", "Seeding", "Stoped"]))]
DOWNLOAD_SETTINGS = {1: {"id": 1, "name": "日常下载", "downloader": "Qbittorrent", "category": "movies",
                          "tags": "NASTOOL", "upload_limit": 0, "download_limit": 0, "content_layout": 0,
                          "ratio_limit": 2, "seeding_time_limit": 2880, "is_paused": False}}
BRUSH_TASKS = [{"id": 1, "name": "松林 · 免费资源", "site": SITES[0]["name"], "state": "Y", "free": "FREE",
                "downloader": 1, "interval": 10, "totalsize": 300, "rss_rule": "大小 5–40 GB",
                "remove_rule": "做种 72 小时", "sendmessage": "Y", "forceupload": "N", "download_count": 28,
                "remove_count": 12, "download_size": "238.4 GB", "upload_size": "1.26 TB",
                "lst_mod_date": "2026-09-09 08:30", "rssurl": "", "up_limit": 0, "down_limit": 0}]
REMOVE_TASKS = {1: {"id": 1, "name": "完成做种后暂停", "enabled": True, "downloader": "Qb", "onlynastool": True,
                    "samedata": False, "interval": 30, "action": 1,
                    "config": {"ratio": 2, "seeding_time": 72, "upload_avs": 0, "size": [1, 80],
                               "savepath_key": "/demo/downloads", "tracker_key": "", "qb_category": ["movies"],
                               "tags": ["NASTOOL"], "torrent_state": ["uploading", "stalledUP"]}}}
STATISTICS = [{"site": site["name"], "url": site["signurl"], "username": "demo", "user_level": "Power User",
               "upload": (800 + i * 240) * GIB, "download": (180 + i * 60) * GIB,
               "ratio": round((800 + i * 240) / (180 + i * 60), 2), "seeding": 60 + i * 25,
               "seeding_size": (240 + i * 90) * GIB, "bonus": 38560 + i * 2450,
               "join_at": "2024-06-18", "update_at": "2026-09-09 08:30", "msg_unread": 0}
              for i, site in enumerate(SITES)]
RESOURCES = [{"title": torrent["title"], "description": "示例资源 · 4K / HEVC / 中文字幕", "enclosure": "",
              "page_url": "", "size": (18 + i * 7) * GIB, "seeders": 128 - i * 12, "peers": 4 + i,
              "grabs": 350 + i * 83, "uploadvolumefactor": 1.0, "downloadvolumefactor": 0.0,
              "pubdate": "2026-09-09 08:00", "date_elapsed": f"{i + 1} 小时前", "imdbid": ""}
             for i, torrent in enumerate(TORRENTS)]


def search_results():
    torrents = [{"id": str(i + 1), "site": SITES[i]["name"], "torrent_name": TORRENTS[0]["title"],
                 "description": "示例资源 · 中文字幕 / 杜比视界", "video_encode": "H265", "reseffect": "HDR10",
                 "size": f"{24 + i * 3}.6 GB", "releasegroup": "DEMO", "uploadvalue": 1.0,
                 "downloadvalue": 0.0, "seeders": 156 - i * 24, "pageurl": "", "enclosure": ""}
                for i in range(3)]
    group = {"group_info": {"restype": "WEB-DL", "respix": "2160p"}, "group_total": len(torrents),
             "group_torrents": {"demo": {"torrent_list": torrents}}}
    return {TITLES[0]: {"key": "demo-media", "poster": MEDIA[0]["image"], "tmdbid": 1,
                        "type": "电影", "vote": 8.7, "overview": MEDIA[0]["overview"], "exist": False,
                        "filter": {"season": [], "site": [s["name"] for s in SITES[:3]],
                                   "free": [{"name": "FREE", "value": "1.0 0.0"}], "video": ["H265"]},
                        "torrent_dict": [("MOV", {"4k": group})]}}


PAGES = {
    "ranking": ("榜单推荐", "discovery/ranking.html"), "tmdb_movie": ("TMDB 电影", "discovery/recommend.html"),
    "tmdb_tv": ("TMDB 电视剧", "discovery/recommend.html"), "bangumi": ("每日放送", "discovery/ranking.html"),
    "recommend": ("推荐列表", "discovery/recommend.html"), "media_detail": ("媒体详情", "discovery/mediainfo.html"),
    "discovery_person": ("演员阵容", "discovery/person.html"), "search": ("资源搜索", "search.html"),
    "site": ("站点维护", "site/site.html"), "sitelist": ("站点资源", "site/sitelist.html"),
    "resources": ("单站资源", "site/resources.html"), "statistics": ("数据统计", "site/statistics.html"),
    "brushtask": ("刷流任务", "site/brushtask.html"), "userdownloader": ("自定义下载器", "download/userdownloader.html"),
    "downloading": ("正在下载", "download/downloading.html"), "downloaded": ("近期下载", "discovery/recommend.html"),
    "torrent_remove": ("自动删种", "download/torrent_remove.html"), "tools": ("工具", "tools/index.html"),
    "tools/site-signin": ("站点自动签到", "tools/site_signin.html"), "service": ("服务", "service.html"),
    "tmdbcache": ("TMDB 缓存", "rename/tmdbcache.html"), "basic": ("基础设置", "setting/basic.html"),
    "media_setting": ("媒体设置", "setting/basic.html"), "service_setting": ("服务设置", "setting/basic.html"),
    "security_setting": ("安全设置", "setting/basic.html"), "laboratory_setting": ("实验室", "setting/basic.html"),
    "downloader": ("下载器", "setting/downloader.html"), "download_setting": ("下载设置", "setting/download_setting.html"),
    "notification": ("消息通知", "setting/notification.html"), "users": ("用户管理", "setting/users.html"),
}
VARIANTS = ["recommend?type=SEARCH&title=媒体搜索&keyword=远山", "recommend?type=MOV&subtype=person&title=参演作品",
            "recommend?type=MOV&subtype=sim&title=类似作品", "recommend?type=MOV&subtype=more&title=相关推荐",
            "recommend?type=TV&subtype=bangumi&week=3&title=星期三", "resources?site=1&title=松林影站"]


def page_context(page):
    channels = DEFINITIONS["MESSAGE_CONF"]
    context = dict(
        Config=CONFIG, CustomScriptCfg={"css": "", "javascript": ""}, Proxy="",
        UserPris=PERMISSIONS, UserName="demo", SystemFlag="MacOS", AppVersion="UI Preview",
        SiteFavicons={s["name"]: "/static/img/logo.png" for s in SITES}, SearchSource="tmdb", TMDBFlag=1,
        RestypeDict=DEFINITIONS["TORRENT_SEARCH_PARAMS"]["restype"], PixDict=DEFINITIONS["TORRENT_SEARCH_PARAMS"]["pix"],
        Indexers=SITES, Sites=SITES, CanDownload=True, CanSystemSettings=True, ChromeOk=True,
        CookieCloudCfg={}, CookieUserInfoCfg={"username": "demo"}, OcrServerConfigured=False,
        DownloadSettings={i: v["name"] for i, v in DOWNLOAD_SETTINGS.items()}, Downloaders=DOWNLOADERS,
        Count=0, CurrentPage=1, TotalPage=1, PageRange=[1], PageNum=30, Search="", KeyWord="", TotalCount=0,
        Type=request.args.get("type", "MOV"), SubType=request.args.get("subtype", ""), Title=request.args.get("title", PAGES.get(page, ("", ""))[0]),
        SubTitle=request.args.get("subtitle", ""), TmdbId=request.args.get("id", "1"), PersonId=request.args.get("personid", "1"),
        Week=request.args.get("week", "3"), Keyword=request.args.get("keyword", ""), Source="tmdb", Filter="", FilterConf={}, Params={},
        DiscoveryType="BANGUMI" if page == "bangumi" else "RANKING", UPCHAR="↑", SiteId="1",
        SiteDict={hashlib.md5(s["name"].encode()).hexdigest(): s for s in SITES},
        DownloaderConf=DEFINITIONS["DOWNLOADER_CONF"], DownloaderConfig=DEFINITIONS["TORRENTREMOVER_DICT"],
        DownloaderTypes=DownloaderType, DownloadSetting=DOWNLOAD_SETTINGS, DefaultDownloadSetting=1,
        Channels=channels["client"], Switchs=channels["switch"], ClientCount=1,
        MessageClients={1: {"id": 1, "type": "telegram", "name": "Telegram 通知（示例）", "enabled": True,
                            "interactive": False, "switchs": ["download_start", "site_signin"], "config": {}}},
        Users=[{"name": "demo", "pris": PERMISSIONS}, {"name": "viewer", "pris": ["探索", "资源搜索"]}], UserCount=2,
        SettingSection={"basic": "system", "media_setting": "media", "service_setting": "service",
                        "security_setting": "security", "laboratory_setting": "laboratory"}.get(page, "system"),
        SettingTitle=PAGES.get(page, ("", ""))[0],
    )
    if page == "search": context.update(Count=3, Results=search_results())
    if page in {"site", "sitelist"}: context.update(Count=len(SITES))
    if page == "resources": context.update(Results=RESOURCES, TotalCount=len(RESOURCES), CurrentPage=0, PageRange=[0], Title=SITES[0]["name"])
    if page == "userdownloader": context.update(Count=len(DOWNLOADERS))
    if page == "downloading": context.update(Torrents=TORRENTS, DownloadCount=len(TORRENTS), Client="qbittorrent")
    if page == "download_setting": context.update(Count=len(DOWNLOAD_SETTINGS))
    if page == "brushtask": context.update(Count=len(BRUSH_TASKS), Tasks=BRUSH_TASKS)
    if page == "torrent_remove": context.update(Count=len(REMOVE_TASKS), TorrentRemoveTasks=REMOVE_TASKS)
    if page == "tools": context.update(Tools=[{"name": "站点自动签到", "description": "管理每日签到、失败重试与执行记录。", "icon": "sign_in.svg", "page": "tools/site-signin"}])
    if page == "tools/site-signin": context.update(ToolConfig={"cron": "08:00", "concurrency": 5, "history_days": 30, "notify": True, "retry_keyword": "错误|失败|超时"})
    if page == "service":
        context.update(Count=3, SchedulerTasks=[{"id": key, "name": title, "state": "OFF", "time": "", "color": "green", "svg": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 5h14v14H5zM8 9h8M8 13h5"/></svg>'}
                       for key, title in [("nametest", "名称识别测试"), ("nettest", "网络连通性测试"), ("backup", "配置备份")]],
                       NettestTargets=["api.themoviedb.org", "image.tmdb.org", "api.telegram.org"])
    if page == "tmdbcache":
        cache = [[f"demo-{i}", {"title": media["title"], "year": media["year"], "tmdb_id": media["id"], "media_type": "电影", "name": media["title"]}] for i, media in enumerate(MEDIA)]
        context.update(Count=len(cache), TotalCount=len(cache), TmdbCaches=cache)
    if page == "statistics":
        context.update(SiteNames=[s["site"] for s in STATISTICS], SiteUploads=[s["upload"] for s in STATISTICS],
                       SiteDownloads=[s["download"] for s in STATISTICS], SiteRatios=[s["ratio"] for s in STATISTICS],
                       SiteErr={}, SiteUserStatistics=STATISTICS, CurrentUpload=85 * GIB, CurrentDownload=24 * GIB,
                       TotalUpload=sum(s["upload"] for s in STATISTICS), TotalDownload=sum(s["download"] for s in STATISTICS),
                       TotalSeeding=sum(s["seeding"] for s in STATISTICS), TotalSeedingSize=sum(s["seeding_size"] for s in STATISTICS))
    if page in {"tmdb_movie", "tmdb_tv"}: context.update(Type="DISCOVER", SubType="MOV" if page == "tmdb_movie" else "TV", Filter=page, FilterConf=DEFINITIONS["DISCOVER_FILTER_CONF"][page])
    if page == "downloaded": context.update(Type="DOWNLOADED")
    return context


def attach_swagger_preview(app):
    """使用原生 RESTX 页面与项目样式；只从 AST 提取分组、路径和方法。"""
    api = Api(app, prefix="/api/v1", doc="/api/v1/", version="1.0", title="NAStool Api",
              description="只读 UI 预览：真实接口路径与方法；参数模型未加载，所有调用均被拦截。",
              security="Bearer Auth", authorizations={"Bearer Auth": {"type": "apiKey", "name": "Authorization", "in": "header"}})
    tree = ast.parse((WEB / "apiv1.py").read_text())
    namespaces = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "namespace":
            name = ast.literal_eval(node.value.args[0])
            description = next((ast.literal_eval(kw.value) for kw in node.value.keywords if kw.arg == "description"), name)
            namespaces[node.targets[0].id] = api.namespace(name, description=description)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef): continue
        route = next((d for d in node.decorator_list if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "route" and isinstance(d.func.value, ast.Name) and d.func.value.id in namespaces), None)
        if route is None: continue
        methods = {}
        for method in node.body:
            if isinstance(method, ast.FunctionDef) and method.name in {"get", "post", "put", "patch", "delete"}:
                def blocked_resource(self, **kwargs):
                    return {"code": -1, "msg": READ_ONLY_MESSAGE, "preview": True}, 403
                blocked_resource.__doc__ = ast.get_docstring(method) or "只读预览，调用已禁用。"
                methods[method.name] = blocked_resource
        namespaces[route.func.value.id].add_resource(type(f"Preview{node.name}", (Resource,), methods), ast.literal_eval(route.args[0]))


def create_preview_app():
    app = Flask("nastool_ui_preview", template_folder=str(WEB / "templates"), static_folder=str(WEB / "static"))
    app.config.update(TEMPLATES_AUTO_RELOAD=True, MAX_CONTENT_LENGTH=1024 * 1024)
    app.jinja_env.undefined = ChainableUndefined
    app.jinja_env.filters.update(hash=lambda value: hashlib.md5(str(value).encode()).hexdigest(),
                                b64encode=lambda value: base64.b64encode(str(value).encode()).decode(),
                                split=lambda value, sep=",": str(value).split(sep),
                                brush_rule_string=lambda value: html.escape(str(value or "")),
                                str_filesize=lambda value: f"{float(value or 0) / GIB:.1f} GB")
    attach_swagger_preview(app)

    @app.after_request
    def isolate_preview(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; object-src 'none'; form-action 'self'; frame-ancestors 'none'"
        if response.mimetype == "text/html" and not response.direct_passthrough:
            body = response.get_data(as_text=True)
            if "</body>" in body:
                badge = '<a href="/preview" style="position:fixed;bottom:12px;left:12px;z-index:1040;padding:8px 12px;background:#e7f2eb;color:#20332d;border:1px solid #bed2c4;border-radius:8px;font:12px system-ui;text-decoration:none">示例数据 · 只读预览</a>'
                guard = '<script>document.addEventListener("click",function(e){const a=e.target.closest("a[href]");if(a && /^https?:/.test(a.href) && new URL(a.href).origin!==location.origin){e.preventDefault();window.show_fail_modal?.("只读演示模式：外部链接不会打开。");}},true);const previewFetch=window.fetch;window.fetch=async function(...args){const r=await previewFetch(...args);if(r.status===403){const p=await r.clone().json().catch(()=>({}));if(p.preview)window.show_fail_modal?.(p.msg);}return r;};</script>'
                response.set_data(body.replace("<head>", '<head><base href="/">', 1).replace("</body>", badge + guard + "</body>"))
        return response

    @app.route("/", methods=["GET", "POST"])
    def shell():
        if request.method == "POST": return blocked()
        context = page_context("")
        context["GoPage"] = request.args.get("next", "ranking").lstrip("/")
        return render_template("navigation.html", **context)

    @app.get("/preview")
    def index():
        links = [("登录", "/preview/login"), ("API 文档（Swagger）", "/api/v1/"), *[(title, "/?next=" + quote(path, safe="")) for path, (title, _) in PAGES.items()],
                 *[(path, "/?next=" + quote(path, safe="")) for path in VARIANTS],
                 *[(str(code), f"/preview/error/{code}") for code in (403, 404, 500)]]
        content = "".join(f'<a href="{url}">{html.escape(title)}</a>' for title, url in links)
        return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI 只读预览</title><style>body{font:15px/1.6 system-ui;background:#f5f6f2;color:#20332d;margin:32px auto;padding:0 24px;max-width:1100px}nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}nav a{padding:16px;background:white;border:1px solid #dee5dd;border-radius:12px;color:#187761;text-decoration:none}p{color:#68786f}</style></head><body><h1>NAS-Tools UI 只读预览</h1><p>真实模板 · 本地示例数据 · 不连接站点或下载器 · 所有写操作均被拦截</p><nav>' + content + '</nav></body></html>'

    @app.get("/preview/login")
    def login_preview():
        return render_template("login.html", GoPage="ranking", LoginWallpaper="/preview/art/0/backdrop.svg", err_msg="")

    @app.get("/preview/error/<int:code>")
    def error_preview(code):
        if code not in (403, 404, 500): abort(404)
        return render_template(f"{code}.html", error="示例错误状态")

    @app.get("/preview/art/<int:index>/<kind>.svg")
    def artwork(index, kind):
        i = index % len(TITLES)
        dark, light = PALETTES[i]
        title = TITLES[i]
        width, height = (1280, 540) if kind == "backdrop" else (480, 720)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 480 720" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="g" x2=".7" y2="1"><stop stop-color="{dark}"/><stop offset="1" stop-color="{light}"/></linearGradient></defs><rect width="480" height="720" fill="url(#g)"/><circle cx="{140 + i * 18}" cy="240" r="105" fill="{light}" opacity=".65"/><path d="M-20 610 170 330 270 450 370 290 530 570V750H-20" fill="{dark}" opacity=".65"/><path d="M-20 680 160 510 280 590 420 450 530 620V750H-20" fill="{dark}" opacity=".8"/><text x="36" y="62" fill="#fff" opacity=".6" font-family="system-ui" font-size="14" letter-spacing="4">NAS-TOOLS · DEMO</text><text x="36" y="623" fill="#fff" font-family="system-ui" font-size="40" font-weight="600" letter-spacing="4">{title}</text><text x="38" y="662" fill="#fff" opacity=".65" font-family="system-ui" font-size="16" letter-spacing="3">示例影像 / 2026</text></svg>'
        return Response(svg, mimetype="image/svg+xml")

    def blocked():
        return jsonify(code=-1, msg=READ_ONLY_MESSAGE, preview=True), 403

    @app.route("/upload", methods=["GET", "POST"])
    @app.route("/backup", methods=["GET", "POST"])
    @app.route("/api/<path:unused>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def block_side_effects(unused=None):
        return blocked()

    @app.post("/dirlist")
    def directory_preview():
        return '<ul class="jqueryFileTree"><li class="directory collapsed"><a href="#" rel="/demo/downloads/">downloads（示例目录）</a></li></ul>'

    @app.post("/do")
    def read_action():
        cmd = request.form.get("cmd", "")
        try: params = json.loads(request.form.get("data", "{}"))
        except (TypeError, ValueError): return jsonify(code=-1, msg="无效示例参数"), 400
        if not isinstance(params, dict): return jsonify(code=-1, msg="无效示例参数"), 400
        if cmd == "get_recommend":
            return jsonify(code=0, Items=MEDIA if int(params.get("page") or 1) == 1 else [], preview=True)
        if cmd == "media_detail":
            detail = dict(MEDIA[0], tmdbid=1, background=["/preview/art/0/backdrop.svg"], runtime="128 分钟", genres="剧情 / 冒险",
                          link="", douban_link="", crews=[{"导演": "陈远（示例）"}, {"编剧": "林川（示例）"}],
                          fact=[{"原名": "Letters from the Mountains"}, {"状态": "已上映"}, {"语言": "中文"}, {"地区": "中国"}],
                          actors=[{"id": i + 1, "name": name, "role": "主演", "image": f"/preview/art/{i}/poster.svg"} for i, name in enumerate(["林川（示例）", "许晴禾（示例）", "周宁（示例）", "陈亦（示例）"])])
            return jsonify(code=0, data=detail)
        if cmd == "media_person": return jsonify(code=0, data=[{"id": i + 1, "name": name, "role": "主演", "image": f"/preview/art/{i}/poster.svg"} for i, name in enumerate(["林川（示例）", "许晴禾（示例）", "周宁（示例）", "陈亦（示例）"])])
        if cmd == "pt_info": return jsonify(code=0, retcode="0", torrents=TORRENTS)
        if cmd == "get_indexers": return jsonify(code=0, indexers=SITES)
        if cmd == "get_sites": return jsonify(code=0, data=SITES, sites=SITES)
        if cmd == "get_site_favicon": return jsonify(code=0, data={s["name"]: "/static/img/logo.png" for s in SITES})
        if cmd == "get_download_setting": return jsonify(code=0, data=DOWNLOAD_SETTINGS[1] if params.get("sid") else list(DOWNLOAD_SETTINGS.values()), default=1)
        if cmd == "get_download_dirs": return jsonify(code=0, paths=["/demo/downloads"])
        if cmd == "get_categories": return jsonify(code=0, data=["剧情", "纪录片"], categories=["剧情", "纪录片"])
        if cmd == "get_tvseason_list": return jsonify(code=0, seasons=[1, 2, 3])
        if cmd == "get_site_history":
            dataset = [["site", "upload", "download"], *[[s["name"], (24 + i * 5) * GIB, (4 + i) * GIB] for i, s in enumerate(SITES)]] if int(params.get("days") or 7) == 1 else [["date", "upload", "download"], *[[f"09-{i:02}", (25 + i * 4) * GIB, (5 + i) * GIB] for i in range(3, 10)]]
            return jsonify(code=0, dataset=dataset)
        if cmd == "get_site_user_statistics": return jsonify(code=0, data=STATISTICS)
        if cmd == "tool_site_signin_status":
            items = [{"site": site["name"], "action_name": "签到", "success": [True, True, False, None][i], "message": ["签到成功（示例）", "已完成（示例）", "连接超时（示例）", "等待下次执行"][i], "created_at": "2026-09-09 08:00", "duration": 860 + 120 * i} for i, site in enumerate(SITES)]
            return jsonify(code=0, running=False, summary={"total": 4, "success": 2, "failed": 1, "pending": 1}, items=items, history=items[:3])
        if cmd == "refresh_message": return jsonify(code=0, lst_time="demo", message=[] if params.get("lst_time") else [{"title": "只读预览已就绪", "content": "当前使用本地示例数据，不连接任何外部服务。", "time": "2026-09-09 08:00", "status": "success"}])
        if cmd == "refresh_process": return jsonify(code=0, value=100, text="示例数据已加载")
        if cmd == "logging": return jsonify(code=0, loglist=[] if params.get("refresh_new") else [
            {"time": "08:30:01", "source": "System", "level": "INFO", "text": "只读 UI 预览已就绪（示例日志）"},
            {"time": "08:30:02", "source": "Indexer", "level": "INFO", "text": "已加载 4 个示例站点"},
            {"time": "08:30:03", "source": "Downloader", "level": "INFO", "text": "当前任务数据来自本地 fixtures，未连接下载器"}])
        if cmd in {"get_remove_torrents", "list_brushtask_torrents", "get_site_activity", "get_site_seeding_info"}: return jsonify(code=0, data=[], torrents=[], dataset=[], preview=True)
        if cmd == "get_site": return jsonify(code=0, data=SITES[0], site=SITES[0])
        if cmd == "get_downloader": return jsonify(code=0, info=DOWNLOADERS[0])
        if cmd == "get_brush_site_capabilities": return jsonify(code=0, data={})
        if cmd == "brushtask_detail": return jsonify(code=0, task=dict(BRUSH_TASKS[0], site=1, rss_rule={}, remove_rule={}))
        if cmd == "get_torrent_remove_task": return jsonify(code=0, detail=REMOVE_TASKS[1])
        if cmd == "get_message_client": return jsonify(code=0, detail={"id": 1, "type": "telegram", "name": "Telegram 通知（示例）", "enabled": 1, "interactive": 0, "switchs": ["site_signin"], "config": {"token": "demo-token", "chat_id": "demo-chat"}})
        return blocked()

    @app.route("/<path:page>", methods=["GET", "POST"])
    def fragment(page):
        if page not in PAGES: abort(404)
        return render_template(PAGES[page][1], **page_context(page))

    return app


def check_preview(app):
    """检查真实模板渲染和预览写入屏障，不启动 HTTP 服务。"""
    client = app.test_client()
    failures = []
    paths = ["/", "/preview", "/preview/login", "/api/v1/", "/api/v1/swagger.json", *["/" + path for path in PAGES], *["/" + path for path in VARIANTS], *[f"/preview/error/{code}" for code in (403, 404, 500)]]
    for path in paths:
        response = client.get(path)
        if response.status_code != 200: failures.append(f"{path}: {response.status_code}")
    for cmd in ("update_config", "restart", "tool_site_signin_run", "download", "pt_remove", "cookiecloud_sync", "net_test", "check_message_client"):
        if client.post("/do", data={"cmd": cmd, "data": "{}"}).status_code != 403: failures.append(f"write allowed: {cmd}")
    for path in ("/upload", "/backup", "/api/v1/config/update"):
        if client.post(path).status_code != 403: failures.append(f"write allowed: {path}")
    assert "web.main" not in sys.modules and "config" not in sys.modules and "app" not in sys.modules
    if failures:
        print("预览检查失败：\n" + "\n".join(failures))
        return 1
    print(f"预览检查通过：{len(paths)} 个真实模板页面/变体；11 个写入入口均已拦截；未加载业务或真实配置模块。")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5108)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    preview = create_preview_app()
    if args.check: raise SystemExit(check_preview(preview))
    print(f"只读 UI 预览：http://127.0.0.1:{args.port}/preview", flush=True)
    preview.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
