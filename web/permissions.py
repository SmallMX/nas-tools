"""Web 页面、动作和 API 的权限声明。

权限元数据集中维护，避免动作注册表与 RBAC 白名单各自演进后发生漂移。
"""

from collections.abc import Iterable


PermissionRule = str | tuple[str, ...]


PATH_PERMISSIONS: dict[str, PermissionRule] = {
    # 系统设置
    "/basic": "系统设置",
    "/media_setting": "系统设置",
    "/service_setting": "系统设置",
    "/security_setting": "系统设置",
    "/laboratory_setting": "系统设置",
    "/users": "系统设置",
    "/downloader": "系统设置",
    "/download_setting": "系统设置",
    "/notification": "系统设置",
    "/tmdbcache": "系统设置",
    "/backup": "系统设置",
    "/dirlist": "系统设置",
    "/api/v1/service/network/test": "系统设置",
    # 上传接口仅用于手动添加种子文件。
    "/upload": ("系统设置", "资源搜索", "下载管理"),

    # 站点管理
    "/site": "站点管理",
    "/sitelist": "站点管理",
    "/resources": "站点管理",
    "/statistics": "站点管理",
    "/tools/site-signin": "站点管理",

    # 工具入口只展示当前账号有权访问的内置工具。
    "/tools": "*",

    # 搜索与探索
    "/search": "资源搜索",
    "/recommend": "探索",
    "/ranking": "探索",
    "/tmdb_movie": "探索",
    "/tmdb_tv": "探索",
    "/bangumi": "探索",
    "/media_detail": "探索",
    "/discovery_person": "探索",

    # 下载管理
    "/downloading": "下载管理",
    "/downloaded": "下载管理",
    "/torrent_remove": "下载管理",
    "/userdownloader": "系统设置",

    # 服务
    "/service": ("服务", "系统设置"),
    "/brushtask": "服务",
}


CMD_PERMISSIONS: dict[str, PermissionRule] = {
    # 系统设置
    "logging": "系统设置",
    "update_config": "系统设置",
    "test_connection": "系统设置",
    "user_manager": "系统设置",
    "get_categories": "系统设置",
    "delete_tmdb_cache": "系统设置",
    "modify_tmdb_cache": "系统设置",
    "add_downloader": "系统设置",
    "delete_downloader": "系统设置",
    "get_downloader": "系统设置",
    "net_test": "系统设置",
    "clear_tmdb_cache": "系统设置",
    "get_users": "系统设置",
    "get_message_client": "系统设置",
    "update_message_client": "系统设置",
    "delete_message_client": "系统设置",
    "check_message_client": "系统设置",
    "test_message_client": "系统设置",
    "get_download_dirs": ("系统设置", "下载管理"),
    "update_sites_cookie_ua": "系统设置",
    "update_torrent_remove_task": ("系统设置", "下载管理"),
    "get_torrent_remove_task": ("系统设置", "下载管理"),
    "delete_torrent_remove_task": ("系统设置", "下载管理"),
    "get_remove_torrents": ("系统设置", "下载管理"),
    "auto_remove_torrents": ("系统设置", "下载管理"),
    "save_user_script": "系统设置",
    "set_system_config": "系统设置",
    "restart": "系统设置",
    # 站点管理
    "update_site": "站点管理",
    "get_site": "站点管理",
    "get_brush_site_capabilities": "服务",
    "del_site": "站点管理",
    "get_site_favicon": "站点管理",
    "get_site_activity": "站点管理",
    "get_site_history": "站点管理",
    "get_site_seeding_info": "站点管理",
    "get_site_user_statistics": "站点管理",
    "check_site_attr": "站点管理",
    "test_site": "站点管理",
    "get_sites": "站点管理",
    "get_indexers": ("站点管理", "资源搜索"),
    "list_site_resources": "站点管理",
    "set_site_captcha_code": "系统设置",
    "cookiecloud_sync": "系统设置",
    "tool_site_signin_status": "站点管理",
    "tool_site_signin_run": "站点管理",
    "tool_site_signin_config_update": "站点管理",

    # 搜索与探索
    "search": "资源搜索",
    "search_media_infos": "资源搜索",
    "get_search_result": "资源搜索",
    "get_recommend": ("探索", "下载管理"),
    "get_tvseason_list": "探索",
    "media_info": ("探索", "资源搜索"),
    "media_detail": "探索",
    "media_similar": "探索",
    "media_recommendations": "探索",
    "media_person": "探索",
    "person_medias": "探索",

    # 下载管理
    "download": "下载管理",
    "download_link": "下载管理",
    "download_torrent": "下载管理",
    "pt_start": "下载管理",
    "pt_stop": "下载管理",
    "pt_remove": "下载管理",
    "pt_info": "下载管理",
    "get_downloaded": "下载管理",
    "refresh_process": "*",
    "get_downloading": "下载管理",
    "get_download_setting": ("下载管理", "系统设置"),
    "update_download_setting": ("下载管理", "系统设置"),
    "delete_download_setting": ("下载管理", "系统设置"),

    # 服务
    "sch": "服务",
    "add_brushtask": "服务",
    "del_brushtask": "服务",
    "brushtask_detail": "服务",
    "run_brushtask": "服务",
    "list_brushtask_torrents": "服务",
    "name_test": ("服务", "站点管理"),
    "send_custom_message": ("服务", "系统设置"),
    "refresh_message": "系统设置",
    "logout": "*",
}


API_PREFIX_PERMISSIONS: tuple[tuple[str, PermissionRule], ...] = (
    ("/api/v1/config/", "系统设置"),
    ("/api/v1/system/logout", "*"),
    ("/api/v1/system/", "系统设置"),
    ("/api/v1/message/", "系统设置"),
    ("/api/v1/torrentremover/", ("系统设置", "下载管理")),
    ("/api/v1/media/cache/", "系统设置"),
    ("/api/v1/media/category/", "系统设置"),
    ("/api/v1/site/", "站点管理"),
    ("/api/v1/search/", "资源搜索"),
    ("/api/v1/recommend/", "探索"),
    ("/api/v1/media/", "探索"),
    ("/api/v1/download/setting/", ("下载管理", "系统设置")),
    ("/api/v1/download/", "下载管理"),
    ("/api/v1/service/", "服务"),
    ("/api/v1/brushtask/downloader/", "系统设置"),
    ("/api/v1/brushtask/", ("服务", "系统设置")),
)


PUBLIC_PATHS = frozenset({"", "/login", "/logout", "/robots.txt", "/telegram", "/healthz"})


def matches_permission(user_permissions: Iterable[str], rule: PermissionRule | None) -> bool:
    if not rule:
        return False
    if rule == "*":
        return True
    allowed = (rule,) if isinstance(rule, str) else rule
    return bool(set(user_permissions).intersection(allowed))
