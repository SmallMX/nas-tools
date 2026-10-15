"""动作和文件路由共用的输入校验，兼容导出保留在 web.action。"""

import ast
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from app.conf import ModuleConf
from app.downloader import Downloader
from app.sites import Sites


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
