"""站点自动签到工具配置读取边界。"""

from collections.abc import Mapping

from config import Config


def get_site_signin_config():
    """返回结构有效的站点自动签到工具配置。"""
    tools_config = Config().get_config("tools")
    if not isinstance(tools_config, Mapping):
        return {}
    signin_config = tools_config.get("site_signin")
    return dict(signin_config) if isinstance(signin_config, Mapping) else {}
