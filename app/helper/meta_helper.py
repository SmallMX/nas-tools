import copy
import os
import pickle
import tempfile
import time
from enum import Enum
from threading import Lock, RLock

from app.utils import ExceptionUtils
from app.utils.commons import singleton
from config import Config

lock = RLock()
save_lock = Lock()

CACHE_EXPIRE_TIMESTAMP_STR = "cache_expire_timestamp"
EXPIRE_TIMESTAMP = 7 * 24 * 3600


def _fsync_directory(directory):
    try:
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass


@singleton
class MetaHelper(object):
    """
    {
        "id": '',
        "title": '',
        "year": '',
        "type": MediaType
    }
    """
    _meta_data = {}

    _meta_path = None
    _tmdb_cache_expire = False
    _revision = 0
    _saved_revision = None
    _next_expiry = None

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.reload_runtime_config()
        with save_lock, lock:
            self._meta_path = os.path.join(Config().get_config_path(), 'tmdb.dat')
            self._meta_data = self.__load_meta_data(self._meta_path)
            self._revision = 0
            self._saved_revision = None
            self._next_expiry = None

    def reload_runtime_config(self):
        """刷新过期策略，不覆盖尚未保存的内存媒体缓存。"""
        laboratory = Config().get_config('laboratory') or {}
        with lock:
            enabled = laboratory.get("tmdb_cache_expire", False)
            if enabled != self._tmdb_cache_expire:
                self._tmdb_cache_expire = enabled
                self._revision += 1

    def clear_meta_data(self):
        """
        清空所有TMDB缓存
        """
        with lock:
            if self._meta_data:
                self._meta_data = {}
                self._revision += 1

    def get_meta_data_path(self):
        """
        返回TMDB缓存文件路径
        """
        return self._meta_path

    def get_meta_data_by_key(self, key):
        """
        根据KEY值获取缓存值
        """
        now = int(time.time())
        with lock:
            info: dict = self._meta_data.get(key)
            if info:
                expire = info.get(CACHE_EXPIRE_TIMESTAMP_STR)
                if not expire or now < expire:
                    if expire != now + EXPIRE_TIMESTAMP:
                        info[CACHE_EXPIRE_TIMESTAMP_STR] = now + EXPIRE_TIMESTAMP
                        if str(info.get("id")) != "0":
                            self._revision += 1
                elif expire and self._tmdb_cache_expire:
                    self.delete_meta_data(key)
                    return {}
            return info or {}

    def dump_meta_data(self, search, page, num):
        """
        分页获取当前缓存列表
        @param search: 检索的缓存key
        @param page: 页码
        @param num: 单页大小
        @return: 总数, 缓存列表
        """
        if page == 1:
            begin_pos = 0
        else:
            begin_pos = (page - 1) * num

        with lock:
            search_metas = [(k, {
                "id": v.get("id"),
                "title": v.get("title"),
                "year": v.get("year"),
                "media_type": v.get("type").value if isinstance(v.get("type"), Enum) else v.get("type"),
                "poster_path": v.get("poster_path"),
                "backdrop_path": v.get("backdrop_path")
            },  str(k).replace("[电影]", "").replace("[电视剧]", "").replace("[未知]", "").replace("-None", ""))
                for k, v in self._meta_data.items() if search.lower() in k.lower() and v.get("id") != 0]
            return len(search_metas), search_metas[begin_pos: begin_pos + num]

    def delete_meta_data(self, key):
        """
        删除缓存信息
        @param key: 缓存key
        @return: 被删除的缓存内容
        """
        with lock:
            removed = self._meta_data.pop(key, None)
            if removed is not None and str(removed.get("id")) != "0":
                self._revision += 1
            return removed

    def delete_meta_data_by_tmdbid(self, tmdbid):
        """
        清空对应TMDBID的所有缓存记录，以强制更新TMDB中最新的数据
        """
        with lock:
            for key, item in list(self._meta_data.items()):
                if str(item.get("id")) == str(tmdbid):
                    self.delete_meta_data(key)

    def delete_unknown_meta(self):
        """
        清除未识别的缓存记录，以便重新检索TMDB
        """
        self.delete_meta_data_by_tmdbid(0)

    def modify_meta_data(self, key, title):
        """
        删除缓存信息
        @param key: 缓存key
        @param title: 标题
        @return: 被修改后缓存内容
        """
        with lock:
            if self._meta_data.get(key):
                self._meta_data[key]['title'] = title
                self._revision += 1
                self._meta_data[key][CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
            return self._meta_data.get(key)

    @staticmethod
    def __load_meta_data(path):
        """
        从文件中加载缓存
        """
        try:
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                return data
            return {}
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {}

    def update_meta_data(self, meta_data):
        """
        新增或更新缓存条目
        """
        if not meta_data:
            return
        with lock:
            for key, item in meta_data.items():
                if not self._meta_data.get(key):
                    item[CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
                    self._meta_data[key] = item
                    if str(item.get("id")) != "0":
                        self._revision += 1

    def save_meta_data(self, force=False):
        """
        保存缓存数据到文件
        """
        with save_lock:
            with lock:
                now = int(time.time())
                expiry_due = self._next_expiry is not None and now >= self._next_expiry
                if not force and self._saved_revision == self._revision and not expiry_due:
                    return
                snapshot = {}
                next_expiry = None
                for key, item in list(self._meta_data.items()):
                    if str(item.get("id")) == '0':
                        continue
                    expiry = item.get(CACHE_EXPIRE_TIMESTAMP_STR)
                    if not expiry:
                        expiry = now + EXPIRE_TIMESTAMP
                        item[CACHE_EXPIRE_TIMESTAMP_STR] = expiry
                    if self._tmdb_cache_expire:
                        if now >= expiry:
                            del self._meta_data[key]
                            continue
                        if next_expiry is None or expiry < next_expiry:
                            next_expiry = expiry
                    snapshot[key] = copy.deepcopy(item)
                revision = self._revision
            self.__write_meta_data(self._meta_path, snapshot)
            with lock:
                self._saved_revision = revision
                self._next_expiry = next_expiry

    @staticmethod
    def __write_meta_data(path, meta_data):
        """在同目录中原子替换缓存文件。"""
        directory = os.path.dirname(path) or "."
        file_descriptor, temp_path = tempfile.mkstemp(
            prefix=".tmdb-",
            suffix=".tmp",
            dir=directory,
        )
        try:
            os.fchmod(file_descriptor, 0o600)
            temp_file = os.fdopen(file_descriptor, mode="wb")
            file_descriptor = None
            with temp_file:
                pickle.dump(meta_data, temp_file, pickle.HIGHEST_PROTOCOL)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, path)
            temp_path = None
            _fsync_directory(directory)
        finally:
            if file_descriptor is not None:
                os.close(file_descriptor)
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def get_cache_title(self, key):
        """
        获取缓存的标题
        """
        cache_media_info = self._meta_data.get(key)
        if not cache_media_info or not cache_media_info.get("id"):
            return None
        return cache_media_info.get("title")

    def set_cache_title(self, key, cn_title):
        """
        重新设置缓存标题
        """
        with lock:
            if key in self._meta_data:
                self._meta_data[key]['title'] = cn_title
                self._revision += 1
