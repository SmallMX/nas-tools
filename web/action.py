import ast
import copy
import datetime
import html as html_lib
import json
import os.path
import re
import signal
from pathlib import Path
from threading import Timer
from urllib.parse import urlsplit

import cn2an
from flask import has_request_context, request
from flask_login import logout_user, current_user
from werkzeug.security import generate_password_hash

import log
from app.brushtask import BrushTask
from app.conf import SystemConfig, ModuleConf
from app.downloader import Downloader
from app.downloader.client import Qbittorrent, Transmission
from app.helper import DbHelper, ProgressHelper, ThreadHelper, \
    MetaHelper, DisplayHelper, CookieCloudHelper
from app.indexer import Indexer
from app.media import Category, Media, Bangumi, DouBan
from app.media.meta import MetaInfo, MetaBase
from app.message import Message, MessageCenter
from app.retired_features import ACTIVE_USER_PERMISSIONS, sanitize_config_write
from app.scheduler import stop_scheduler
from app.sites import Sites, SiteUserInfo, SiteCookie
from app.tools import SiteSignin
from app.torrentremover import TorrentRemover
from app.utils import StringUtils, RequestUtils, ExceptionUtils, Torrent
from app.utils.types import SearchType, DownloaderType, MediaType, MovieTypes
from config import Config
from web.backend.search_torrents import search_medias_for_web, search_media_by_message
from web.backend.web_utils import WebUtils
from web.security import (
    request_has_system_settings,
    sanitize_downloader,
    sanitize_message_client,
)
from web.tools import SiteSigninWebService


def get_allowed_file_roots():
    """返回允许 Web 文件操作触达的已配置目录。"""
    configured_paths = list(Downloader().get_download_visit_dirs() or [])

    roots = set()
    for configured_path in configured_paths:
        candidate = Path(str(configured_path)).expanduser()
        if not candidate.is_absolute():
            continue
        resolved = candidate.resolve(strict=False)
        if resolved == Path(resolved.anchor):
            continue
        roots.add(resolved)
    return tuple(sorted(roots, key=lambda item: len(str(item)), reverse=True))


def resolve_allowed_file_path(path, roots=None, must_exist=True):
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ValueError("文件路径为空或不合法")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("文件路径必须为绝对路径")
    try:
        resolved = candidate.resolve(strict=must_exist)
    except (FileNotFoundError, OSError) as error:
        raise ValueError("文件不存在或无法访问") from error
    allowed_roots = roots if roots is not None else get_allowed_file_roots()
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError("文件路径不在允许操作的目录内")
    return resolved


