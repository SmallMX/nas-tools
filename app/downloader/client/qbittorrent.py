import re
import time
from datetime import datetime
from urllib import parse

from packaging.version import parse as v

import log
import qbittorrentapi
from app.downloader.client._base import _IDownloadClient
from app.utils import ExceptionUtils, StringUtils
from app.utils.types import DownloaderType
from config import Config


# ===== 5. 第三方系统集成：qBittorrent 下载器控制 =====
# 初学者注意：我们的程序并不负责真正的“下载数据”工作，这个苦力活是由专业的下载软件（如 qBittorrent 或 Transmission）去做的。
# 这里就是我们和 qBittorrent 沟通的“遥控器”。我们通过 qbittorrentapi 这个第三方库，模拟用户操作去给它发指令。

class Qbittorrent(_IDownloadClient):
    schema = "qbittorrent"
    client_type = DownloaderType.QB.value
    _client_config = {}

    _auto_management = False
    _verify_cert = True
    qbc = None
    ver = None
    host = None
    port = None
    username = None
    password = None

    def __init__(self, config=None):
        if config:
            self._client_config = config
        else:
            self._client_config = Config().get_config('qbittorrent')
        self.init_config()
        self.connect()

    def init_config(self):
        self._verify_cert = True
        if self._client_config:
            self.host = self._client_config.get('qbhost')
            self.port = int(self._client_config.get('qbport')) if str(self._client_config.get('qbport')).isdigit() else 0
            self.username = self._client_config.get('qbusername')
            self.password = self._client_config.get('qbpassword')
            # 自动管理模式开关
            self._auto_management = self._client_config.get('auto_management')
            verify_cert = self._client_config.get('verify_cert')
            self._verify_cert = True if verify_cert is None else StringUtils.to_bool(verify_cert)

    @classmethod
    def match(cls, ctype):
        return True if ctype in [cls.schema, cls.client_type] else False

    def connect(self):
        if self.host and self.port:
            self.qbc = self.__login_qbittorrent()

    def __login_qbittorrent(self):
        """
        连接并登录 qbittorrent
        初学者注意：这就好比你在浏览器里输入 qBittorrent 的网址、用户名和密码。
        只不过这里是用代码的方式去建立连接。
        :return: qbittorrent 客户端对象
        """
        try:
            # 登录
            qbt = qbittorrentapi.Client(host=self.host,
                                        port=self.port,
                                        username=self.username,
                                        password=self.password,
                                        VERIFY_WEBUI_CERTIFICATE=self._verify_cert,
                                        REQUESTS_ARGS={'timeout': (10, 30)})
            try:
                qbt.auth_log_in()
                self.ver = qbt.app_version()
            except qbittorrentapi.LoginFailed as e:
                print(str(e))
            return qbt
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            log.error(f"【{self.client_type}】qBittorrent连接出错：{str(err)}")
            return None

    def get_status(self):
        if not self.qbc:
            return False
        try:
            return True if self.qbc.transfer_info() else False
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def get_torrents(self, ids=None, status=None, tag=None):
        """
        获取种子列表
        return: 种子列表, 是否发生异常
        """
        if not self.qbc:
            return [], True
        try:
            torrents = self.qbc.torrents_info(torrent_hashes=ids, status_filter=status, tag=tag)
            if self.is_ver_less_4_4():
                torrents = self.filter_torrent_by_tag(torrents, tag=tag)
            return torrents or [], False
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return [], True

    def get_downloading_torrents(self, tag=None):
        """
        获取正在下载的种子
        return: 种子列表, 是否发生异常
        """
        if not self.qbc:
            return []
        torrents, _ = self.get_torrents(status=["downloading"], tag=tag)
        return torrents

    def remove_torrents_tag(self, ids, tag):
        """
        移除种子Tag
        :param ids: 种子Hash列表
        :param tag: 标签内容
        """
        try:
            return self.qbc.torrents_delete_tags(torrent_hashes=ids, tags=tag)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def torrents_set_force_start(self, ids):
        """
        设置强制作种
        """
        try:
            self.qbc.torrents_set_force_start(enable=True, torrent_hashes=ids)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)

    @staticmethod
    def __has_required_tags(torrent, required_tags):
        if not required_tags:
            return True
        torrent_tags = torrent.get("tags") or []
        if isinstance(torrent_tags, str):
            torrent_tags = [tag.strip() for tag in torrent_tags.split(",") if tag.strip()]
        return set(required_tags).issubset(set(torrent_tags))

    def get_remove_torrents(self, config=None):
        if not config:
            return []
        remove_torrents = []
        remove_torrents_ids = []
        # qBittorrent Web API 的 tag 参数只接受单个标签，多标签组合在本地严格复核
        torrents, error_flag = self.get_torrents()
        if error_flag:
            return []
        ratio = config.get("ratio")
        # 做种时间 单位：小时
        seeding_time = config.get("seeding_time")
        # 大小 单位：GB
        size = config.get("size")
        minsize = size[0] * 1024 * 1024 * 1024 if size else 0
        maxsize = size[-1] * 1024 * 1024 * 1024 if size else 0
        # 平均上传速度 单位 KB/s
        upload_avs = config.get("upload_avs")
        savepath_key = config.get("savepath_key")
        tracker_key = config.get("tracker_key")
        qb_state = config.get("qb_state")
        qb_category = config.get("qb_category")
        for torrent in torrents:
            if not self.__has_required_tags(torrent, config.get("filter_tags")):
                continue
            date_done = torrent.completion_on if torrent.completion_on > 0 else torrent.added_on
            date_now = int(time.mktime(datetime.now().timetuple()))
            torrent_seeding_time = date_now - date_done if date_done else 0
            torrent_upload_avs = torrent.uploaded / torrent_seeding_time if torrent_seeding_time else 0
            if ratio and torrent.ratio <= ratio:
                continue
            if seeding_time and torrent_seeding_time <= seeding_time * 3600:
                continue
            if size and (torrent.size >= maxsize or torrent.size <= minsize):
                continue
            if upload_avs and torrent_upload_avs >= upload_avs * 1024:
                continue
            if savepath_key and not re.findall(savepath_key, torrent.save_path, re.I):
                continue
            if tracker_key and not re.findall(tracker_key, torrent.tracker, re.I):
                continue
            if qb_state and torrent.state not in qb_state:
                continue
            if qb_category and torrent.category not in qb_category:
                continue
            remove_torrents.append({
                "id": torrent.hash,
                "name": torrent.name,
                "site": parse.urlparse(torrent.tracker).netloc.split(".")[-2] if torrent.tracker else "",
                "size": torrent.size
            })
            remove_torrents_ids.append(torrent.hash)
        if config.get("samedata") and remove_torrents:
            remove_torrents_plus = []
            for remove_torrent in remove_torrents:
                name = remove_torrent.get("name")
                size = remove_torrent.get("size")
                for torrent in torrents:
                    if not self.__has_required_tags(torrent, config.get("filter_tags")):
                        continue
                    if torrent.name == name and torrent.size == size and torrent.hash not in remove_torrents_ids:
                        remove_torrents_plus.append({
                            "id": torrent.hash,
                            "name": torrent.name,
                            "site": parse.urlparse(torrent.tracker).netloc.split(".")[-2],
                            "size": torrent.size
                        })
            remove_torrents_plus += remove_torrents
            return remove_torrents_plus
        return remove_torrents

    def __get_last_add_torrentid_by_tag(self, tag, status=None):
        """
        根据种子的下载链接获取下载中或暂停的钟子的ID
        :return: 种子ID
        """
        try:
            torrents, _ = self.get_torrents(status=status, tag=tag)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return None
        if torrents:
            return torrents[0].get("hash")
        else:
            return None

    def get_torrent_id_by_tag(self, tag, status=None):
        """
        通过标签多次尝试获取刚添加的种子ID，并移除标签
        """
        torrent_id = None
        # QB添加下载后需要时间，重试5次每次等待5秒
        for i in range(1, 6):
            time.sleep(5)
            torrent_id = self.__get_last_add_torrentid_by_tag(tag=tag,
                                                              status=status)
            if torrent_id is None:
                continue
            else:
                self.remove_torrents_tag(torrent_id, tag)
                break
        return torrent_id

    def add_torrent(self,
                    content,
                    is_paused=False,
                    download_dir=None,
                    tag=None,
                    category=None,
                    content_layout=None,
                    upload_limit=None,
                    download_limit=None,
                    ratio_limit=None,
                    seeding_time_limit=None,
                    cookie=None
                    ):
        """
        【常用操作】告诉 qBittorrent 下载新种子
        初学者注意：当你选好电影点击“下载”时，最后就会走到这里。把种子的链接（urls）发给 qBittorrent，它就会乖乖开始干活。
        :param content: 种子urls或文件
        :param is_paused: 添加后暂停
        :param tag: 标签
        :param download_dir: 下载路径
        :param category: 分类
        :param content_layout: 布局
        :param upload_limit: 上传限速 Kb/s
        :param download_limit: 下载限速 Kb/s
        :param ratio_limit: 分享率限制
        :param seeding_time_limit: 做种时间限制
        :param cookie: 站点Cookie用于辅助下载种子
        :return: bool 是否成功
        """
        if not self.qbc or not content:
            return False
        if isinstance(content, str):
            urls = content
            torrent_files = None
        else:
            urls = None
            torrent_files = content
        if download_dir:
            save_path = download_dir
        else:
            save_path = None
        if not category:
            category = None
        if tag:
            tags = tag
        else:
            tags = None
        if not content_layout:
            content_layout = None
        if upload_limit:
            upload_limit = int(upload_limit) * 1024
        else:
            upload_limit = None
        if download_limit:
            download_limit = int(download_limit) * 1024
        else:
            download_limit = None
        if ratio_limit:
            ratio_limit = round(float(ratio_limit), 2)
        else:
            ratio_limit = None
        if seeding_time_limit:
            seeding_time_limit = int(seeding_time_limit)
        else:
            seeding_time_limit = None
        try:
            if self._auto_management:
                use_auto_torrent_management = True
            else:
                use_auto_torrent_management = False
            qbc_ret = self.qbc.torrents_add(urls=urls,
                                            torrent_files=torrent_files,
                                            save_path=save_path,
                                            category=category,
                                            is_paused=is_paused,
                                            tags=tags,
                                            content_layout=content_layout,
                                            upload_limit=upload_limit,
                                            download_limit=download_limit,
                                            ratio_limit=ratio_limit,
                                            seeding_time_limit=seeding_time_limit,
                                            use_auto_torrent_management=use_auto_torrent_management,
                                            cookie=cookie)
            return True if qbc_ret and str(qbc_ret).find("Ok") != -1 else False
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    @staticmethod
    def __normalize_torrent_ids(ids):
        if isinstance(ids, str):
            return ids.strip() or None
        if isinstance(ids, (list, tuple, set)):
            normalized_ids = [item.strip() for item in ids if isinstance(item, str) and item.strip()]
            return normalized_ids or None
        return None

    def start_torrents(self, ids):
        if not self.qbc:
            return False
        ids = self.__normalize_torrent_ids(ids)
        if not ids:
            return False
        try:
            self.qbc.torrents_resume(torrent_hashes=ids)
            return True
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def stop_torrents(self, ids):
        if not self.qbc:
            return False
        ids = self.__normalize_torrent_ids(ids)
        if not ids:
            return False
        try:
            self.qbc.torrents_pause(torrent_hashes=ids)
            return True
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def delete_torrents(self, delete_file, ids):
        if not self.qbc:
            return False
        ids = self.__normalize_torrent_ids(ids)
        if not ids:
            return False
        try:
            self.qbc.torrents_delete(delete_files=delete_file, torrent_hashes=ids)
            return True
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def get_files(self, tid):
        try:
            return self.qbc.torrents_files(torrent_hash=tid)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return None

    def set_files(self, **kwargs):
        """
        设置下载文件的状态，priority为0为不下载，priority为1为下载
        """
        if not kwargs.get("torrent_hash") or not kwargs.get("file_ids"):
            return False
        try:
            self.qbc.torrents_file_priority(torrent_hash=kwargs.get("torrent_hash"),
                                            file_ids=kwargs.get("file_ids"),
                                            priority=kwargs.get("priority"))
            return True
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return False

    def set_torrent_tag(self, **kwargs):
        pass

    def get_download_dirs(self):
        if not self.qbc:
            return []
        ret_dirs = []
        try:
            categories = self.qbc.torrents_categories(requests_args={'timeout': (5, 10)}) or {}
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return []
        for category in categories.values():
            if category and category.get("savePath") and category.get("savePath") not in ret_dirs:
                ret_dirs.append(category.get("savePath"))
        return ret_dirs

    def set_uploadspeed_limit(self, ids, limit):
        """
        设置上传限速，单位bytes/sec
        """
        if not self.qbc:
            return
        if not ids or not limit:
            return
        self.qbc.torrents_set_upload_limit(limit=int(limit),
                                           torrent_hashes=ids)

    def set_downloadspeed_limit(self, ids, limit):
        """
        设置下载限速，单位bytes/sec
        """
        if not self.qbc:
            return
        if not ids or not limit:
            return
        self.qbc.torrents_set_download_limit(limit=int(limit),
                                             torrent_hashes=ids)

    def is_ver_less_4_4(self):
        return v(self.ver) < v("v4.4.0")

    @staticmethod
    def filter_torrent_by_tag(torrents, tag):
        if not tag:
            return torrents
        if not isinstance(tag, list):
            tag = [tag]
        results = []
        for torrent in torrents:
            include_flag = True
            for t in tag:
                if t and t not in torrent.get("tags"):
                    include_flag = False
                    break
            if include_flag:
                results.append(torrent)
        return results

    def change_torrent(self, **kwargs):
        """
        修改种子状态
        """
        pass

    def get_downloading_progress(self, tag=None):
        """
        获取正在下载的种子进度
        """
        Torrents = self.get_downloading_torrents(tag=tag)
        DispTorrents = []
        for torrent in Torrents:
            # 进度
            progress = round(torrent.get('progress') * 100, 1)
            if torrent.get('state') in ['pausedDL']:
                state = "Stoped"
                speed = "已暂停"
            else:
                state = "Downloading"
                _dlspeed = StringUtils.str_filesize(torrent.get('dlspeed'))
                _upspeed = StringUtils.str_filesize(torrent.get('upspeed'))
                if progress >= 100:
                    speed = "%s%sB/s %s%sB/s" % (chr(8595), _dlspeed, chr(8593), _upspeed)
                else:
                    eta = StringUtils.str_timelong(torrent.get('eta'))
                    speed = "%s%sB/s %s%sB/s %s" % (chr(8595), _dlspeed, chr(8593), _upspeed, eta)
            # 主键
            DispTorrents.append({
                'id': torrent.get('hash'),
                'name': torrent.get('name'),
                'speed': speed,
                'state': state,
                'progress': progress
            })
        return DispTorrents
