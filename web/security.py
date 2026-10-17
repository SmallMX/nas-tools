import copy
import datetime
import hmac
from functools import wraps

import jwt
from flask import g, has_request_context, request

from app.utils import TokenCache
from config import Config


def extract_auth_token(auth_header):
    if not auth_header:
        return None
    parts = str(auth_header).strip().split()
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def require_auth(func):
    """校验 API Key。"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = extract_auth_token(request.headers.get("Authorization"))
        api_key = str((Config().get_config("security") or {}).get("api_key") or "")
        if auth and api_key:
            if hmac.compare_digest(auth, api_key):
                return func(*args, **kwargs)
        return {
            "code": 401,
            "success": False,
            "message": "安全认证未通过，请检查ApiKey"
        }, 401

    return wrapper


def generate_access_token(username: str, algorithm: str = "HS256", exp: float = 2):
    """生成访问令牌。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    exp_datetime = now + datetime.timedelta(hours=exp)
    access_payload = {
        "exp": exp_datetime,
        "iat": now,
        "username": username,
    }
    return jwt.encode(
        access_payload,
        Config().get_config("security").get("api_key"),
        algorithm=algorithm,
    )


def __decode_auth_token(token: str, algorithms="HS256"):
    """解密令牌并返回解析状态与载荷。"""
    key = Config().get_config("security").get("api_key")
    try:
        payload = jwt.decode(token, key=key, algorithms=algorithms)
    except Exception:
        return False, {}
    return True, payload


def identify(auth_header: str):
    """返回令牌是否有效及其用户名。"""
    flag = False
    if auth_header:
        flag, payload = __decode_auth_token(auth_header)
        if payload:
            return flag, payload.get("username") or ""
    return flag, ""


def request_is_admin():
    """验证当前请求的管理员身份，API Token 优先于浏览器会话。"""
    from flask_login import current_user
    from web.backend.user import User

    if not has_request_context():
        return False
    api_username = getattr(g, "api_username", None)
    if api_username:
        user = User().get_user(api_username)
    elif current_user.is_authenticated:
        user = User().get_user(current_user.username)
    else:
        user = None
    return bool(user and user.id == 0)


def login_required(func):
    """验证 API Token 是否属于当前配置的管理员。"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        def auth_failed():
            return {
                "code": 401,
                "success": False,
                "message": "安全认证未通过，请检查Token"
            }, 401

        token = extract_auth_token(request.headers.get("Authorization", default=None))
        if not token:
            return auth_failed()
        latest_token = TokenCache.get(token)
        if not latest_token:
            return auth_failed()
        flag, username = identify(latest_token)
        if not flag or not username:
            return {
                "code": 401,
                "success": False,
                "message": "安全认证已过期，请重新登录"
            }, 401

        from web.backend.user import User

        user = User().get_user(username)
        if not user or user.id != 0:
            return auth_failed()

        g.api_username = username
        return func(*args, **kwargs)

    return wrapper


def desensitize_config_dict(cfg):
    """对配置项中的密码、密钥和 Cookie 做脱敏处理。"""
    cfg_copy = copy.deepcopy(cfg)

    def mask_key(data, key_path):
        current = data
        for key in key_path[:-1]:
            if current and key in current:
                current = current[key]
            else:
                return
        last_key = key_path[-1]
        if current and last_key in current and current[last_key]:
            current[last_key] = "******"

    keys_to_mask = [
        ["app", "login_password"],
        ["app", "rmt_tmdbkey"],
        ["app", "fanart_api_key"],
        ["app", "douban_api_key"],
        ["app", "douban_api_secret"],
        ["security", "api_key"],
        ["security", "flask_secret_key"],
        ["security", "telegram_webhook_secret"],
        ["qbittorrent", "qbpassword"],
        ["transmission", "trpassword"],
    ]
    for key_path in keys_to_mask:
        mask_key(cfg_copy, key_path)
    return cfg_copy


def sanitize_brush_task(task):
    """构造不含站点 Cookie、RSS passkey 和 UA 的 Web DTO。"""
    if not isinstance(task, dict):
        return {}
    allowed_fields = {
        "id", "name", "site", "site_id", "interval", "state",
        "downloader", "downloader_name", "free",
        "rss_rule", "remove_rule", "seed_size", "sendmessage",
        "forceupload", "download_count", "remove_count", "download_size",
        "upload_size", "lst_mod_date", "site_url",
    }
    return {key: value for key, value in task.items() if key in allowed_fields}


def sanitize_downloader(downloader):
    """构造不含下载器密码的 Web DTO。"""
    if not isinstance(downloader, dict):
        return {}
    allowed_fields = {"id", "name", "type", "host", "port", "username", "save_dir"}
    return {key: value for key, value in downloader.items() if key in allowed_fields}


def sanitize_message_client(client):
    """返回可供 Web 展示的消息渠道 DTO，并遮盖长期凭据。"""
    if not isinstance(client, dict):
        return {}
    sanitized = copy.deepcopy(client)
    config = sanitized.get("config")
    if isinstance(config, dict):
        for key, value in config.items():
            normalized_key = str(key).lower()
            if value and any(marker in normalized_key for marker in (
                    "token", "password", "secret", "api_key", "cookie")):
                config[key] = "******"
    return sanitized
