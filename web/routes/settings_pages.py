"""配置、用户、通知与系统维护页面。"""

from flask import Blueprint, request, render_template
from flask_login import login_required

from app.brushtask import BrushTask
from app.conf import ModuleConf, SystemConfig
from app.downloader import Downloader
from app.helper import MetaHelper
from app.message import Message
from app.utils.types import DownloaderType
from config import Config
from web.action import WebAction
from web.security import (
    current_user_can,
    desensitize_config_dict,
    sanitize_downloader,
    sanitize_message_client,
)


settings_pages_bp = Blueprint("settings_pages", __name__)


@settings_pages_bp.route('/userdownloader', methods=['POST', 'GET'])
@login_required
def userdownloader():
    downloaders = [
        sanitize_downloader(downloader)
        for downloader in BrushTask().get_downloader_info()
    ]
    return render_template("download/userdownloader.html",
                           Count=len(downloaders),
                           Downloaders=downloaders)


@settings_pages_bp.route('/service', methods=['POST', 'GET'])
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


@settings_pages_bp.route('/tmdbcache', methods=['POST', 'GET'])
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


@settings_pages_bp.route('/basic', methods=['POST', 'GET'])
@login_required
def basic():
    return render_basic_setting("system", "基础设置")


@settings_pages_bp.route('/media_setting', methods=['POST', 'GET'])
@login_required
def media_setting():
    return render_basic_setting("media", "媒体设置")


@settings_pages_bp.route('/service_setting', methods=['POST', 'GET'])
@login_required
def service_setting():
    return render_basic_setting("service", "服务设置")


@settings_pages_bp.route('/security_setting', methods=['POST', 'GET'])
@login_required
def security_setting():
    return render_basic_setting("security", "安全设置")


@settings_pages_bp.route('/laboratory_setting', methods=['POST', 'GET'])
@login_required
def laboratory_setting():
    return render_basic_setting("laboratory", "实验室")


@settings_pages_bp.route('/downloader', methods=['POST', 'GET'])
@login_required
def downloader():
    return render_template("setting/downloader.html",
                           Config=Config().get_config(),
                           DownloaderConf=ModuleConf.DOWNLOADER_CONF)


@settings_pages_bp.route('/download_setting', methods=['POST', 'GET'])
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


@settings_pages_bp.route('/notification', methods=['POST', 'GET'])
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


@settings_pages_bp.route('/users', methods=['POST', 'GET'])
@login_required
def users():
    Users = WebAction().get_users().get("result")
    return render_template("setting/users.html", Users=Users, UserCount=len(Users))
