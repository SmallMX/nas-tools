"""
主数据库操作模块 (app.db.main_db)
================================

封装对 user.db 的所有数据库操作，提供 MainDb (DAO) 和 DbPersist (事务装饰器)。

技术选型：SQLAlchemy ORM + SQLite + scoped_session (线程安全) + QueuePool (连接池)
"""

import json
import os
import threading
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

from app.db.models import Base
from app.retired_features import ACTIVE_USER_PERMISSIONS
from app.utils import ExceptionUtils
from config import Config

# 线程锁，保护 init_db() 中的建表操作
lock = threading.Lock()

# SQLAlchemy 引擎 —— 管理数据库连接池
# 关键参数：
#   check_same_thread=False  允许跨线程共享 SQLite 连接
#   pool_pre_ping=True       取连接前检测存活性
#   pool_size=50             常驻连接数
#   pool_recycle=600         连接 10 分钟后自动回收
#   max_overflow=0           不允许超出 pool_size 的额外连接
_CONFIG_PATH = Config().get_config_path()
_DB_PATH = os.path.join(_CONFIG_PATH, 'user.db')

# 已下线功能遗留的表和系统配置。名称固定在代码中，供启动迁移和备份清理复用。
RETIRED_DATABASE_TABLES = frozenset({
    "config_rss_parser",
    "config_sync_paths",
    "config_user_rss",
    "douban_medias",
    "rss_history",
    "rss_movies",
    "rss_torrents",
    "rss_tv_episodes",
    "rss_tvs",
    "sync_history",
    "transfer_blacklist",
    "transfer_history",
    "transfer_unknown",
    "userrss_task_history",
})
RETIRED_DATABASE_COLUMNS = {
    "config_site": frozenset({"exclude", "size"}),
    "site_brush_task": frozenset({"transfer"}),
}
RETIRED_DATABASE_FILES = frozenset({"media.db", "media.db-shm", "media.db-wal"})
RETIRED_SYSTEM_CONFIG_KEYS = frozenset({"SpeedLimit"})
SUPPORTED_MESSAGE_SWITCHES = frozenset({
    "download_start",
    "download_fail",
    "site_signin",
    "site_message",
    "brushtask_added",
    "brushtask_remove",
    "custom_message",
})


def _secure_database_files():
    for database_file in (_DB_PATH, f"{_DB_PATH}-wal", f"{_DB_PATH}-shm"):
        if os.path.exists(database_file):
            os.chmod(database_file, 0o600)


_Engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_size=50,
    pool_recycle=60 * 10,
    max_overflow=0
)


