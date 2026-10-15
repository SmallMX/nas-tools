import copy
import json

import log
from app.helper import DictHelper
from app.utils.commons import singleton


@singleton
class SystemConfig:

    # 系统设置
    _DEFAULTS = {
        # 默认下载设置
        "DefaultDownloadSetting": None,
        # CookieCloud的设置
        "CookieCloud": {},
        # 自动获取Cookie的用户信息
        "CookieUserInfo": {},
        # 用户自定义CSS/JavsScript
        "CustomScript": {}
    }

    def __init__(self):
        self.systemconfig = copy.deepcopy(self._DEFAULTS)
        self.init_config()

    def init_config(self, key=None):
        """
        缓存系统设置
        """
        keys = [key] if key else self._DEFAULTS
        helper = DictHelper()
        for config_key in keys:
            if config_key not in self._DEFAULTS:
                continue
            default = self._DEFAULTS[config_key]
            value = helper.get("SystemConfig", config_key)
            if value is None or value == "":
                value = copy.deepcopy(default)
            elif isinstance(default, (dict, list)):
                try:
                    value = json.loads(value)
                    if not isinstance(value, type(default)):
                        raise TypeError("配置类型不匹配")
                except (TypeError, ValueError):
                    # 保留数据库原值供排查；日志不输出可能包含凭证的内容。
                    log.warn(f"【Config】系统配置 {config_key} 无法解析或类型不匹配，已使用默认值")
                    value = copy.deepcopy(default)
            self.systemconfig[config_key] = value

    def set_system_config(self, key, value):
        """
        设置系统设置
        """
        if key not in self.systemconfig:
            return False
        if isinstance(value, dict) \
                or isinstance(value, list):
            if value:
                value = json.dumps(value)
            else:
                value = None
        if not DictHelper().set("SystemConfig", key, value):
            return False
        self.init_config(key)
        return True

    def get_system_config(self, key=None):
        """
        获取系统设置
        """
        if not key:
            return self.systemconfig
        return self.systemconfig.get(key)
