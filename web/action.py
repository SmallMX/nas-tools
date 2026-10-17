from app.helper import DbHelper, ThreadHelper
from app.message import Message
from app.tools import SiteSignin
from app.torrentremover import TorrentRemover
from app.utils.types import SearchType
from web.actions.download import DownloadActions
from web.actions.search import SearchActions
from web.actions.sites import SiteActions
from web.actions.system import SystemActions, get_restart_target_pid
from web.actions.validation import (
    get_allowed_file_roots,
    is_valid_btih_magnet,
    parse_brush_rule,
    prepare_message_client_config,
    prepare_site_note,
    resolve_allowed_file_path,
    validate_configured_site_url,
    validate_site_config_url,
)
from web.backend.search_torrents import search_media_by_message
from web.tools import SiteSigninWebService


class WebAction:
    """保留动作协议与公开调用入口，将业务处理交给各领域服务。"""

    dbhelper = None
    _actions = {}
    TvTypes = ['TV', '电视剧']

    def __init__(self):
        self.dbhelper = DbHelper()
        self._downloads = DownloadActions(self.dbhelper)
        self._search = SearchActions(self.dbhelper, self._downloads)
        self._sites = SiteActions(self.dbhelper)
        self._system = SystemActions(self.dbhelper)
        site_signin_service = SiteSigninWebService()
        self._actions = {
            "sch": self._downloads.sch,
            "search": self._search.search,
            "download": self._downloads.download,
            "download_link": self._downloads.download_link,
            "download_torrent": self._downloads.download_torrent,
            "pt_start": self._downloads.pt_start,
            "pt_stop": self._downloads.pt_stop,
            "pt_remove": self._downloads.pt_remove,
            "pt_info": self._downloads.pt_info,
            "logging": self._system.logging,
            "update_site": self._sites.update_site,
            "get_site": self._sites.get_site,
            "get_brush_site_capabilities": self._sites.get_brush_site_capabilities,
            "del_site": self._sites.del_site,
            "get_site_favicon": self._sites.get_site_favicon,
            "restart": self._system.restart,
            "logout": self._system.logout,
            "update_config": self._system.update_config,
            "media_info": self._search.media_info,
            "test_connection": self._downloads.test_connection,
            "refresh_message": self._system.refresh_message,
            "delete_tmdb_cache": self._search.delete_tmdb_cache,
            "modify_tmdb_cache": self._search.modify_tmdb_cache,
            "add_brushtask": self._sites.add_brushtask,
            "del_brushtask": self._sites.del_brushtask,
            "brushtask_detail": self._sites.brushtask_detail,
            "add_downloader": self._downloads.add_downloader,
            "delete_downloader": self._downloads.delete_downloader,
            "get_downloader": self._downloads.get_downloader,
            "name_test": self._search.name_test,
            "net_test": self._system.net_test,
            "get_site_activity": self._sites.get_site_activity,
            "get_site_history": self._sites.get_site_history,
            "get_recommend": self.get_recommend,
            "get_downloaded": self.get_downloaded,
            "get_site_seeding_info": self._sites.get_site_seeding_info,
            "clear_tmdb_cache": self._search.clear_tmdb_cache,
            "check_site_attr": self._sites.check_site_attr,
            "refresh_process": self._system.refresh_process,

            "get_tvseason_list": self._search.get_tvseason_list,
            "run_brushtask": self._sites.run_brushtask,
            "list_site_resources": self._sites.list_site_resources,
            "get_categories": self._search.get_categories,

            "get_search_result": self.get_search_result,
            "search_media_infos": self.search_media_infos,
            "get_downloading": self.get_downloading,
            "test_site": self._sites.test_site,
            "get_download_setting": self._downloads.get_download_setting,
            "update_download_setting": self._downloads.update_download_setting,
            "delete_download_setting": self._downloads.delete_download_setting,
            "update_message_client": self._system.update_message_client,
            "delete_message_client": self._system.delete_message_client,
            "check_message_client": self._system.check_message_client,
            "get_message_client": self._system.get_message_client,
            "test_message_client": self._system.test_message_client,
            "get_sites": self._sites.get_sites,
            "get_indexers": self._sites.get_indexers,
            "get_download_dirs": self._downloads.get_download_dirs,
            "update_sites_cookie_ua": self._sites.update_sites_cookie_ua,
            "set_site_captcha_code": self._sites.set_site_captcha_code,
            "update_torrent_remove_task": self._downloads.update_torrent_remove_task,
            "get_torrent_remove_task": self._downloads.get_torrent_remove_task,
            "delete_torrent_remove_task": self._downloads.delete_torrent_remove_task,
            "get_remove_torrents": self._downloads.get_remove_torrents,
            "auto_remove_torrents": self._downloads.auto_remove_torrents,
            "list_brushtask_torrents": self._sites.list_brushtask_torrents,
            "set_system_config": self._system.set_system_config,
            "get_site_user_statistics": self.get_site_user_statistics,
            "send_custom_message": self.send_custom_message,
            "cookiecloud_sync": self._sites.cookiecloud_sync,
            "media_detail": self.media_detail,
            "media_similar": self._search.media_similar,
            "media_recommendations": self._search.media_recommendations,
            "media_person": self._search.media_person,
            "person_medias": self._search.person_medias,
            "save_user_script": self._system.save_user_script,
            "tool_site_signin_status": site_signin_service.status,
            "tool_site_signin_run": site_signin_service.run,
            "tool_site_signin_config_update": site_signin_service.update_config,
        }

    def action(self, cmd, data=None):
        func = self._actions.get(cmd)
        if not func:
            return {"code": -1, "msg": "非授权访问！"}
        else:
            return func(data)

    def api_action(self, cmd, data=None):
        result = self.action(cmd, data)
        if not result:
            return {
                "code": -1,
                "success": False,
                "message": "服务异常，未获取到返回结果"
            }
        code = result.get("code", result.get("retcode", 0))
        if not code or str(code) == "0":
            success = True
        else:
            success = False
        message = result.get("msg", result.get("retmsg", ""))
        for key in ['code', 'retcode', 'msg', 'retmsg']:
            if key in result:
                result.pop(key)
        return {
            "code": code,
            "success": success,
            "message": message,
            "data": result
        }

    @staticmethod
    def handle_message_job(msg, in_from=SearchType.OT, user_id=None, user_name=None):
        """
        处理消息事件
        """
        if not msg:
            return
        commands = {
            "/ptr": {"func": TorrentRemover().auto_remove_torrents, "desp": "删种"},
            "/signin": {"func": SiteSignin().signin, "desp": "站点签到"},
        }
        command = commands.get(msg)
        message = Message()

        if command:
            # 启动服务
            ThreadHelper().start_thread(command.get("func"), ())
            message.send_channel_msg(
                channel=in_from, title="正在运行 %s ..." % command.get("desp"), user_id=user_id)
        else:
            # 站点检索或直接下载
            ThreadHelper().start_thread(search_media_by_message,
                                        (msg, in_from, user_id, user_name))

    restart_server = staticmethod(SystemActions.restart_server)
    set_config_value = staticmethod(SystemActions.set_config_value)
    get_system_message = staticmethod(SystemActions.get_system_message)
    mediainfo_dict = staticmethod(SearchActions.mediainfo_dict)
    parse_brush_rule_string = staticmethod(SiteActions.parse_brush_rule_string)
    search_media_infos = staticmethod(SearchActions.search_media_infos)
    get_downloading = staticmethod(DownloadActions.get_downloading)
    get_site_user_statistics = staticmethod(SiteActions.get_site_user_statistics)
    send_custom_message = staticmethod(SystemActions.send_custom_message)
    media_detail = staticmethod(SearchActions.media_detail)

    def get_recommend(self, data):
        return self._search.get_recommend(data)

    def get_downloaded(self, data):
        return self._downloads.get_downloaded(data)

    def get_search_result(self, data=None):
        return self._search.get_search_result(data)