@event.listens_for(_Engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _connection_record):
    """为每个池连接设置一致的并发与持久化参数。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        _secure_database_files()
    finally:
        cursor.close()

# scoped_session：线程安全的 Session 工厂
# 同一线程内多次调用 _Session() 返回同一个 Session（线程本地单例）
# expire_on_commit=False：commit 后不过期对象属性，避免额外查询
_Session = scoped_session(sessionmaker(bind=_Engine,
                                       autoflush=True,
                                       autocommit=False,
                                       expire_on_commit=False))


def remove_db_session():
    """关闭并移除当前线程持有的 scoped Session。"""
    _Session.remove()


class MainDb:
    """
    主数据库访问对象 (DAO)，封装对 user.db 的增删改查和事务控制。

    本类是无状态轻量对象，底层 Session 由 scoped_session 管理。
    写操作后需显式调用 commit()，或使用 DbPersist 装饰器自动管理。
    """

    @property
    def session(self):
        """获取当前线程的数据库 Session（线程本地单例）。"""
        return _Session()

    @staticmethod
    def init_db():
        """
        初始化数据库表结构 (CREATE TABLE IF NOT EXISTS)。
        使用线程锁保护，确保并发安全。
        """
        with lock:
            Base.metadata.create_all(_Engine)
            with _Engine.begin() as connection:
                for table, retired_columns in RETIRED_DATABASE_COLUMNS.items():
                    existing_columns = {
                        str(row[1]).lower(): str(row[1])
                        for row in connection.exec_driver_sql(f'PRAGMA table_info("{table}")')
                    }
                    for column in sorted(retired_columns.intersection(existing_columns)):
                        actual_column = existing_columns[column]
                        connection.exec_driver_sql(
                            f'ALTER TABLE "{table}" DROP COLUMN "{actual_column}"'
                        )
                for table in sorted(RETIRED_DATABASE_TABLES):
                    connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
                for key in sorted(RETIRED_SYSTEM_CONFIG_KEYS):
                    connection.exec_driver_sql(
                        'DELETE FROM system_dict WHERE type = ? AND "key" = ?',
                        ("SystemConfig", key),
                    )
                connection.exec_driver_sql(
                    'UPDATE download_setting SET downloader = NULL '
                    "WHERE TRIM(COALESCE(downloader, '')) <> '' "
                    'AND downloader NOT IN (?, ?)',
                    ("Qbittorrent", "Transmission"),
                )
                connection.exec_driver_sql(
                    'DELETE FROM message_client WHERE type IS NULL OR type != ?',
                    ("telegram",),
                )
                message_rows = connection.exec_driver_sql(
                    'SELECT id, switchs FROM message_client WHERE type = ?',
                    ("telegram",),
                ).fetchall()
                for client_id, switchs in message_rows:
                    try:
                        parsed_switches = json.loads(switchs) if switchs else []
                    except (TypeError, ValueError):
                        parsed_switches = []
                    if not isinstance(parsed_switches, list):
                        parsed_switches = []
                    filtered_switches = [
                        switch
                        for switch in parsed_switches
                        if isinstance(switch, str)
                        and switch in SUPPORTED_MESSAGE_SWITCHES
                    ]
                    connection.exec_driver_sql(
                        'UPDATE message_client SET switchs = ? WHERE id = ?',
                        (json.dumps(filtered_switches, ensure_ascii=False), client_id),
                    )
                site_rows = connection.exec_driver_sql(
                    'SELECT id, note FROM config_site WHERE note IS NOT NULL AND note != ?',
                    ("",),
                ).fetchall()
                for site_id, note in site_rows:
                    try:
                        site_note = json.loads(note)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(site_note, dict):
                        continue
                    retired_note_keys = {"rule", "subtitle"}.intersection(site_note)
                    if not retired_note_keys:
                        continue
                    for key in retired_note_keys:
                        site_note.pop(key)
                    connection.exec_driver_sql(
                        'UPDATE config_site SET note = ? WHERE id = ?',
                        (json.dumps(site_note, ensure_ascii=False), site_id),
                    )
                user_rows = connection.exec_driver_sql(
                    'SELECT id, pris FROM config_users WHERE pris IS NOT NULL'
                ).fetchall()
                for user_id, permissions in user_rows:
                    filtered_permissions = [
                        permission.strip()
                        for permission in str(permissions).split(",")
                        if permission.strip()
                        and permission.strip() in ACTIVE_USER_PERMISSIONS
                    ]
                    normalized_permissions = ",".join(filtered_permissions)
                    if normalized_permissions != permissions:
                        connection.exec_driver_sql(
                            'UPDATE config_users SET pris = ? WHERE id = ?',
                            (normalized_permissions, user_id),
                        )
            for filename in sorted(RETIRED_DATABASE_FILES):
                retired_path = os.path.join(_CONFIG_PATH, filename)
                if os.path.isfile(retired_path):
                    os.unlink(retired_path)
            _secure_database_files()

    def insert(self, data):
        """插入一条或多条 ORM 对象（列表时用 add_all，单个用 add）。"""
        if isinstance(data, list):
            self.session.add_all(data)
        else:
            self.session.add(data)

    def query(self, *obj):
        """创建查询对象，返回 SQLAlchemy Query 可链式调用 filter/all 等。"""
        return self.session.query(*obj)

    def flush(self):
        """将待处理变更刷新到数据库但不提交事务（用于获取自增 ID 等场景）。"""
        self.session.flush()

    def commit(self):
        """提交当前事务，持久化所有变更。"""
        self.session.commit()

    def rollback(self):
        """回滚当前事务，撤销未提交的变更。"""
        self.session.rollback()


class DbPersist(object):
    """
    数据库持久化装饰器 —— 自动管理事务提交/回滚。

    使用示例::

        @DbPersist(db=MainDb())
        def add_record(self, title):
            self.db.insert(SomeModel(title=title))
            # 无需手动 commit

    返回值约定：成功返回 True（或函数原始非 None 返回值），异常返回 False。
    """

    def __init__(self, db):
        """
        :param db: MainDb 实例，用于调用 commit/rollback
        """
        self.db = db

    def __call__(self, f):
        """
        将装饰器应用到目标函数，包装为自动事务管理。
        """
        def persist(*args, **kwargs):
            try:
                ret = f(*args, **kwargs)
                self.db.commit()
                return True if ret is None else ret
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                self.db.rollback()
                return False

        return persist