def parse_brush_rule(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError("刷流规则格式不合法")
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as error:
        raise ValueError("刷流规则无法解析") from error
    if not isinstance(parsed, dict):
        raise ValueError("刷流规则必须为字典")
    return parsed


def prepare_message_client_config(ctype, config, existing_config=None):
    """解析消息渠道配置，并在编辑时安全保留未重新提交的密码字段。"""
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (TypeError, ValueError) as error:
            raise ValueError("消息渠道配置不是有效 JSON") from error
    if not isinstance(config, dict):
        raise ValueError("消息渠道配置格式不合法")
    prepared = dict(config)
    existing = existing_config if isinstance(existing_config, dict) else {}
    client_schema = ModuleConf.MESSAGE_CONF.get("client", {}).get(ctype)
    if not client_schema:
        raise ValueError("不支持的消息渠道类型")
    fields = client_schema.get("config", {}) or {}
    unknown_fields = set(prepared).difference(fields)
    if unknown_fields:
        raise ValueError("消息渠道配置包含未知字段")
    for field_name, field_attr in fields.items():
        if field_attr.get("type") != "password":
            continue
        value = prepared.get(field_name)
        if value in (None, "", "******"):
            old_value = existing.get(field_name)
            if old_value:
                prepared[field_name] = old_value
            elif field_attr.get("required"):
                raise ValueError(f"{field_attr.get('title') or field_name} 不能为空")
            else:
                prepared[field_name] = ""
    for field_name, field_attr in fields.items():
        if field_attr.get("required") and prepared.get(field_name) in (None, ""):
            raise ValueError(f"{field_attr.get('title') or field_name} 不能为空")
    return prepared


_MAGNET_PATTERN = re.compile(
    r"^magnet:\?xt=urn:btih:(?:[0-9a-f]{40}|[a-z2-7]{32})(?:&[^\s#]{1,4000})?$",
    re.IGNORECASE,
)


def is_valid_btih_magnet(value):
    return isinstance(value, str) and len(value) <= 4096 and bool(_MAGNET_PATTERN.fullmatch(value.strip()))


def _url_endpoint(value):
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError("下载链接为空或过长")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("下载链接地址不合法") from error
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("下载链接仅支持 HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("下载链接不得包含用户凭据")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("下载链接域名不合法") from error
    effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    return host, effective_port


def validate_site_config_url(value, label="站点地址"):
    """规范并校验管理员保存的站点 URL，仅接受不含凭据的 HTTP(S) 地址。"""
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    try:
        _url_endpoint(normalized)
    except ValueError as error:
        raise ValueError(f"{label}仅支持有效的 HTTP(S) 地址") from error
    return normalized


def validate_configured_site_url(site_name, value):
    """仅允许访问请求所指向、且服务端已保存的站点地址。"""
    if not isinstance(site_name, str) or not site_name.strip():
        raise ValueError("未指定已配置站点")
    saved_site = next((
        site for site in Sites().get_sites() or []
        if str(site.get("name") or "") == site_name.strip()
    ), None)
    if not saved_site:
        raise ValueError("站点未在服务端配置")
    allowed_endpoints = set()
    for saved_url in (
            saved_site.get("signurl"),
            saved_site.get("rssurl"),
            saved_site.get("strict_url")):
        if not saved_url:
            continue
        try:
            allowed_endpoints.add(_url_endpoint(saved_url))
        except ValueError:
            continue
    endpoint = _url_endpoint(value)
    if endpoint not in allowed_endpoints:
        raise ValueError("下载链接与服务端保存的站点地址不匹配")
    return value


_ALLOWED_SITE_NOTE_KEYS = frozenset({
    "apikey", "download_setting", "parse", "ua",
    "chrome", "proxy", "message",
})


def prepare_site_note(note):
    """仅持久化当前站点功能仍会读取的扩展属性。"""
    if isinstance(note, str):
        if not note.strip():
            return ""
        try:
            note = json.loads(note)
        except (TypeError, ValueError) as error:
            raise ValueError("站点属性不是有效 JSON") from error
    if note is None:
        return None
    if not isinstance(note, dict):
        raise ValueError("站点属性格式不合法")
    return json.dumps({
        key: value for key, value in note.items() if key in _ALLOWED_SITE_NOTE_KEYS
    }, ensure_ascii=False)


def get_restart_target_pid(server_software=None):
    if server_software is None and has_request_context():
        server_software = request.environ.get("SERVER_SOFTWARE")
    server_software = str(server_software or os.environ.get("SERVER_SOFTWARE", "")).lower()
    if server_software.startswith("gunicorn"):
        parent_pid = os.getppid()
        if parent_pid > 1:
            return parent_pid
    return os.getpid()


class WebAction:
    dbhelper = None
    _actions = {}
    TvTypes = ['TV', '电视剧']

    def __init__(self):
        self.dbhelper = DbHelper()
        site_signin_service = SiteSigninWebService()
        self._actions = {
            "sch": self.__sch,
            "search": self.__search,
            "download": self.__download,
            "download_link": self.__download_link,
            "download_torrent": self.__download_torrent,
            "pt_start": self.__pt_start,
            "pt_stop": self.__pt_stop,
            "pt_remove": self.__pt_remove,
            "pt_info": self.__pt_info,
            "logging": self.__logging,
            "update_site": self.__update_site,
            "get_site": self.__get_site,
            "get_brush_site_capabilities": self.__get_brush_site_capabilities,
            "del_site": self.__del_site,
            "get_site_favicon": self.__get_site_favicon,
            "restart": self.__restart,
            "logout": self.__logout,
            "update_config": self.__update_config,
            "media_info": self.__media_info,
            "test_connection": self.__test_connection,
            "user_manager": self.__user_manager,
            "refresh_message": self.__refresh_message,
            "delete_tmdb_cache": self.__delete_tmdb_cache,
            "modify_tmdb_cache": self.__modify_tmdb_cache,
            "add_brushtask": self.__add_brushtask,
            "del_brushtask": self.__del_brushtask,
            "brushtask_detail": self.__brushtask_detail,
            "add_downloader": self.__add_downloader,
            "delete_downloader": self.__delete_downloader,
            "get_downloader": self.__get_downloader,
            "name_test": self.__name_test,
            "net_test": self.__net_test,
            "get_site_activity": self.__get_site_activity,
            "get_site_history": self.__get_site_history,
            "get_recommend": self.get_recommend,
            "get_downloaded": self.get_downloaded,
            "get_site_seeding_info": self.__get_site_seeding_info,
            "clear_tmdb_cache": self.__clear_tmdb_cache,
            "check_site_attr": self.__check_site_attr,
            "refresh_process": self.__refresh_process,

            "get_tvseason_list": self.__get_tvseason_list,
            "run_brushtask": self.__run_brushtask,
            "list_site_resources": self.__list_site_resources,
            "get_categories": self.__get_categories,

            "get_search_result": self.get_search_result,
            "search_media_infos": self.search_media_infos,
            "get_users": self.get_users,
            "get_downloading": self.get_downloading,
            "test_site": self.__test_site,
            "get_download_setting": self.__get_download_setting,
            "update_download_setting": self.__update_download_setting,
            "delete_download_setting": self.__delete_download_setting,
            "update_message_client": self.__update_message_client,
            "delete_message_client": self.__delete_message_client,
            "check_message_client": self.__check_message_client,
            "get_message_client": self.__get_message_client,
            "test_message_client": self.__test_message_client,
            "get_sites": self.__get_sites,
            "get_indexers": self.__get_indexers,
            "get_download_dirs": self.__get_download_dirs,
            "update_sites_cookie_ua": self.__update_sites_cookie_ua,
            "set_site_captcha_code": self.__set_site_captcha_code,
            "update_torrent_remove_task": self.__update_torrent_remove_task,
            "get_torrent_remove_task": self.__get_torrent_remove_task,
            "delete_torrent_remove_task": self.__delete_torrent_remove_task,
            "get_remove_torrents": self.__get_remove_torrents,
            "auto_remove_torrents": self.__auto_remove_torrents,
            "list_brushtask_torrents": self.__list_brushtask_torrents,
            "set_system_config": self.__set_system_config,
            "get_site_user_statistics": self.get_site_user_statistics,
            "send_custom_message": self.send_custom_message,
            "cookiecloud_sync": self.__cookiecloud_sync,
            "media_detail": self.media_detail,
            "media_similar": self.__media_similar,
            "media_recommendations": self.__media_recommendations,
            "media_person": self.__media_person,
            "person_medias": self.__person_medias,
            "save_user_script": self.__save_user_script,
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
    def restart_server():
        """
        返回响应后发送 SIGTERM，由外部进程管理器按部署策略拉起服务。
        """
        logout_user()

        target_pid = get_restart_target_pid()

        def shutdown():
            stop_scheduler()
            DisplayHelper().quit()
            os.kill(target_pid, signal.SIGTERM)

        timer = Timer(0.75, shutdown)
        timer.daemon = True
        timer.start()

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

    @staticmethod
    def set_config_value(cfg, cfg_key, cfg_value):
        """
        根据Key设置配置值
        """
        if cfg_value == "******":
            return cfg
        cfg_value = sanitize_config_write(cfg_key, cfg_value)
        optional_service_labels = {
            "app.ocr_server": "OCR服务地址",
            "laboratory.tmdb_proxy": "TMDB代理服务地址",
        }
        if cfg_key in optional_service_labels:
            cfg_value = validate_site_config_url(
                cfg_value, optional_service_labels[cfg_key]
            ).rstrip('/')
        # 密码
        if cfg_key == "app.login_password":
            if not cfg_value:
                return cfg
            if not cfg_value.startswith("[hash]"):
                cfg['app']['login_password'] = "[hash]%s" % generate_password_hash(
                    cfg_value)
            else:
                cfg['app']['login_password'] = cfg_value
            return cfg
        # 代理
        if cfg_key == "app.proxies":
            if cfg_value:
                if not cfg_value.startswith("http") and not cfg_value.startswith("sock"):
                    cfg['app']['proxies'] = {
                        "https": "http://%s" % cfg_value, "http": "http://%s" % cfg_value}
                else:
                    cfg['app']['proxies'] = {"https": "%s" %
                                             cfg_value, "http": "%s" % cfg_value}
            else:
                cfg['app']['proxies'] = {"https": None, "http": None}
            return cfg
        # 最大支持三层赋值
        keys = cfg_key.split(".")
        if keys:
            if len(keys) == 1:
                cfg[keys[0]] = cfg_value
            elif len(keys) == 2:
                if not cfg.get(keys[0]):
                    cfg[keys[0]] = {}
                cfg[keys[0]][keys[1]] = cfg_value
            elif len(keys) == 3:
                if cfg.get(keys[0]):
                    if not cfg[keys[0]].get(keys[1]) or isinstance(cfg[keys[0]][keys[1]], str):
                        cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value
                else:
                    cfg[keys[0]] = {}
                    cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value

        return cfg

    @staticmethod
    def __sch(data):
        """
        启动定时服务
        """
        commands = {
            "autoremovetorrents": TorrentRemover().auto_remove_torrents,
        }
        sch_item = data.get("item")
        command = commands.get(sch_item)
        if not command:
            return {"code": 1, "msg": "不支持的服务", "item": sch_item}
        ThreadHelper().start_thread(command, ())
        return {"code": 0, "msg": "服务已启动", "item": sch_item}

    @staticmethod
    def __search(data):
        """
        WEB检索资源
        """
        search_word = data.get("search_word")
        ident_flag = False if data.get("unident") else True
        filters = data.get("filters")
        tmdbid = data.get("tmdbid")
        media_type = data.get("media_type")
        if media_type:
            if media_type in MovieTypes:
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        if search_word:
            ret, ret_msg = search_medias_for_web(content=search_word,
                                                 ident_flag=ident_flag,
                                                 filters=filters,
                                                 tmdbid=tmdbid,
                                                 media_type=media_type)
            if ret != 0:
                return {"code": ret, "msg": ret_msg}
        return {"code": 0}

    def __download(self, data):
        """
        从WEB添加下载
        """
        dl_id = data.get("id")
        dl_dir = data.get("dir")
        dl_setting = data.get("setting")
        results = self.dbhelper.get_search_result_by_id(dl_id)
        for res in results:
            media = Media().get_media_info(title=res.torrent_name, subtitle=res.description)
            if not media:
                continue
            media.set_torrent_info(enclosure=res.enclosure,
                                   size=res.size,
                                   site=res.site,
                                   page_url=res.pageurl,
                                   upload_volume_factor=float(
                                       res.upload_volume_factor),
                                   download_volume_factor=float(res.download_volume_factor))
            # 添加下载
            ret, ret_msg = Downloader().download(media_info=media,
                                                 download_dir=dl_dir,
                                                 download_setting=dl_setting)
            if ret:
                # 发送消息
                media.user_name = current_user.username
                Message().send_download_message(in_from=SearchType.WEB,
                                                can_item=media)
            else:
                return {"retcode": -1, "retmsg": ret_msg}
        return {"retcode": 0, "retmsg": ""}

    @staticmethod
    def __download_link(data):
        """
        从WEB添加下载链接
        """
        site = data.get("site")
        enclosure = data.get("enclosure")
        title = data.get("title")
        description = data.get("description")
        page_url = data.get("page_url")
        size = data.get("size")
        seeders = data.get("seeders")
        uploadvolumefactor = data.get("uploadvolumefactor")
        downloadvolumefactor = data.get("downloadvolumefactor")
        dl_dir = data.get("dl_dir")
        dl_setting = data.get("dl_setting")
        if not isinstance(title, str) or not title.strip() or len(title) > 1000 \
                or not isinstance(enclosure, str):
            return {"code": -1, "msg": "种子信息有误"}
        enclosure = enclosure.strip()
        try:
            if is_valid_btih_magnet(enclosure):
                if page_url:
                    page_url = validate_configured_site_url(site, page_url)
            elif (enclosure.startswith("[") and enclosure.endswith("]")) \
                    or enclosure.startswith("#"):
                if len(enclosure) > 4096:
                    raise ValueError("站点解析规则过长")
                page_url = validate_configured_site_url(site, page_url)
            else:
                enclosure = validate_configured_site_url(site, enclosure)
                if page_url:
                    page_url = validate_configured_site_url(site, page_url)
            uploadvolumefactor = float(uploadvolumefactor if uploadvolumefactor is not None else 1)
            downloadvolumefactor = float(downloadvolumefactor if downloadvolumefactor is not None else 1)
            if not 0 <= uploadvolumefactor <= 10 or not 0 <= downloadvolumefactor <= 10:
                raise ValueError("上传或下载系数超出允许范围")
        except (TypeError, ValueError) as error:
            return {"code": -1, "msg": str(error)}
        media = Media().get_media_info(title=title, subtitle=description)
        if not media:
            media = MetaInfo(title=title)
            media.org_string = title
        media.site = site
        media.enclosure = enclosure
        media.page_url = page_url
        media.size = size
        media.upload_volume_factor = uploadvolumefactor
        media.download_volume_factor = downloadvolumefactor
        media.seeders = seeders
        # 添加下载
        ret, ret_msg = Downloader().download(media_info=media,
                                             download_dir=dl_dir,
                                             download_setting=dl_setting)
        if ret:
            # 发送消息
            media.user_name = current_user.username
            Message().send_download_message(SearchType.WEB, media)
            return {"code": 0, "msg": "下载成功"}
        else:
            return {"code": 1, "msg": ret_msg or "如连接正常，请检查下载任务是否存在"}

    @staticmethod
    def __download_torrent(data):
        """
        从种子文件添加下载
        """

        def __download(_media_info, _file_path):
            _media_info.site = "WEB"
            # 添加下载
            ret, ret_msg = Downloader().download(media_info=_media_info,
                                                 download_dir=dl_dir,
                                                 download_setting=dl_setting,
                                                 torrent_file=_file_path)
            # 发送消息
            _media_info.user_name = current_user.username
            if ret:
                Message().send_download_message(SearchType.WEB, _media_info)
            else:
                Message().send_download_fail_message(_media_info, ret_msg)
            return bool(ret), ret_msg or "下载器拒绝了任务"

        if not isinstance(data, dict):
            return {"code": -1, "msg": "请求格式不合法"}
        dl_dir = data.get("dl_dir")
        dl_setting = data.get("dl_setting")
        files = data.get("files") or []
        magnets = data.get("magnets") or []
        if not isinstance(files, list) or not isinstance(magnets, list):
            return {"code": -1, "msg": "种子文件和磁链必须使用列表格式"}
        files = [item for item in files if item]
        magnets = [item for item in magnets if item]
        if not files and not magnets:
            return {"code": -1, "msg": "没有种子文件或磁链"}
        if len(files) + len(magnets) > 20:
            return {"code": -1, "msg": "单次最多处理 20 个种子或磁链"}

        temp_root = Path(Config().get_temp_path()).resolve()
        failures = []
        success_count = 0
        for index, file_item in enumerate(files, start=1):
            file_path = None
            try:
                if not isinstance(file_item, dict):
                    raise ValueError("文件描述格式不合法")
                file_name = file_item.get("upload", {}).get("filename")
                if not isinstance(file_name, str) \
                        or Path(file_name).name != file_name \
                        or Path(file_name).suffix.lower() != ".torrent":
                    raise ValueError("仅接受临时目录中的 .torrent 文件名")
                raw_path = temp_root / file_name
                if raw_path.is_symlink():
                    raise ValueError("不允许使用符号链接种子文件")
                file_path = raw_path.resolve(strict=True)
                if file_path.parent != temp_root or not file_path.is_file():
                    raise ValueError("种子文件不在临时目录内")
                media_info = Media().get_media_info(title=file_name)
                if not media_info:
                    media_info = MetaInfo(title=file_name)
                    media_info.org_string = file_name
                success, error_message = __download(media_info, str(file_path))
                if success:
                    success_count += 1
                else:
                    failures.append(f"文件 {index}: {error_message}")
            except (OSError, ValueError) as error:
                failures.append(f"文件 {index}: {error}")
            except Exception as error:
                ExceptionUtils.exception_traceback(error)
                failures.append(f"文件 {index}: 处理失败")
            finally:
                if file_path and file_path.parent == temp_root:
                    try:
                        file_path.unlink(missing_ok=True)
                    except OSError:
                        log.warn(f"【Download】临时种子文件清理失败：{file_path.name}")

        for index, magnet in enumerate(magnets, start=1):
            try:
                if not is_valid_btih_magnet(magnet):
                    raise ValueError("磁链必须以 magnet:?xt=urn:btih: 开头并包含有效 BTIH")
                magnet = magnet.strip()
                title = Torrent().get_magnet_title(magnet)
                if title:
                    media_info = Media().get_media_info(title=title)
                else:
                    media_info = MetaInfo(title="磁力链接")
                    media_info.org_string = magnet
                if not media_info:
                    media_info = MetaInfo(title=title or "磁力链接")
                    media_info.org_string = title or magnet
                media_info.set_torrent_info(enclosure=magnet,
                                            download_volume_factor=0,
                                            upload_volume_factor=1)
                success, error_message = __download(media_info, None)
                if success:
                    success_count += 1
                else:
                    failures.append(f"磁链 {index}: {error_message}")
            except ValueError as error:
                failures.append(f"磁链 {index}: {error}")
            except Exception as error:
                ExceptionUtils.exception_traceback(error)
                failures.append(f"磁链 {index}: 处理失败")

        if failures:
            return {
                "code": 1,
                "msg": f"成功 {success_count} 项，失败 {len(failures)} 项：" + "；".join(failures),
                "success_count": success_count,
                "failures": failures,
            }
        return {"code": 0, "msg": f"成功添加 {success_count} 个下载任务"}

    @staticmethod
    def __pt_start(data):
        """
        开始下载
        """
        tid = data.get("id") if isinstance(data, dict) else None
        if not tid:
            return {"retcode": 1, "retmsg": "下载任务 ID 不能为空", "id": tid}
        if Downloader().start_torrents(ids=tid):
            return {"retcode": 0, "id": tid}
        return {"retcode": 1, "retmsg": "下载器未能启动任务", "id": tid}

    @staticmethod
    def __pt_stop(data):
        """
        停止下载
        """
        tid = data.get("id") if isinstance(data, dict) else None
        if not tid:
            return {"retcode": 1, "retmsg": "下载任务 ID 不能为空", "id": tid}
        if Downloader().stop_torrents(ids=tid):
            return {"retcode": 0, "id": tid}
        return {"retcode": 1, "retmsg": "下载器未能停止任务", "id": tid}

    @staticmethod
    def __pt_remove(data):
        """
        删除下载
        """
        tid = data.get("id") if isinstance(data, dict) else None
        if not tid:
            return {"retcode": 1, "retmsg": "下载任务 ID 不能为空", "id": tid}
        if Downloader().delete_torrents(ids=tid, delete_file=True):
            return {"retcode": 0, "id": tid}
        return {"retcode": 1, "retmsg": "下载器未能删除任务", "id": tid}

    @staticmethod
    def __pt_info(data):
        """
        查询具体种子的信息
        """
        ids = data.get("ids")
        Client, Torrents = Downloader().get_torrents(torrent_ids=ids)
        DispTorrents = []
        for torrent in Torrents:
            if not torrent:
                continue
            if Client == DownloaderType.QB:
                if torrent.get('state') in ['pausedDL']:
                    state = "Stoped"
                    speed = "已暂停"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.get('dlspeed'))
                    eta = StringUtils.str_timelong(torrent.get('eta'))
                    upspeed = StringUtils.str_filesize(torrent.get('upspeed'))
                    speed = "%s%sB/s %s%sB/s %s" % (chr(8595),
                                                    dlspeed, chr(8593), upspeed, eta)
                # 进度
                progress = round(torrent.get('progress') * 100)
                # 主键
                key = torrent.get('hash')

            else:
                if torrent.status in ['stopped']:
                    state = "Stoped"
                    speed = "已暂停"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.rateDownload)
                    upspeed = StringUtils.str_filesize(torrent.rateUpload)
                    speed = "%s%sB/s %s%sB/s" % (chr(8595),
                                                 dlspeed, chr(8593), upspeed)
                # 进度
                progress = round(torrent.progress, 1)
                # 主键
                key = torrent.id

            torrent_info = {'id': key, 'speed': speed,
                            'state': state, 'progress': progress}
            if torrent_info not in DispTorrents:
                DispTorrents.append(torrent_info)
        return {"retcode": 0, "torrents": DispTorrents}

    @staticmethod
    def __logging(data):
        """
        查询实时日志
        """
        log_list = []
        refresh_new = data.get('refresh_new')
        source = data.get('source')

        if not source:
            if not refresh_new:
                log_list = list(log.LOG_QUEUE)
            elif log.LOG_INDEX:
                if log.LOG_INDEX > len(list(log.LOG_QUEUE)):
                    log_list = list(log.LOG_QUEUE)
                else:
                    log_list = list(log.LOG_QUEUE)[-log.LOG_INDEX:]
            log.LOG_INDEX = 0
        else:
            queue_logs = list(log.LOG_QUEUE)
            for message in queue_logs:
                if str(message.get("source")) == source:
                    log_list.append(message)
                else:
                    continue

            if refresh_new:
                if int(refresh_new) < len(log_list):
                    log_list = log_list[int(refresh_new):]
                elif int(refresh_new) >= len(log_list):
                    log_list = []
        return {"loglist": log_list}

    def __update_site(self, data):
        """
        维护站点信息
        """

        def __is_site_duplicate(query_name, query_tid):
            # 检查是否重名
            _sites = self.dbhelper.get_site_by_name(name=query_name)
            for site in _sites:
                site_id = site.id
                if str(site_id) != str(query_tid):
                    return True
            return False

        tid = data.get('site_id')
        name = data.get('site_name')
        site_pri = data.get('site_pri')
        try:
            rssurl = validate_site_config_url(data.get('site_rssurl'), "站点 RSS 地址")
            signurl = validate_site_config_url(data.get('site_signurl'), "站点签到地址")
            note = prepare_site_note(data.get('site_note'))
        except ValueError as error:
            return {"code": 400, "msg": str(error)}
        cookie = data.get('site_cookie')
        rss_uses = data.get('site_include')

        if __is_site_duplicate(name, tid):
            return {"code": 400, "msg": "站点名称重复"}

        if tid:
            sites = self.dbhelper.get_site_by_id(tid)
            # 站点不存在
            if not sites:
                return {"code": 400, "msg": "站点不存在"}

            old_name = sites[0].name
            old_cookie = sites[0].cookie

            if cookie == "******":
                cookie = old_cookie

            ret = self.dbhelper.update_config_site(tid=tid,
                                                   name=name,
                                                   site_pri=site_pri,
                                                   rssurl=rssurl,
                                                   signurl=signurl,
                                                   cookie=cookie,
                                                   note=note,
                                                   rss_uses=rss_uses)
            if ret and (name != old_name):
                # 更新历史站点数据信息
                self.dbhelper.update_site_user_statistics_site_name(
                    name, old_name)
                self.dbhelper.update_site_seed_info_site_name(name, old_name)
                self.dbhelper.update_site_statistics_site_name(name, old_name)

        else:
            ret = self.dbhelper.insert_config_site(name=name,
                                                   site_pri=site_pri,
                                                   rssurl=rssurl,
                                                   signurl=signurl,
                                                   cookie=cookie,
                                                   note=note,
                                                   rss_uses=rss_uses)
        # 生效站点配置
        Sites().init_config()
        # 初始化刷流任务
        BrushTask().init_config()
        return {"code": ret}

    @staticmethod
    def __get_site(data):
        """
        查询单个站点信息
        """
        tid = data.get("id")
        site_free = False
        site_2xfree = False
        site_hr = False
        if tid:
            ret = Sites().get_sites(siteid=tid)
            if ret.get("rssurl"):
                site_attr = Sites().get_grapsite_conf(ret.get("rssurl"))
                if site_attr.get("FREE"):
                    site_free = True
                if site_attr.get("2XFREE"):
                    site_2xfree = True
                if site_attr.get("HR"):
                    site_hr = True
        else:
            ret = []
        return {"code": 0, "site": ret, "site_free": site_free, "site_2xfree": site_2xfree, "site_hr": site_hr}

    @staticmethod
    def __get_brush_site_capabilities(data):
        """返回刷流页面所需能力，不暴露 Cookie、RSS URL 等站点配置。"""
        tid = data.get("id") if isinstance(data, dict) else None
        site_free = False
        site_2xfree = False
        site_hr = False
        if tid:
            site = Sites().get_sites(siteid=tid) or {}
            rss_url = site.get("rssurl")
            if rss_url:
                site_attr = Sites().get_grapsite_conf(rss_url) or {}
                site_free = bool(site_attr.get("FREE"))
                site_2xfree = bool(site_attr.get("2XFREE"))
                site_hr = bool(site_attr.get("HR"))
        return {
            "code": 0,
            "site_free": site_free,
            "site_2xfree": site_2xfree,
            "site_hr": site_hr,
        }

    @staticmethod
    def __get_sites(data):
        """
        查询多个站点信息
        """
        rss = True if data.get("rss") else False
        brush = True if data.get("brush") else False
        signin = True if data.get("signin") else False
        statistic = True if data.get("statistic") else False
        basic = True if data.get("basic") else False
        if basic:
            sites = Sites().get_site_dict(rss=rss,
                                          brush=brush,
                                          signin=signin,
                                          statistic=statistic)
        else:
            sites = Sites().get_sites(rss=rss,
                                      brush=brush,
                                      signin=signin,
                                      statistic=statistic)
            desensitized_sites = []
            for site in sites:
                site_copy = dict(site)
                if site_copy.get("cookie"):
                    site_copy["cookie"] = "******"
                if site_copy.get("apikey"):
                    site_copy["apikey"] = "******"
                desensitized_sites.append(site_copy)
            sites = desensitized_sites
        return {"code": 0, "sites": sites}

    def __del_site(self, data):
        """
        删除单个站点信息
        """
        tid = data.get("id")
        if tid:
            ret = self.dbhelper.delete_config_site(tid)
            self.dbhelper.delete_site_signin_history(tid)
            Sites().init_config()
            BrushTask().init_config()
            return {"code": ret}
        else:
            return {"code": 0}

    def __restart(self, data):
        """
        重启
        """
        # 退出主进程
        self.restart_server()
        return {"code": 0}

    @staticmethod
    def __logout(data):
        """
        注销
        """
        logout_user()
        return {"code": 0}

    def __update_config(self, data):
        """
        更新配置信息
        """
        cfg = copy.deepcopy(Config().get_config())
        cfgs = dict(data).items()
        # 仅测试不保存
        config_test = False
        # 修改配置
        try:
            for key, value in cfgs:
                if key == "test" and value:
                    config_test = True
                    continue
                # 生效配置
                cfg = self.set_config_value(cfg, key, value)
        except ValueError as error:
            return {"code": 1, "msg": str(error)}

        # 保存配置
        if not config_test:
            Config().save_config(cfg)

        return {"code": 0}

    def __media_info(self, data):
        """
        查询媒体信息
        """
        mediaid = data.get("id")
        mtype = data.get("type")
        title = data.get("title")
        year = data.get("year")
        seasons = []
        link_url = ""
        vote_average = 0
        poster_path = ""
        release_date = ""
        overview = ""
        # 类型
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.TV

        if mediaid:
            media = WebUtils.get_mediainfo_from_id(
                mtype=media_type, mediaid=mediaid)
        else:
            media = Media().get_media_info(
                title=f"{title} {year}", mtype=media_type)
        if not media or not media.tmdb_info:
            return {
                "code": 1,
                "retmsg": "无法查询到TMDB信息",
                "type_str": media_type.value
            }
        if not mediaid:
            mediaid = media.tmdb_id
        link_url = media.get_detail_url()
        overview = media.overview
        poster_path = media.get_poster_image()
        title = media.title
        vote_average = round(float(media.vote_average or 0), 1)
        year = media.year
        if media_type != MediaType.MOVIE:
            release_date = media.tmdb_info.get('first_air_date')
            seasons = [{
                "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                "num": season.get("season_number")} for season in
                Media().get_tmdb_tv_seasons(tv_info=media.tmdb_info)]
        else:
            release_date = media.tmdb_info.get('release_date')

        return {
            "code": 0,
            "type": mtype,
            "type_str": media_type.value,
            "title": title,
            "vote_average": vote_average,
            "poster_path": poster_path,
            "release_date": release_date,
            "year": year,
            "overview": overview,
            "link_url": link_url,
            "tmdbid": mediaid,
            "seasons": seasons
        }

    @staticmethod
    def __test_connection(data):
        """
        测试连通性
        """
        ALLOWED_TESTS = {
            "qbittorrent": Qbittorrent,
            "transmission": Transmission,
        }
        command = data.get("command")
        ret = None
        if command:
            try:
                module_obj = None
                commands = command if isinstance(command, list) else [command]
                for cmd_str in commands:
                    client_type = ALLOWED_TESTS.get(cmd_str)
                    if not client_type:
                        ret = None
                        break
                    module_obj = client_type()
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
                    ret = module_obj.get_status()
                # 重载配置
                Config().init_config()
                if module_obj:
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
            except Exception as e:
                ret = None
                ExceptionUtils.exception_traceback(e)
            return {"code": 0 if ret else 1}
        return {"code": 0}

    def __user_manager(self, data):
        """
        用户管理
        """
        if not isinstance(data, dict):
            return {"code": 1, "success": False, "message": "请求参数错误"}
        oper = str(data.get("oper") or "").strip().lower()
        name = str(data.get("name") or "").strip()
        if oper not in {"add", "del"}:
            return {"code": 1, "success": False, "message": "不支持的用户操作"}
        if not name or len(name) > 64:
            return {"code": 1, "success": False, "message": "用户名不能为空且不能超过 64 个字符"}

        if oper == "add":
            raw_password = data.get("password")
            if not isinstance(raw_password, str) or not 8 <= len(raw_password) <= 128:
                return {"code": 1, "success": False, "message": "密码长度必须为 8 至 128 个字符"}
            if name == (Config().get_config("app") or {}).get("login_user") \
                    or self.dbhelper.is_user_exists(name):
                return {"code": 1, "success": False, "message": "用户已存在"}
            pris = data.get("pris")
            if isinstance(pris, str):
                pris = [permission.strip() for permission in pris.split(",")]
            if not isinstance(pris, list) or not pris \
                    or any(permission not in ACTIVE_USER_PERMISSIONS for permission in pris):
                return {"code": 1, "success": False, "message": "包含已下线或未知权限"}
            normalized_permissions = list(dict.fromkeys(pris))
            password_hash = generate_password_hash(raw_password)
            ret = self.dbhelper.insert_user(name, password_hash, ",".join(normalized_permissions))
        else:
            if name == (Config().get_config("app") or {}).get("login_user"):
                return {"code": 1, "success": False, "message": "不能删除管理员用户"}
            ret = self.dbhelper.delete_user(name)

        if ret:
            return {"code": 0, "success": True}
        return {"code": 1, "success": False, "message": "用户不存在或操作失败"}

    @staticmethod
    def get_system_message(lst_time):
        messages = MessageCenter().get_system_messages(lst_time=lst_time)
        if messages:
            lst_time = messages[0].get("time")
        return {
            "code": 0,
            "message": messages,
            "lst_time": lst_time
        }

    def __refresh_message(self, data):
        """
        刷新首页消息中心
        """
        lst_time = data.get("lst_time")
        system_msg = self.get_system_message(lst_time=lst_time)
        messages = system_msg.get("message")
        lst_time = system_msg.get("lst_time")
        message_items = []
        for message in list(reversed(messages)):
            def plain_text(value):
                text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.IGNORECASE)
                return html_lib.unescape(re.sub(r"<[^>]+>", "", text))

            message_items.append({
                "level": str(message.get("level") or "INFO"),
                "title": plain_text(message.get("title")),
                "content": plain_text(message.get("content")),
                "time": str(message.get("time") or ""),
            })
        return {"code": 0, "message": message_items, "lst_time": lst_time}

    @staticmethod
    def __delete_tmdb_cache(data):
        """
        删除tmdb缓存
        """
        if MetaHelper().delete_meta_data(data.get("cache_key")):
            MetaHelper().save_meta_data()
        return {"code": 0}

    @staticmethod
    def __modify_tmdb_cache(data):
        """
        修改TMDB缓存的标题
        """
        if MetaHelper().modify_meta_data(data.get("key"), data.get("title")):
            MetaHelper().save_meta_data(force=True)
        return {"code": 0}

    def __add_brushtask(self, data):
        """
        新增刷流任务
        """
        # 输入值
        brushtask_id = data.get("brushtask_id")
        brushtask_name = data.get("brushtask_name")
        brushtask_site = data.get("brushtask_site")
        brushtask_interval = data.get("brushtask_interval")
        brushtask_downloader = data.get("brushtask_downloader")
        brushtask_totalsize = data.get("brushtask_totalsize")
        brushtask_state = data.get("brushtask_state")
        brushtask_sendmessage = 'Y' if data.get(
            "brushtask_sendmessage") else 'N'
        brushtask_forceupload = 'Y' if data.get(
            "brushtask_forceupload") else 'N'
        brushtask_free = data.get("brushtask_free")
        brushtask_hr = data.get("brushtask_hr")
        brushtask_torrent_size = data.get("brushtask_torrent_size")
        brushtask_include = data.get("brushtask_include")
        brushtask_exclude = data.get("brushtask_exclude")
        brushtask_dlcount = data.get("brushtask_dlcount")
        brushtask_peercount = data.get("brushtask_peercount")
        brushtask_seedtime = data.get("brushtask_seedtime")
        brushtask_seedratio = data.get("brushtask_seedratio")
        brushtask_seedsize = data.get("brushtask_seedsize")
        brushtask_dltime = data.get("brushtask_dltime")
        brushtask_avg_upspeed = data.get("brushtask_avg_upspeed")
        brushtask_iatime = data.get("brushtask_iatime")
        brushtask_pubdate = data.get("brushtask_pubdate")
        brushtask_upspeed = data.get("brushtask_upspeed")
        brushtask_downspeed = data.get("brushtask_downspeed")
        # 选种规则
        rss_rule = {
            "free": brushtask_free,
            "hr": brushtask_hr,
            "size": brushtask_torrent_size,
            "include": brushtask_include,
            "exclude": brushtask_exclude,
            "dlcount": brushtask_dlcount,
            "peercount": brushtask_peercount,
            "pubdate": brushtask_pubdate,
            "upspeed": brushtask_upspeed,
            "downspeed": brushtask_downspeed
        }
        # 删除规则
        remove_rule = {
            "time": brushtask_seedtime,
            "ratio": brushtask_seedratio,
            "uploadsize": brushtask_seedsize,
            "dltime": brushtask_dltime,
            "avg_upspeed": brushtask_avg_upspeed,
            "iatime": brushtask_iatime
        }
        # 添加记录
        item = {
            "name": brushtask_name,
            "site": brushtask_site,
            "free": brushtask_free,
            "interval": brushtask_interval,
            "downloader": brushtask_downloader,
            "seed_size": brushtask_totalsize,
            "state": brushtask_state,
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "sendmessage": brushtask_sendmessage,
            "forceupload": brushtask_forceupload
        }
        self.dbhelper.insert_brushtask(brushtask_id, item)

        # 重新初始化任务
        BrushTask().init_config()
        return {"code": 0}

    def __del_brushtask(self, data):
        """
        删除刷流任务
        """
        brush_id = data.get("id")
        if brush_id:
            self.dbhelper.delete_brushtask(brush_id)
            # 重新初始化任务
            BrushTask().init_config()
            return {"code": 0}
        return {"code": 1}

    def __brushtask_detail(self, data):
        """
        查询刷流任务详情
        """
        brush_id = data.get("id")
        brushtask = self.dbhelper.get_brushtasks(brush_id)
        if not brushtask:
            return {"code": 1, "task": {}}
        site_info = Sites().get_sites(siteid=brushtask.site)
        try:
            rss_rule = parse_brush_rule(brushtask.rss_rule)
            remove_rule = parse_brush_rule(brushtask.remove_rule)
        except ValueError as error:
            return {"code": 1, "msg": str(error), "task": {}}
        task = {
            "id": brushtask.id,
            "name": brushtask.name,
            "site": brushtask.site,
            "interval": brushtask.inteval,
            "state": brushtask.state,
            "downloader": brushtask.downloader,
            "free": brushtask.freeleech,
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "seed_size": brushtask.seed_size,
            "download_count": brushtask.download_count,
            "remove_count": brushtask.remove_count,
            "download_size": StringUtils.str_filesize(brushtask.download_size),
            "upload_size": StringUtils.str_filesize(brushtask.upload_size),
            "lst_mod_date": brushtask.lst_mod_date,
            "site_url": StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl")),
            "sendmessage": brushtask.sendmessage,
            "forceupload": brushtask.forceupload
        }
        return {"code": 0, "task": task}

    def __add_downloader(self, data):
        """
        添加自定义下载器
        """
        test = data.get("test")
        dl_id = data.get("id")
        dl_name = data.get("name")
        dl_type = data.get("type")
        if dl_type not in {"qbittorrent", "transmission"}:
            return {"code": 1, "msg": "不支持的下载器类型"}
        password = data.get("password")
        if dl_id and not password:
            existing = self.dbhelper.get_user_downloaders(dl_id)
            if existing:
                password = existing.password
        if test:
            # 测试
            if dl_type == "qbittorrent":
                downloader = Qbittorrent(
                    config={
                        "qbhost": data.get("host"),
                        "qbport": data.get("port"),
                        "qbusername": data.get("username"),
                        "qbpassword": password
                    })
            else:
                downloader = Transmission(
                    config={
                        "trhost": data.get("host"),
                        "trport": data.get("port"),
                        "trusername": data.get("username"),
                        "trpassword": password
                    })
            if downloader.get_status():
                return {"code": 0}
            else:
                return {"code": 1}
        else:
            # 保存
            self.dbhelper.update_user_downloader(
                did=dl_id,
                name=dl_name,
                dtype=dl_type,
                user_config={
                    "host": data.get("host"),
                    "port": data.get("port"),
                    "username": data.get("username"),
                    "password": password,
                    "save_dir": data.get("save_dir")
                },
                note=None)
            BrushTask().init_config()
            return {"code": 0}

    def __delete_downloader(self, data):
        """
        删除自定义下载器
        """
        dl_id = data.get("id")
        if dl_id:
            self.dbhelper.delete_user_downloader(dl_id)
            BrushTask().init_config()
        return {"code": 0}

    def __get_downloader(self, data):
        """
        查询自定义下载器
        """
        dl_id = data.get("id")
        if dl_id:
            info = self.dbhelper.get_user_downloaders(dl_id)
            if info:
                return {"code": 0, "info": sanitize_downloader(info.as_dict())}
        return {"code": 1}

    def __name_test(self, data):
        """
        名称识别测试
        """
        name = data.get("name")
        if not name:
            return {"code": -1}
        media_info = Media().get_media_info(title=name)
        if not media_info:
            return {"code": 0, "data": {"name": "无法识别"}}
        return {"code": 0, "data": self.mediainfo_dict(media_info)}

    @staticmethod
    def mediainfo_dict(media_info):
        if not media_info:
            return {}
        tmdb_id = media_info.tmdb_id
        tmdb_link = media_info.get_detail_url()
        tmdb_S_E_link = ""
        if tmdb_id:
            if media_info.get_season_string():
                tmdb_S_E_link = "%s/season/%s" % (tmdb_link,
                                                  media_info.get_season_seq())
                if media_info.get_episode_string():
                    tmdb_S_E_link = "%s/episode/%s" % (
                        tmdb_S_E_link, media_info.get_episode_seq())
        return {
            "type": media_info.type.value if media_info.type else "",
            "name": media_info.get_name(),
            "title": media_info.title,
            "year": media_info.year,
            "season_episode": media_info.get_season_episode_string(),
            "part": media_info.part,
            "tmdbid": tmdb_id,
            "tmdblink": tmdb_link,
            "tmdb_S_E_link": tmdb_S_E_link,
            "category": media_info.category,
            "restype": media_info.resource_type,
            "effect": media_info.resource_effect,
            "pix": media_info.resource_pix,
            "team": media_info.resource_team,
            "video_codec": media_info.video_encode,
            "audio_codec": media_info.audio_encode,
            "org_string": media_info.org_string
        }

    @staticmethod
    def __net_test(data):
        target = str(data or "").strip().lower().rstrip(".")
        if target not in {item.lower().rstrip(".") for item in ModuleConf.NETTEST_TARGETS}:
            return {"res": False, "time": "0 毫秒", "msg": "不支持的网络测试目标"}
        if target == "image.tmdb.org":
            target = target + "/t/p/w500/wwemzKWzjKYJFfCeiB57q3r4Bcm.png"
        target = "https://" + target
        start_time = datetime.datetime.now()
        if target.find("themoviedb") != -1 \
                or target.find("telegram") != -1 \
                or target.find("fanart") != -1 \
                or target.find("tmdb") != -1:
            res = RequestUtils(proxies=Config().get_proxies(),
                               timeout=5).get_res(target, allow_redirects=False)
        else:
            res = RequestUtils(timeout=5).get_res(target, allow_redirects=False)
        elapsed_ms = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
        if not res:
            return {"res": False, "time": "%s 毫秒" % elapsed_ms}
        elif res.ok:
            return {"res": True, "time": "%s 毫秒" % elapsed_ms}
        else:
            return {"res": False, "time": "%s 毫秒" % elapsed_ms}

    @staticmethod
    def __get_site_activity(data):
        """
        查询site活动[上传，下载，魔力值]
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return {"code": 1, "msg": "查询参数错误"}

        resp = {"code": 0}

        resp.update(
            {"dataset": SiteUserInfo().get_pt_site_activity_history(data["name"])})
        return resp

    @staticmethod
    def __get_site_history(data):
        """
        查询site 历史[上传，下载]
        :param data: {"days":累计时间}
        :return:
        """
        if not data or "days" not in data or not isinstance(data["days"], int):
            return {"code": 1, "msg": "查询参数错误"}

        resp = {"code": 0}
        _, _, site, upload, download = SiteUserInfo().get_pt_site_statistics_history(data["days"] + 1)

        # 调整为dataset组织数据
        dataset = [["site", "upload", "download"]]
        dataset.extend([[site, upload, download]
                       for site, upload, download in zip(site, upload, download)])
        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def __get_site_seeding_info(data):
        """
        查询site 做种分布信息 大小，做种数
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return {"code": 1, "msg": "查询参数错误"}

        resp = {"code": 0}

        seeding_info = SiteUserInfo().get_pt_site_seeding_info(
            data["name"]).get("seeding_info", [])
        # 调整为dataset组织数据
        dataset = [["seeders", "size"]]
        dataset.extend(seeding_info)

        resp.update({"dataset": dataset})
        return resp

    def get_recommend(self, data):
        Type = data.get("type")
        SubType = data.get("subtype")
        CurrentPage = data.get("page")
        if not CurrentPage:
            CurrentPage = 1
        else:
            CurrentPage = int(CurrentPage)

        res_list = []
        if Type in ['MOV', 'TV']:
            if SubType == "hm":
                # TMDB热门电影
                res_list = Media().get_tmdb_hot_movies(CurrentPage)
            elif SubType == "ht":
                # TMDB热门电视剧
                res_list = Media().get_tmdb_hot_tvs(CurrentPage)
            elif SubType == "nm":
                # TMDB最新电影
                res_list = Media().get_tmdb_new_movies(CurrentPage)
            elif SubType == "nt":
                # TMDB最新电视剧
                res_list = Media().get_tmdb_new_tvs(CurrentPage)
            elif SubType == "dbom":
                # 豆瓣正在上映
                res_list = DouBan().get_douban_online_movie(CurrentPage)
            elif SubType == "dbhm":
                # 豆瓣热门电影
                res_list = DouBan().get_douban_hot_movie(CurrentPage)
            elif SubType == "dbht":
                # 豆瓣热门电视剧
                res_list = DouBan().get_douban_hot_tv(CurrentPage)
            elif SubType == "dbdh":
                # 豆瓣热门动画
                res_list = DouBan().get_douban_hot_anime(CurrentPage)
            elif SubType == "dbnm":
                # 豆瓣最新电影
                res_list = DouBan().get_douban_new_movie(CurrentPage)
            elif SubType == "dbtop":
                # 豆瓣TOP250电影
                res_list = DouBan().get_douban_top250_movie(CurrentPage)
            elif SubType == "dbzy":
                # 豆瓣最新电视剧
                res_list = DouBan().get_douban_hot_show(CurrentPage)
            elif SubType == "dbct":
                # 华语口碑剧集榜
                res_list = DouBan().get_douban_chinese_weekly_tv(CurrentPage)
            elif SubType == "dbgt":
                # 全球口碑剧集榜
                res_list = DouBan().get_douban_weekly_tv_global(CurrentPage)
            elif SubType == "sim":
                # 相似推荐
                TmdbId = data.get("tmdbid")
                res_list = self.__media_similar({
                    "tmdbid": TmdbId,
                    "page": CurrentPage,
                    "type": Type
                }).get("data")
            elif SubType == "more":
                # 更多推荐
                TmdbId = data.get("tmdbid")
                res_list = self.__media_recommendations({
                    "tmdbid": TmdbId,
                    "page": CurrentPage,
                    "type": Type
                }).get("data")
            elif SubType == "person":
                # 人物作品
                PersonId = data.get("personid")
                res_list = self.__person_medias({
                    "personid": PersonId,
                    "type": Type,
                    "page": CurrentPage
                }).get("data")
            elif SubType == "bangumi":
                # Bangumi每日放送
                Week = data.get("week")
                res_list = Bangumi().get_bangumi_calendar(page=CurrentPage, week=Week)
        elif Type == "SEARCH":
            # 搜索词条
            Keyword = data.get("keyword")
            Source = data.get("source")
            medias = WebUtils.search_media_infos(
                keyword=Keyword, source=Source, page=CurrentPage)
            res_list = [media.to_dict() for media in medias]
        elif Type == "DOWNLOADED":
            # 近期下载
            res_list = self.get_downloaded({
                "page": CurrentPage
            }).get("Items")
        elif Type == "TRENDING":
            # TMDB流行趋势
            res_list = Media().get_tmdb_trending_all_week(page=CurrentPage)
        elif Type == "DISCOVER":
            # TMDB发现
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            # 过滤参数 with_genres with_original_language
            params = data.get("params") or {}
            res_list = Media().get_tmdb_discover(mtype=mtype, page=CurrentPage, params=params)
        elif Type == "DOUBANTAG":
            # 豆瓣发现
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            # 参数
            params = data.get("params") or {}
            # 排序
            sort = params.get("sort") or "T"
            # 选中的分类
            tags = params.get("tags") or ""
            # 过滤参数
            res_list = DouBan().get_douban_disover(mtype=mtype,
                                                   sort=sort,
                                                   tags=tags,
                                                   page=CurrentPage)

        return {"code": 0, "Items": res_list}

    def get_downloaded(self, data):
        page = data.get("page")
        Items = self.dbhelper.get_download_history(page=page)
        if Items:
            return {"code": 0, "Items": [{
                'id': item.tmdbid,
                'orgid': item.tmdbid,
                'tmdbid': item.tmdbid,
                'title': item.title,
                'type': 'MOV' if item.type == "电影" else "TV",
                'media_type': item.type,
                'year': item.year,
                'vote': item.vote,
                'image': item.poster,
                'overview': item.torrent,
                "date": item.date,
                "site": item.site
            } for item in Items]}
        else:
            return {"code": 0, "Items": []}

    @staticmethod
    def parse_brush_rule_string(rules: dict):
        if not rules:
            return ""
        if not isinstance(rules, dict):
            return ""

        def escaped(value):
            return html_lib.escape(str(value or ""), quote=True)

        def split_rule(value):
            parts = str(value or "").split("#", 1)
            return parts if len(parts) == 2 else ["", ""]

        rule_filter_string = {"gt": ">", "lt": "<", "bw": ""}
        rule_htmls = []
        if rules.get("size"):
            sizes = split_rule(rules.get("size"))
            if sizes[0]:
                if sizes[1]:
                    sizes[1] = sizes[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="种子大小">种子大小: %s %sGB</span>'
                    % (rule_filter_string.get(sizes[0]), escaped(sizes[1])))
        if rules.get("pubdate"):
            pubdates = split_rule(rules.get("pubdate"))
            if pubdates[0]:
                if pubdates[1]:
                    pubdates[1] = pubdates[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="发布时间">发布时间: %s %s小时</span>'
                    % (rule_filter_string.get(pubdates[0]), escaped(pubdates[1])))
        if rules.get("upspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="上传限速">上传限速: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("upspeed")) * 1024))
        if rules.get("downspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="下载限速">下载限速: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("downspeed")) * 1024))
        if rules.get("include"):
            rule_htmls.append(
                '<span class="badge badge-outline text-green me-1 mb-1 text-wrap text-start" title="包含规则">包含: %s</span>'
                % escaped(rules.get("include")))
        if rules.get("hr"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1" title="排除HR">排除: HR</span>')
        if rules.get("exclude"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1 text-wrap text-start" title="排除规则">排除: %s</span>'
                % escaped(rules.get("exclude")))
        if rules.get("dlcount"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="同时下载数量限制">同时下载: %s</span>'
                              % escaped(rules.get("dlcount")))
        if rules.get("peercount"):
            peer_counts = None
            peer_count_parts = split_rule(rules.get("peercount"))
            if len(peer_count_parts) == 2 and peer_count_parts[1]:
                peer_count_parts[1] = peer_count_parts[1].replace(",", "-")
                peer_counts = peer_count_parts
            if peer_counts:
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="当前做种人数限制">做种人数: %s %s</span>'
                    % (rule_filter_string.get(peer_counts[0]), escaped(peer_counts[1])))
        if rules.get("time"):
            times = split_rule(rules.get("time"))
            if times[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="做种时间">做种时间: %s %s小时</span>'
                    % (rule_filter_string.get(times[0]), escaped(times[1])))
        if rules.get("ratio"):
            ratios = split_rule(rules.get("ratio"))
            if ratios[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="分享率">分享率: %s %s</span>'
                    % (rule_filter_string.get(ratios[0]), escaped(ratios[1])))
        if rules.get("uploadsize"):
            uploadsizes = split_rule(rules.get("uploadsize"))
            if uploadsizes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="上传量">上传量: %s %sGB</span>'
                    % (rule_filter_string.get(uploadsizes[0]), escaped(uploadsizes[1])))
        if rules.get("dltime"):
            dltimes = split_rule(rules.get("dltime"))
            if dltimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="下载耗时">下载耗时: %s %s小时</span>'
                    % (rule_filter_string.get(dltimes[0]), escaped(dltimes[1])))
        if rules.get("avg_upspeed"):
            avg_upspeeds = split_rule(rules.get("avg_upspeed"))
            if avg_upspeeds[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="平均上传速度">平均上传速度: %s %sKB/S</span>'
                    % (rule_filter_string.get(avg_upspeeds[0]), escaped(avg_upspeeds[1])))
        if rules.get("iatime"):
            iatimes = split_rule(rules.get("iatime"))
            if iatimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="未活动时间">未活动时间: %s %s小时</span>'
                    % (rule_filter_string.get(iatimes[0]), escaped(iatimes[1])))

        return "<br>".join(rule_htmls)

    @staticmethod
    def __clear_tmdb_cache(data):
        """
        清空TMDB缓存
        """
        try:
            MetaHelper().clear_meta_data()
            os.remove(MetaHelper().get_meta_data_path())
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {"code": 0, "msg": str(e)}
        return {"code": 0}

    @staticmethod
    def __check_site_attr(data):
        """
        检查站点标识
        """
        site_attr = Sites().get_grapsite_conf(data.get("url"))
        site_free = site_2xfree = site_hr = False
        if site_attr.get("FREE"):
            site_free = True
        if site_attr.get("2XFREE"):
            site_2xfree = True
        if site_attr.get("HR"):
            site_hr = True
        return {"code": 0, "site_free": site_free, "site_2xfree": site_2xfree, "site_hr": site_hr}

    @staticmethod
    def __refresh_process(data):
        """
        刷新进度条
        """
        process_type = data.get("type")
        if process_type == "sitecookie" and has_request_context() \
                and not request_has_system_settings():
            return {"code": 403, "value": 0, "text": "权限不足"}
        detail = ProgressHelper().get_process(process_type)
        if detail:
            return {"code": 0, "value": detail.get("value"), "text": detail.get("text")}
        else:
            return {"code": 1, "value": 0, "text": "正在处理..."}

    @staticmethod
    def __get_tvseason_list(data):
        """
        获取剧集季列表
        """
        tmdbid = data.get("tmdbid")
        title = data.get("title")
        if title:
            title_season = MetaInfo(title=title).begin_season
        else:
            title_season = None
        if not str(tmdbid).isdigit():
            media_info = WebUtils.get_mediainfo_from_id(mtype=MediaType.TV,
                                                        mediaid=tmdbid)
            season_infos = Media().get_tmdb_tv_seasons(media_info.tmdb_info)
        else:
            season_infos = Media().get_tmdb_tv_seasons_byid(tmdbid=tmdbid)
        if title_season:
            seasons = [
                {
                    "text": "第%s季" % title_season,
                    "num": title_season
                }
            ]
        else:
            seasons = [
                {
                    "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                    "num": season.get("season_number")
                }
                for season in season_infos
            ]
        return {"code": 0, "seasons": seasons}

    @staticmethod
    def __run_brushtask(data):
        BrushTask().check_task_rss(data.get("id"))
        return {"code": 0}

    @staticmethod
    def __list_site_resources(data):
        resources = Indexer().list_builtin_resources(index_id=data.get("id"),
                                                     page=data.get("page"),
                                                     keyword=data.get("keyword"))
        if not resources:
            return {"code": 1, "msg": "获取站点资源出现错误，无法连接到站点！"}
        else:
            return {"code": 0, "data": resources}

    @staticmethod
    def __get_categories(data):
        if data.get("type") == "电影":
            categories = Category().get_movie_categorys()
        elif data.get("type") == "电视剧":
            categories = Category().get_tv_categorys()
        else:
            categories = Category().get_anime_categorys()
        return {"code": 0, "category": list(categories), "id": data.get("id"), "value": data.get("value")}

    def get_search_result(self, data=None):
        """
        查询所有搜索结果
        """
        SearchResults = {}
        res = self.dbhelper.get_search_results()
        total = len(res)
        for item in res:
            # 质量(来源、效果)、分辨率
            if item.res_type:
                try:
                    res_mix = json.loads(item.res_type)
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
                respix = res_mix.get("respix") or ""
                video_encode = res_mix.get("video_encode") or ""
                restype = res_mix.get("restype") or ""
                reseffect = res_mix.get("reseffect") or ""
            else:
                restype = ""
                respix = ""
                reseffect = ""
                video_encode = ""
            # 分组标识 (来源，分辨率)
            group_key = re.sub(r"[-.\s@|]", "", f"{respix}_{restype}").lower()
            # 分组信息
            group_info = {
                "respix": respix,
                "restype": restype,
            }
            # 种子唯一标识 （大小，质量(来源、效果)，制作组组成）
            unique_key = re.sub(r"[-.\s@|]", "",
                                f"{respix}_{restype}_{video_encode}_{reseffect}_{item.size}_{item.otherinfo}").lower()
            # 标识信息
            unique_info = {
                "video_encode": video_encode,
                "size": item.size,
                "reseffect": reseffect,
                "releasegroup": item.otherinfo
            }
            # 结果
            title_string = f"{item.title}"
            if item.year:
                title_string = f"{title_string} ({item.year})"
            # 电视剧季集标识
            mtype = item.type or ""
            SE_key = item.es_string if item.es_string and mtype != "MOV" else "MOV"
            media_type = {"MOV": "电影", "TV": "电视剧", "ANI": "动漫"}.get(mtype)
            # 种子信息
            torrent_item = {
                "id": item.id,
                "seeders": item.seeders,
                "enclosure": item.enclosure,
                "site": item.site,
                "torrent_name": item.torrent_name,
                "description": item.description,
                "pageurl": item.pageurl,
                "uploadvalue": item.upload_volume_factor,
                "downloadvalue": item.download_volume_factor,
                "size": item.size,
                "respix": respix,
                "restype": restype,
                "reseffect": reseffect,
                "releasegroup": item.otherinfo,
                "video_encode": video_encode
            }
            # 促销
            free_item = {
                "value": f"{item.upload_volume_factor} {item.download_volume_factor}",
                "name": MetaBase.get_free_string(item.upload_volume_factor, item.download_volume_factor)
            }
            # 季
            filter_season = SE_key.split()[0] if SE_key and SE_key not in [
                "MOV", "TV"] else None
            # 合并搜索结果
            if SearchResults.get(title_string):
                # 种子列表
                result_item = SearchResults[title_string]
                torrent_dict = SearchResults[title_string].get("torrent_dict")
                SE_dict = torrent_dict.get(SE_key)
                if SE_dict:
                    group = SE_dict.get(group_key)
                    if group:
                        unique = group.get("group_torrents").get(unique_key)
                        if unique:
                            unique["torrent_list"].append(torrent_item)
                            group["group_total"] += 1
                        else:
                            group["group_total"] += 1
                            group.get("group_torrents")[unique_key] = {
                                "unique_info": unique_info,
                                "torrent_list": [torrent_item]
                            }
                    else:
                        SE_dict[group_key] = {
                            "group_info": group_info,
                            "group_total": 1,
                            "group_torrents": {
                                unique_key: {
                                    "unique_info": unique_info,
                                    "torrent_list": [torrent_item]
                                }
                            }
                        }
                else:
                    torrent_dict[SE_key] = {
                        group_key: {
                            "group_info": group_info,
                            "group_total": 1,
                            "group_torrents": {
                                unique_key: {
                                    "unique_info": unique_info,
                                    "torrent_list": [torrent_item]
                                }
                            }
                        }
                    }
                # 过滤条件
                torrent_filter = dict(result_item.get("filter"))
                if free_item not in torrent_filter.get("free"):
                    torrent_filter["free"].append(free_item)
                if item.site not in torrent_filter.get("site"):
                    torrent_filter["site"].append(item.site)
                if video_encode \
                        and video_encode not in torrent_filter.get("video"):
                    torrent_filter["video"].append(video_encode)
                if filter_season \
                        and filter_season not in torrent_filter.get("season"):
                    torrent_filter["season"].append(filter_season)
            else:
                # 是否已存在
                if item.tmdbid:
                    exist_flag = False
                else:
                    exist_flag = False
                SearchResults[title_string] = {
                    "key": item.id,
                    "title": item.title,
                    "year": item.year,
                    "type_key": mtype,
                    "image": item.image,
                    "type": media_type,
                    "vote": item.vote,
                    "tmdbid": item.tmdbid,
                    "backdrop": item.image,
                    "poster": item.poster,
                    "overview": item.overview,
                    "exist": exist_flag,
                    "torrent_dict": {
                        SE_key: {
                            group_key: {
                                "group_info": group_info,
                                "group_total": 1,
                                "group_torrents": {
                                    unique_key: {
                                        "unique_info": unique_info,
                                        "torrent_list": [torrent_item]
                                    }
                                }
                            }
                        }
                    },
                    "filter": {
                        "site": [item.site],
                        "free": [free_item],
                        "video": [video_encode] if video_encode else [],
                        "season": [filter_season] if filter_season else []
                    }
                }

        # 提升整季的顺序到顶层
        def se_sort(k):
            k = re.sub(r" +|(?<=s\d)\D*?(?=e)|(?<=s\d\d)\D*?(?=e)",
                       " ", k[0], flags=re.I).split()
            return (k[0], k[1]) if len(k) > 1 else ("Z" + k[0], "ZZZ")

        # 开始排序季集顺序
        for title, item in SearchResults.items():
            # 排序筛选器 季
            item["filter"]["season"].sort(reverse=True)
            # 排序种子列 集
            item["torrent_dict"] = sorted(item["torrent_dict"].items(),
                                          key=se_sort,
                                          reverse=True)
        return {"code": 0, "total": total, "result": SearchResults}

    @staticmethod
    def search_media_infos(data):
        """
        根据关键字搜索相似词条
        """
        SearchWord = data.get("keyword")
        if not SearchWord:
            return []
        SearchSourceType = data.get("searchtype")
        medias = WebUtils.search_media_infos(keyword=SearchWord,
                                             source=SearchSourceType)

        return {"code": 0, "result": [media.to_dict() for media in medias]}




    @staticmethod
    def get_downloading(data=None):
        """
        查询正在下载的任务
        """
        torrents = Downloader().get_downloading_progress()
        MediaHander = Media()
        for torrent in torrents:
            # 识别
            name = torrent.get("name")
            media_info = MediaHander.get_media_info(title=name)
            if not media_info:
                torrent.update({
                    "title": name,
                    "image": ""
                })
                continue
            if not media_info.tmdb_info:
                year = media_info.year
                if year:
                    title = "%s (%s) %s" % (media_info.get_name(),
                                            year, media_info.get_season_episode_string())
                else:
                    title = "%s %s" % (media_info.get_name(),
                                       media_info.get_season_episode_string())
            else:
                title = "%s %s" % (media_info.get_title_string(
                ), media_info.get_season_episode_string())
            poster_path = media_info.get_poster_image()
            torrent.update({
                "title": title,
                "image": poster_path or ""
            })
        return {"code": 0, "result": torrents}

    def get_users(self, data=None):
        """
        查询所有用户
        """
        user_list = self.dbhelper.get_users()
        Users = []
        for user in user_list:
            pris = str(user.pris).split(",")
            Users.append({"id": user.id, "name": user.name, "pris": pris})
        return {"code": 0, "result": Users}

    @staticmethod
    def __test_site(data):
        """
        测试站点连通性
        """
        flag, msg, times = Sites().test_connection(data.get("id"))
        code = 0 if flag else -1
        return {"code": code, "msg": msg, "time": times}

    @staticmethod
    def __get_download_setting(data):
        sid = data.get("sid")
        if sid:
            download_setting = Downloader().get_download_setting(sid=sid)
        else:
            download_setting = list(
                Downloader().get_download_setting().values())
        return {"code": 0, "data": download_setting}

    def __update_download_setting(self, data):
        sid = data.get("sid")
        name = data.get("name")
        category = data.get("category")
        tags = data.get("tags")
        content_layout = data.get("content_layout")
        is_paused = data.get("is_paused")
        upload_limit = data.get("upload_limit")
        download_limit = data.get("download_limit")
        ratio_limit = data.get("ratio_limit")
        seeding_time_limit = data.get("seeding_time_limit")
        downloader = data.get("downloader")
        if downloader not in {"", None, DownloaderType.QB.value, DownloaderType.TR.value}:
            return {"code": 1, "msg": "不支持的下载器类型"}
        self.dbhelper.update_download_setting(sid=sid,
                                              name=name,
                                              category=category,
                                              tags=tags,
                                              content_layout=content_layout,
                                              is_paused=is_paused,
                                              upload_limit=upload_limit or 0,
                                              download_limit=download_limit or 0,
                                              ratio_limit=ratio_limit or 0,
                                              seeding_time_limit=seeding_time_limit or 0,
                                              downloader=downloader)
        Downloader().init_config()
        return {"code": 0}

    def __delete_download_setting(self, data):
        sid = data.get("sid")
        self.dbhelper.delete_download_setting(sid=sid)
        Downloader().init_config()
        return {"code": 0}

    def __update_message_client(self, data):
        """
        更新消息设置
        """
        name = data.get("name")
        cid = data.get("cid")
        ctype = data.get("type")
        config = data.get("config")
        switchs = data.get("switchs")
        switchs = switchs if isinstance(switchs, list) else []
        supported_switches = set(ModuleConf.MESSAGE_CONF.get("switch", {}))
        if any(
            not isinstance(switch, str) or switch not in supported_switches
            for switch in switchs
        ):
            return {"code": 1, "msg": "消息渠道包含已下线或未知的通知类型"}
        interactive = data.get("interactive")
        enabled = data.get("enabled")
        existing = Message().get_message_client_info(cid=cid) if cid else None
        try:
            config_dict = prepare_message_client_config(
                ctype,
                config,
                (existing or {}).get("config"),
            )
        except ValueError as error:
            return {"code": 1, "msg": str(error)}
        saved = self.dbhelper.insert_message_client(
            name=name,
            ctype=ctype,
            config=json.dumps(config_dict, ensure_ascii=False),
            switchs=switchs,
            interactive=interactive,
            enabled=enabled,
            cid=cid,
        )
        if not saved:
            return {"code": 1, "msg": "消息渠道保存失败"}
        Message().init_config()
        return {"code": 0}

    def __delete_message_client(self, data):
        """
        删除消息设置
        """
        if self.dbhelper.delete_message_client(cid=data.get("cid")):
            Message().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    def __check_message_client(self, data):
        """
        维护消息设置
        """
        flag = data.get("flag")
        cid = data.get("cid")
        ctype = data.get("type")
        checked = data.get("checked")
        if flag == "interactive":
            # TG/WX只能开启一个交互
            if checked:
                self.dbhelper.check_message_client(interactive=0, ctype=ctype)
            self.dbhelper.check_message_client(cid=cid,
                                               interactive=1 if checked else 0)
            Message().init_config()
            return {"code": 0}
        elif flag == "enable":
            self.dbhelper.check_message_client(cid=cid,
                                               enabled=1 if checked else 0)
            Message().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __get_message_client(data):
        """
        获取消息设置
        """
        cid = data.get("cid")
        detail = Message().get_message_client_info(cid=cid)
        if not detail:
            return {"code": 1, "msg": "消息渠道不存在", "detail": {}}
        return {"code": 0, "detail": sanitize_message_client(detail)}

    @staticmethod
    def __test_message_client(data):
        """
        测试消息设置
        """
        ctype = data.get("type")
        cid = data.get("cid")
        existing = Message().get_message_client_info(cid=cid) if cid else None
        try:
            config = prepare_message_client_config(
                ctype,
                data.get("config"),
                (existing or {}).get("config"),
            )
        except ValueError as error:
            return {"code": 1, "msg": str(error)}
        res = Message().get_status(ctype=ctype, config=config)
        if res:
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __get_indexers(data=None):
        """
        获取索引器
        """
        return {"code": 0, "indexers": Indexer().get_indexer_dict()}

    @staticmethod
    def __get_download_dirs(data):
        """
        获取下载目录
        """
        sid = data.get("sid")
        site = data.get("site")
        if not sid and site:
            sid = Sites().get_site_download_setting(site_name=site)
        dirs = Downloader().get_download_dirs(setting=sid)
        return {"code": 0, "paths": dirs}

    @staticmethod
    def __update_sites_cookie_ua(data):
        """
        更新所有站点的Cookie和UA
        """
        siteid = data.get("siteid")
        username = data.get("username")
        password = data.get("password")
        twostepcode = data.get("two_step_code")
        ocrflag = data.get("ocrflag")
        # 保存设置
        SystemConfig().set_system_config(key="CookieUserInfo",
                                         value={
                                             "username": username,
                                             "password": password,
                                             "two_step_code": twostepcode
                                         })
        retcode, messages = SiteCookie().update_sites_cookie_ua(siteid=siteid,
                                                                username=username,
                                                                password=password,
                                                                twostepcode=twostepcode,
                                                                ocrflag=ocrflag)
        if retcode == 0:
            Sites().init_config()
        return {"code": retcode, "messages": messages}

    @staticmethod
    def __set_site_captcha_code(data):
        """
        设置站点验证码
        """
        code = data.get("code")
        value = data.get("value")
        SiteCookie().set_code(code=code, value=value)
        return {"code": 0}

    @staticmethod
    def __update_torrent_remove_task(data):
        """
        更新自动删种任务
        """
        flag, msg = TorrentRemover().update_torrent_remove_task(data=data)
        if not flag:
            return {"code": 1, "msg": msg}
        else:
            TorrentRemover().init_config()
            return {"code": 0}

    @staticmethod
    def __get_torrent_remove_task(data=None):
        """
        获取自动删种任务
        """
        if data:
            tid = data.get("tid")
        else:
            tid = None
        return {"code": 0, "detail": TorrentRemover().get_torrent_remove_tasks(taskid=tid)}

    @staticmethod
    def __delete_torrent_remove_task(data):
        """
        删除自动删种任务
        """
        tid = data.get("tid")
        flag = TorrentRemover().delete_torrent_remove_task(taskid=tid)
        if flag:
            TorrentRemover().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def __get_remove_torrents(data):
        """
        获取满足自动删种任务的种子
        """
        tid = data.get("tid")
        flag, torrents = TorrentRemover().get_remove_torrents(taskid=tid)
        if not flag or not torrents:
            return {"code": 1, "msg": "未获取到符合处理条件种子"}
        return {"code": 0, "data": torrents}

    @staticmethod
    def __auto_remove_torrents(data):
        """
        执行自动删种任务
        """
        tid = data.get("tid")
        TorrentRemover().auto_remove_torrents(taskids=tid)
        return {"code": 0}

    @staticmethod
    def __get_site_favicon(data):
        """
        获取站点图标
        """
        sitename = data.get("name")
        return {"code": 0, "icon": Sites().get_site_favicon(site_name=sitename)}

    def __list_brushtask_torrents(self, data):
        """
        获取刷流任务的种子明细
        """
        results = self.dbhelper.get_brushtask_torrents(brush_id=data.get("id"),
                                                       active=False)
        if not results:
            return {"code": 1, "msg": "未下载种子或未获取到种子明细"}
        return {"code": 0, "data": [item.as_dict() for item in results]}

    @staticmethod
    def __set_system_config(data):
        """
        设置系统设置（数据库）
        """
        key = data.get("key")
        value = data.get("value")
        if not key or not value:
            return {"code": 1}
        try:
            if SystemConfig().set_system_config(key=key, value=value):
                return {"code": 0}
            return {"code": 1}
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {"code": 1}

    @staticmethod
    def get_site_user_statistics(data):
        """
        获取站点用户统计信息
        """
        sites = data.get("sites")
        encoding = data.get("encoding") or "RAW"
        sort_by = data.get("sort_by")
        sort_on = data.get("sort_on")
        site_hash = data.get("site_hash")
        statistics = SiteUserInfo().get_site_user_statistics(sites=sites, encoding=encoding)
        if sort_by and sort_on in ["asc", "desc"]:
            if sort_on == "asc":
                statistics.sort(key=lambda x: x[sort_by])
            else:
                statistics.sort(key=lambda x: x[sort_by], reverse=True)
        if site_hash == "Y":
            for item in statistics:
                item["site_hash"] = StringUtils.md5_hash(item.get("site"))
        return {"code": 0, "data": statistics}

    @staticmethod
    def send_custom_message(data):
        """
        发送自定义消息
        """
        title = data.get("title")
        text = data.get("text") or ""
        image = data.get("image") or ""
        Message().send_custom_message(title=title, text=text, image=image)
        return {"code": 0}

    def __cookiecloud_sync(self, data):
        """
        CookieCloud数据同步
        """
        try:
            server = validate_site_config_url(
                data.get("server"), "CookieCloud服务器地址"
            ).rstrip('/')
        except ValueError as error:
            return {"code": 1, "msg": str(error)}
        key = data.get("key")
        password = data.get("password")
        # 保存设置
        SystemConfig().set_system_config(key="CookieCloud",
                                         value={
                                             "server": server,
                                             "key": key,
                                             "password": password
                                         })
        # 同步数据
        contents, retmsg = CookieCloudHelper(server=server,
                                             key=key,
                                             password=password).download_data()
        if not contents:
            return {"code": 1, "msg": retmsg}
        success_count = 0
        for domain, content_list in contents.items():
            if domain.startswith('.'):
                domain = domain[1:]
            cookie_str = ""
            for content in content_list:
                cookie_str += content.get("name") + \
                    "=" + content.get("value") + ";"
            if not cookie_str:
                continue
            site_info = Sites().get_sites(siteurl=domain)
            if not site_info:
                continue
            self.dbhelper.update_site_cookie_ua(tid=site_info.get("id"),
                                                cookie=cookie_str)
            success_count += 1
        if success_count:
            # 重载站点信息
            Sites().init_config()
            return {"code": 0, "msg": f"成功更新 {success_count} 个站点的Cookie数据"}
        return {"code": 0, "msg": "同步完成，但未更新任何站点的Cookie！"}

    @staticmethod
    def media_detail(data):
        """
        获取媒体详情
        """
        # TMDBID 或 DB:豆瓣ID
        tmdbid = data.get("tmdbid")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定媒体ID"}
        media_info = WebUtils.get_mediainfo_from_id(
            mtype=mtype, mediaid=tmdbid)
        # 检查TMDB信息
        if not media_info or not media_info.tmdb_info:
            return {
                "code": 1,
                "msg": "无法查询到TMDB信息"
            }
        MediaHander = Media()
        return {
            "code": 0,
            "data": {
                "tmdbid": media_info.tmdb_id,
                "douban_id": media_info.douban_id,
                "background": MediaHander.get_tmdb_backdrops(tmdbinfo=media_info.tmdb_info),
                "image": media_info.get_poster_image(),
                "vote": media_info.vote_average,
                "year": media_info.year,
                "title": media_info.title,
                "genres": MediaHander.get_tmdb_genres_names(tmdbinfo=media_info.tmdb_info),
                "overview": media_info.overview,
                "runtime": StringUtils.str_timehours(media_info.runtime),
                "fact": MediaHander.get_tmdb_factinfo(media_info),
                "crews": MediaHander.get_tmdb_crews(tmdbinfo=media_info.tmdb_info, nums=6),
                "actors": MediaHander.get_tmdb_cats(mtype=mtype, tmdbid=media_info.tmdb_id),
                "link": media_info.get_detail_url(),
                "douban_link": media_info.get_douban_detail_url()
            }
        }

    @staticmethod
    def __media_similar(data):
        """
        查询TMDB相似媒体
        """
        tmdbid = data.get("tmdbid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定TMDBID"}
        if mtype == MediaType.MOVIE:
            result = Media().get_movie_similar(tmdbid=tmdbid, page=page)
        else:
            result = Media().get_tv_similar(tmdbid=tmdbid, page=page)
        return {"code": 0, "data": result}

    @staticmethod
    def __media_recommendations(data):
        """
        查询TMDB同类推荐媒体
        """
        tmdbid = data.get("tmdbid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定TMDBID"}
        if mtype == MediaType.MOVIE:
            result = Media().get_movie_recommendations(tmdbid=tmdbid, page=page)
        else:
            result = Media().get_tv_recommendations(tmdbid=tmdbid, page=page)
        return {"code": 0, "data": result}

    @staticmethod
    def __media_person(data):
        """
        查询TMDB媒体所有演员
        """
        tmdbid = data.get("tmdbid")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定TMDBID"}
        return {"code": 0, "data": Media().get_tmdb_cats(tmdbid=tmdbid,
                                                         mtype=mtype)}

    @staticmethod
    def __person_medias(data):
        """
        查询演员参演作品
        """
        personid = data.get("personid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not personid:
            return {"code": 1, "msg": "未指定演员ID"}
        return {"code": 0, "data": Media().get_person_medias(personid=personid,
                                                             mtype=mtype,
                                                             page=page)}

    @staticmethod
    def __save_user_script(data):
        """
        保存用户自定义脚本
        """
        script = data.get("javascript") or ""
        css = data.get("css") or ""
        SystemConfig().set_system_config(key="CustomScript",
                                         value={
                                             "css": css,
                                             "javascript": script
                                         })
        return {"code": 0, "msg": "保存成功"}
