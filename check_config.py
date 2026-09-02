import ipaddress
import os
import secrets
import string
import tempfile

from werkzeug.security import generate_password_hash
from app.retired_features import (
    ACTIVE_CONFIG_SECTION_KEYS,
    RETIRED_CONFIG_SECTIONS,
    RETIRED_NESTED_CONFIG_KEYS,
)
from config import Config


def is_public_bind_address(publish_address):
    """判断 Docker 宿主机发布地址是否超出本机回环范围。"""
    normalized_address = str(publish_address or "").strip().strip("[]")
    try:
        return not ipaddress.ip_address(normalized_address).is_loopback
    except ValueError:
        return normalized_address.lower() != "localhost"


def _write_initial_credentials(credentials):
    """将仅首启需要的明文凭据写入私有文件，避免进入容器日志。"""
    config_dir = Config().get_config_path()
    credentials_path = os.path.join(config_dir, "initial-credentials.txt")
    file_descriptor, temp_path = tempfile.mkstemp(
        prefix=".initial-credentials-",
        suffix=".tmp",
        dir=config_dir,
        text=True,
    )
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, mode="w", encoding="utf-8") as credentials_file:
            credentials_file.write("NAS-Tools 初始凭据\n")
            if credentials.get("username"):
                credentials_file.write(f"用户名: {credentials['username']}\n")
            if credentials.get("password"):
                credentials_file.write(f"密码: {credentials['password']}\n")
            if credentials.get("api_key"):
                credentials_file.write(f"API Key: {credentials['api_key']}\n")
            credentials_file.write("首次登录并保存凭据后，请删除此文件。\n")
            credentials_file.flush()
            os.fsync(credentials_file.fileno())
        os.replace(temp_path, credentials_path)
        temp_path = None
        os.chmod(credentials_path, 0o600)
        Config()._fsync_directory(config_dir)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    print(f"【安全提示】初始管理员凭据已写入：{credentials_path}")


def check_config():
    """
    检查配置文件，如有错误进行日志输出
    """
    # 检查日志输出
    if Config().get_config('app'):
        logtype = Config().get_config('app').get('logtype')
        if logtype:
            print("日志输出类型为：%s" % logtype)
        if logtype == "server":
            logserver = Config().get_config('app').get('logserver')
            if not logserver:
                print("【Config】日志中心地址未配置，无法正常输出日志")
            else:
                print("日志将上送到服务器：%s" % logserver)
        elif logtype == "file":
            logpath = Config().get_config('app').get('logpath')
            if not logpath:
                print("【Config】日志文件路径未配置，无法正常输出日志")
            else:
                print("日志将写入文件：%s" % logpath)

        # 检查登录用户和密码
        login_user = Config().get_config('app').get('login_user')
        login_password = Config().get_config('app').get('login_password')
        if not login_user or not login_password:
            print("WEB管理用户或密码配置不完整，请检查初始化结果")
        else:
            print("WEB管理页面用户：%s" % str(login_user))

        # Docker-only 部署由反向代理终止 TLS，应用容器始终提供 HTTP。
        print("应用容器使用 http://IP:3000 提供服务")

        rmt_tmdbkey = Config().get_config('app').get('rmt_tmdbkey')
        if not rmt_tmdbkey:
            print("TMDB API Key未配置，媒体识别、搜索下载及自动选择下载目录等功能将无法正常运行！")
        rmt_match_mode = Config().get_config('app').get('rmt_match_mode')
        if rmt_match_mode:
            rmt_match_mode = rmt_match_mode.upper()
        else:
            rmt_match_mode = "NORMAL"
        if rmt_match_mode == "STRICT":
            print("TMDB匹配模式：严格模式")
        else:
            print("TMDB匹配模式：正常模式")
    else:
        print("配置文件格式错误，找不到app配置项！")

    # 检查媒体分类配置
    if Config().get_config('media'):
        category = Config().get_config('media').get('category')
        if not category:
            print("未配置分类策略")
    else:
        print("配置文件格式错误，找不到media配置项！")

    # 检查站点配置
    if Config().get_config('pt'):
        pt_client = Config().get_config('pt').get('pt_client')
        print("下载软件设置为：%s" % pt_client)

        search_auto = Config().get_config('pt').get('search_auto')
        if search_auto:
            print("远程渠道搜索已开启自动择优下载")

    else:
        print("配置文件格式错误，找不到pt配置项！")

    tools_config = Config().get_config('tools')
    if isinstance(tools_config, dict):
        site_signin_config = tools_config.get('site_signin')
    else:
        site_signin_config = {}
    site_signin_config = site_signin_config if isinstance(site_signin_config, dict) else {}
    if not site_signin_config.get('cron'):
        print("站点自动签到时间未配置，站点签到工具已关闭")


