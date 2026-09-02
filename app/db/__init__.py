"""
数据库模块 (app.db)
==================

本模块是 NAS-Tools 的**数据持久化层**，负责管理应用运行所需的 SQLite 数据库：

1. **user.db** (主数据库)
   - 由 `MainDb` 管理，存储系统配置、站点信息和下载历史等核心业务数据。
   - 表结构定义在 `models.py` 中继承自 `Base` 的所有 ORM 模型。
   - 表结构由当前版本的 SQLAlchemy ORM 模型直接创建。

应用启动时调用 `init_db()` 创建当前模型中尚不存在的数据表，并清理已下线功能遗留的数据结构。
"""

import log
from .main_db import MainDb
from .main_db import DbPersist
from .main_db import remove_db_session


def init_db():
    """
    初始化数据库表结构。

    调用 MainDb 的 init_db() 方法，通过 SQLAlchemy 的
    ``Base.metadata.create_all()`` 在 user.db 中创建所有 ORM 模型定义的表。
    如果表已存在则跳过，并幂等清理已下线功能遗留的表和系统配置。
    """
    log.console('开始初始化数据库...')
    MainDb().init_db()
    log.console('数据库初始化完成')
