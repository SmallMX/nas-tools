"""已下线功能的配置与权限边界。"""

RETIRED_CONFIG_SECTIONS = frozenset({
    "aria2",
    "client115",
    "emby",
    "jackett",
    "jellyfin",
    "message",
    "pikpak",
    "plex",
    "prowlarr",
    "scraper_nfo",
    "scraper_pic",
    "subtitle",
    "sync",
})

RETIRED_NESTED_CONFIG_KEYS = frozenset({
    ("app", "init_files"),
    ("pt", "pt_check_interval"),
    ("pt", "pt_monitor"),
    ("pt", "rmt_mode"),
    ("pt", "search_indexer"),
    ("pt", "search_no_result_rss"),
    ("pt", "search_rss_interval"),
    ("qbittorrent", "force_upload"),
    ("security", "media_server_webhook_allow_ip"),
    ("security", "synology_webhook_allow_ip"),
})

ACTIVE_CONFIG_SECTION_KEYS = {
    "douban": frozenset({"cookie"}),
    "media": frozenset({"category"}),
}

ACTIVE_USER_PERMISSIONS = (
    "资源搜索",
    "探索",
    "站点管理",
    "下载管理",
    "服务",
    "系统设置",
)


def is_retired_config_path(config_path):
    """判断 Web 配置写入路径是否属于已下线功能。"""
    parts = tuple(
        part.strip().lower() for part in str(config_path or "").split(".")
    )
    if not parts or not parts[0]:
        return False
    if parts[0] in RETIRED_CONFIG_SECTIONS:
        return True
    if len(parts) >= 2 and parts[:2] in RETIRED_NESTED_CONFIG_KEYS:
        return True
    allowed_keys = ACTIVE_CONFIG_SECTION_KEYS.get(parts[0])
    if allowed_keys is not None:
        return len(parts) >= 2 and parts[1] not in allowed_keys
    return False


def sanitize_config_write(config_path, value):
    """拒绝退役路径，并从合法的整段配置更新中剔除退役键。"""
    parts = tuple(
        part.strip().lower() for part in str(config_path or "").split(".")
    )
    if is_retired_config_path(config_path):
        raise ValueError("配置项已下线")

    if parts == ("pt", "pt_client") \
            and value not in ("qbittorrent", "transmission"):
        raise ValueError("不支持的下载器类型")

    if len(parts) != 1:
        return value

    section = parts[0]
    governed_sections = set(ACTIVE_CONFIG_SECTION_KEYS).union(
        retired_section for retired_section, _ in RETIRED_NESTED_CONFIG_KEYS
    )
    if section in governed_sections and not isinstance(value, dict):
        raise ValueError("配置段格式不合法")
    if not isinstance(value, dict):
        return value
    if section not in governed_sections:
        return value

    sanitized = {
        str(key).strip().lower(): item for key, item in value.items()
    }
    for retired_section, retired_key in RETIRED_NESTED_CONFIG_KEYS:
        if retired_section == section:
            sanitized.pop(retired_key, None)

    allowed_keys = ACTIVE_CONFIG_SECTION_KEYS.get(section)
    if allowed_keys is not None:
        sanitized = {
            key: item for key, item in sanitized.items() if key in allowed_keys
        }

    if section == "pt" \
            and "pt_client" in sanitized \
            and sanitized["pt_client"] not in ("qbittorrent", "transmission"):
        raise ValueError("不支持的下载器类型")
    if value and not sanitized:
        raise ValueError("配置段仅包含已下线配置项")
    return sanitized
