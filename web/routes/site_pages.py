"""站点资源、统计与刷流页面。"""

from flask import Blueprint, request, render_template
from flask_login import login_required

from app.brushtask import BrushTask
from app.conf import SystemConfig
from app.downloader import Downloader
from app.helper import ChromeHelper
from app.indexer import Indexer
from app.sites import Sites, SiteUserInfo
from config import Config
from web.action import WebAction
from web.security import current_user_can, sanitize_brush_task, sanitize_downloader


site_pages_bp = Blueprint("site_pages", __name__)


@site_pages_bp.route('/site', methods=['POST', 'GET'])
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


@site_pages_bp.route('/sitelist', methods=['POST', 'GET'])
@login_required
def sitelist():
    IndexerSites = Indexer().get_builtin_indexers(check=False, public=False)
    return render_template("site/sitelist.html",
                           Sites=IndexerSites,
                           Count=len(IndexerSites))


@site_pages_bp.route('/resources', methods=['POST', 'GET'])
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


@site_pages_bp.route('/statistics', methods=['POST', 'GET'])
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


@site_pages_bp.route('/brushtask', methods=['POST', 'GET'])
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
