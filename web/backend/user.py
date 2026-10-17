from flask_login import UserMixin
from werkzeug.security import check_password_hash

from config import Config


class User(UserMixin):
    """由配置文件定义的唯一管理员账号。"""

    def __init__(self):
        app_config = Config().get_config('app') or {}
        self.id = 0
        self.username = app_config.get('login_user')
        password = app_config.get('login_password') or ""
        self.password_hash = password[6:] if password.startswith('[hash]') else None

    def verify_password(self, password):
        if not self.password_hash or not isinstance(password, str) or not password:
            return False
        return check_password_hash(self.password_hash, password)

    def get(self, user_id):
        """恢复管理员会话；旧普通用户的 Session 不再有效。"""
        if str(user_id) == "0" and self.username and self.password_hash:
            return self
        return None

    def get_user(self, user_name):
        if user_name and user_name == self.username and self.password_hash:
            return self
        return None
