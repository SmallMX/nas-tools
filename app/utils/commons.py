# -*- coding: utf-8 -*-
import threading
from functools import wraps

# 线程锁
lock = threading.RLock()

# 全局实例
INSTANCES = {}


# 单例模式注解
def singleton(cls):
    # 创建字典用来保存类的实例对象
    global INSTANCES

    @wraps(cls)
    def _singleton(*args, **kwargs):
        # 先判断这个类有没有对象
        if cls not in INSTANCES:
            with lock:
                if cls not in INSTANCES:
                    INSTANCES[cls] = cls(*args, **kwargs)
                    pass
        # 将实例对象返回
        return INSTANCES[cls]

    return _singleton


def get_singleton_instance(factory):
    """仅获取已经启动的单例，配置刷新不隐式创建后台服务。"""
    with lock:
        return INSTANCES.get(getattr(factory, "__wrapped__", factory))