def initialize_config():
    """
    初始化当前版本运行所需的缺失配置
    """
    _config = Config().get_config()
    overwrite_config = False
    initial_credentials = {}

    # 清理已下线功能遗留配置，避免旧部署继续携带无效凭据和开关。
    for legacy_section in RETIRED_CONFIG_SECTIONS:
        if legacy_section in _config:
            _config.pop(legacy_section)
            overwrite_config = True

    pt_config = _config.get("pt")
    if isinstance(pt_config, dict):
        if pt_config.get("pt_client") not in ("qbittorrent", "transmission"):
            pt_config["pt_client"] = "qbittorrent"
            overwrite_config = True

    for section, legacy_key in RETIRED_NESTED_CONFIG_KEYS:
        section_config = _config.get(section)
        if isinstance(section_config, dict) and legacy_key in section_config:
            section_config.pop(legacy_key)
            overwrite_config = True

    for section, allowed_keys in ACTIVE_CONFIG_SECTION_KEYS.items():
        section_config = _config.get(section)
        if not isinstance(section_config, dict):
            continue
        for legacy_key in set(section_config).difference(allowed_keys):
            section_config.pop(legacy_key)
            overwrite_config = True

    if not isinstance(_config.get("app"), dict):
        _config['app'] = {}
        overwrite_config = True
    if not _config['app'].get("login_user"):
        _config['app']['login_user'] = 'admin'
        overwrite_config = True

    # 密码初始化
    login_password = _config['app'].get("login_password")
    is_default_pw = False
    if not login_password:
        is_default_pw = True

    if is_default_pw:
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for _ in range(16))
        _config['app']['login_password'] = "[hash]%s" % generate_password_hash(new_password)
        initial_credentials['username'] = _config['app']['login_user']
        initial_credentials['password'] = new_password
        overwrite_config = True

    # 实验室配置初始化
    if not _config.get("laboratory"):
        _config['laboratory'] = {
            'search_keyword': False,
            'tmdb_cache_expire': True,
            'search_en_title': True,
            'chrome_browser': False
        }
        overwrite_config = True

    # 安全配置初始化
    if not isinstance(_config.get("security"), dict):
        _config['security'] = {}
        overwrite_config = True

    if not _config['security'].get("telegram_webhook_allow_ip"):
        _config['security']['telegram_webhook_allow_ip'] = {
            'ipv4': '127.0.0.1',
            'ipv6': '::1/128'
        }
        overwrite_config = True

    if not _config['security'].get("telegram_webhook_secret"):
        _config['security']['telegram_webhook_secret'] = secrets.token_urlsafe(32)
        overwrite_config = True

    if not _config['security'].get("flask_secret_key"):
        _config['security']['flask_secret_key'] = secrets.token_urlsafe(48)
        overwrite_config = True

    # API密钥初始化
    api_key = _config.get("security", {}).get("api_key")
    if not api_key:
        alphabet = string.ascii_letters + string.digits
        new_api_key = ''.join(secrets.choice(alphabet) for _ in range(32))
        _config['security']['api_key'] = new_api_key
        initial_credentials['api_key'] = new_api_key
        overwrite_config = True

    # 重写配置文件
    if overwrite_config:
        Config().save_config(_config)
    if initial_credentials:
        _write_initial_credentials(initial_credentials)
