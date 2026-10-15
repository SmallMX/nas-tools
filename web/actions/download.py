from pathlib import Path
from flask_login import current_user
import log
from app.brushtask import BrushTask
from app.downloader import Downloader
from app.downloader.client import Qbittorrent, Transmission
from app.helper import ThreadHelper
from app.media import Media
from app.media.meta import MetaInfo
from app.message import Message
from app.sites import Sites
from app.torrentremover import TorrentRemover
from app.utils import StringUtils, ExceptionUtils, Torrent
from app.utils.types import SearchType, DownloaderType
from config import Config
from web.security import sanitize_downloader
from web.actions.validation import is_valid_btih_magnet, validate_configured_site_url


class DownloadActions:
    """下载控制、下载器设置与自动删种动作。"""

    def __init__(self, dbhelper):
        self.dbhelper = dbhelper

    def download(self, data):
        """
        从WEB添加下载
        """
        dl_id = data.get("id")
        dl_dir = data.get("dir")
        dl_setting = data.get("setting")
        results = self.dbhelper.get_search_result_by_id(dl_id)
        for res in results:
            media = Media().get_media_info(title=res.torrent_name, subtitle=res.description)
            if not media:
                continue
            media.set_torrent_info(enclosure=res.enclosure,
                                   size=res.size,
                                   site=res.site,
                                   page_url=res.pageurl,
                                   upload_volume_factor=float(
                                       res.upload_volume_factor),
                                   download_volume_factor=float(res.download_volume_factor))
            # 添加下载
            ret, ret_msg = Downloader().download(media_info=media,
                                                 download_dir=dl_dir,
                                                 download_setting=dl_setting)
            if ret:
                # 发送消息
                media.user_name = current_user.username
                Message().send_download_message(in_from=SearchType.WEB,
                                                can_item=media)
            else:
                return {"retcode": -1, "retmsg": ret_msg}
        return {"retcode": 0, "retmsg": ""}

    @staticmethod
    def download_link(data):
        """
        从WEB添加下载链接
        """
        site = data.get("site")
        enclosure = data.get("enclosure")
        title = data.get("title")
        description = data.get("description")
        page_url = data.get("page_url")
        size = data.get("size")
        seeders = data.get("seeders")
        uploadvolumefactor = data.get("uploadvolumefactor")
        downloadvolumefactor = data.get("downloadvolumefactor")
        dl_dir = data.get("dl_dir")
        dl_setting = data.get("dl_setting")
        if not isinstance(title, str) or not title.strip() or len(title) > 1000 \
                or not isinstance(enclosure, str):
            return {"code": -1, "msg": "种子信息有误"}
        enclosure = enclosure.strip()
        try:
            if is_valid_btih_magnet(enclosure):
                if page_url:
                    page_url = validate_configured_site_url(site, page_url)
            elif (enclosure.startswith("[") and enclosure.endswith("]")) \
                    or enclosure.startswith("#"):
                if len(enclosure) > 4096:
                    raise ValueError("站点解析规则过长")
                page_url = validate_configured_site_url(site, page_url)
            else:
                enclosure = validate_configured_site_url(site, enclosure)
                if page_url:
                    page_url = validate_configured_site_url(site, page_url)
            uploadvolumefactor = float(uploadvolumefactor if uploadvolumefactor is not None else 1)
            downloadvolumefactor = float(downloadvolumefactor if downloadvolumefactor is not None else 1)
            if not 0 <= uploadvolumefactor <= 10 or not 0 <= downloadvolumefactor <= 10:
                raise ValueError("上传或下载系数超出允许范围")
        except (TypeError, ValueError) as error:
            return {"code": -1, "msg": str(error)}
        media = Media().get_media_info(title=title, subtitle=description)
        if not media:
            media = MetaInfo(title=title)
            media.org_string = title
        media.site = site
        media.enclosure = enclosure
        media.page_url = page_url
        media.size = size
        media.upload_volume_factor = uploadvolumefactor
        media.download_volume_factor = downloadvolumefactor
        media.seeders = seeders
        # 添加下载
        ret, ret_msg = Downloader().download(media_info=media,
                                             download_dir=dl_dir,
                                             download_setting=dl_setting)
        if ret:
            # 发送消息
            media.user_name = current_user.username
            Message().send_download_message(SearchType.WEB, media)
            return {"code": 0, "msg": "下载成功"}
        else:
            return {"code": 1, "msg": ret_msg or "如连接正常，请检查下载任务是否存在"}

    @staticmethod
    def download_torrent(data):
        """
        从种子文件添加下载
        """

        def __download(_media_info, _file_path):
            _media_info.site = "WEB"
            # 添加下载
            ret, ret_msg = Downloader().download(media_info=_media_info,
                                                 download_dir=dl_dir,
                                                 download_setting=dl_setting,
                                                 torrent_file=_file_path)
            # 发送消息
            _media_info.user_name = current_user.username
            if ret:
                Message().send_download_message(SearchType.WEB, _media_info)
            else:
                Message().send_download_fail_message(_media_info, ret_msg)
            return bool(ret), ret_msg or "下载器拒绝了任务"

        if not isinstance(data, dict):
            return {"code": -1, "msg": "请求格式不合法"}
        dl_dir = data.get("dl_dir")
        dl_setting = data.get("dl_setting")
        files = data.get("files") or []
        magnets = data.get("magnets") or []
        if not isinstance(files, list) or not isinstance(magnets, list):
            return {"code": -1, "msg": "种子文件和磁链必须使用列表格式"}
        files = [item for item in files if item]
        magnets = [item for item in magnets if item]
        if not files and not magnets:
            return {"code": -1, "msg": "没有种子文件或磁链"}
        if len(files) + len(magnets) > 20:
            return {"code": -1, "msg": "单次最多处理 20 个种子或磁链"}

        temp_root = Path(Config().get_temp_path()).resolve()
        failures = []
        success_count = 0
        for index, file_item in enumerate(files, start=1):
            file_path = None
            try:
                if not isinstance(file_item, dict):
                    raise ValueError("文件描述格式不合法")
                file_name = file_item.get("upload", {}).get("filename")
                if not isinstance(file_name, str) \
                        or Path(file_name).name != file_name \
                        or Path(file_name).suffix.lower() != ".torrent":
                    raise ValueError("仅接受临时目录中的 .torrent 文件名")
                raw_path = temp_root / file_name
                if raw_path.is_symlink():
                    raise ValueError("不允许使用符号链接种子文件")
                file_path = raw_path.resolve(strict=True)
                if file_path.parent != temp_root or not file_path.is_file():
                    raise ValueError("种子文件不在临时目录内")
                media_info = Media().get_media_info(title=file_name)
                if not media_info:
                    media_info = MetaInfo(title=file_name)
                    media_info.org_string = file_name
                success, error_message = __download(media_info, str(file_path))
                if success:
                    success_count += 1
                else:
                    failures.append(f"文件 {index}: {error_message}")
            except (OSError, ValueError) as error:
                failures.append(f"文件 {index}: {error}")
            except Exception as error:
                ExceptionUtils.exception_traceback(error)
                failures.append(f"文件 {index}: 处理失败")
            finally:
                if file_path and file_path.parent == temp_root:
                    try:
                        file_path.unlink(missing_ok=True)
                    except OSError:
                        log.warn(f"【Download】临时种子文件清理失败：{file_path.name}")

        for index, magnet in enumerate(magnets, start=1):
            try:
                if not is_valid_btih_magnet(magnet):
                    raise ValueError("磁链必须以 magnet:?xt=urn:btih: 开头并包含有效 BTIH")
                magnet = magnet.strip()
                title = Torrent().get_magnet_title(magnet)
                if title:
                    media_info = Media().get_media_info(title=title)
                else:
                    media_info = MetaInfo(title="磁力链接")
                    media_info.org_string = magnet
                if not media_info:
                    media_info = MetaInfo(title=title or "磁力链接")
                    media_info.org_string = title or magnet
                media_info.set_torrent_info(enclosure=magnet,
                                            download_volume_factor=0,
                                            upload_volume_factor=1)
                success, error_message = __download(media_info, None)
                if success:
                    success_count += 1
                else:
                    failures.append(f"磁链 {index}: {error_message}")
            except ValueError as error:
                failures.append(f"磁链 {index}: {error}")
            except Exception as error:
                ExceptionUtils.exception_traceback(error)
                failures.append(f"磁链 {index}: 处理失败")

        if failures:
            return {
                "code": 1,
                "msg": f"成功 {success_count} 项，失败 {len(failures)} 项：" + "；".join(failures),
                "success_count": success_count,
                "failures": failures,
            }
        return {"code": 0, "msg": f"成功添加 {success_count} 个下载任务"}

    @staticmethod
    def _control_torrent(data, operation, failure_message):
        tid = data.get("id") if isinstance(data, dict) else None
        if not tid:
            return {"retcode": 1, "retmsg": "下载任务 ID 不能为空", "id": tid}
        if operation(tid):
            return {"retcode": 0, "id": tid}
        return {"retcode": 1, "retmsg": failure_message, "id": tid}

    @staticmethod
    def pt_start(data):
        """开始下载。"""
        return DownloadActions._control_torrent(
            data, lambda tid: Downloader().start_torrents(ids=tid), "下载器未能启动任务"
        )

    @staticmethod
    def pt_stop(data):
        """停止下载。"""
        return DownloadActions._control_torrent(
            data, lambda tid: Downloader().stop_torrents(ids=tid), "下载器未能停止任务"
        )

    @staticmethod
    def pt_remove(data):
        """删除下载及其文件。"""
        return DownloadActions._control_torrent(
            data, lambda tid: Downloader().delete_torrents(ids=tid, delete_file=True), "下载器未能删除任务"
        )

    @staticmethod
    def pt_info(data):
        """
        查询具体种子的信息
        """
        ids = data.get("ids")
        Client, Torrents = Downloader().get_torrents(torrent_ids=ids)
        DispTorrents = []
        for torrent in Torrents:
            if not torrent:
                continue
            if Client == DownloaderType.QB:
                if torrent.get('state') in ['pausedDL']:
                    state = "Stoped"
                    speed = "已暂停"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.get('dlspeed'))
                    eta = StringUtils.str_timelong(torrent.get('eta'))
                    upspeed = StringUtils.str_filesize(torrent.get('upspeed'))
                    speed = "%s%sB/s %s%sB/s %s" % (chr(8595),
                                                    dlspeed, chr(8593), upspeed, eta)
                # 进度
                progress = round(torrent.get('progress') * 100)
                # 主键
                key = torrent.get('hash')

            else:
                if torrent.status in ['stopped']:
                    state = "Stoped"
                    speed = "已暂停"
                else:
                    state = "Downloading"
                    dlspeed = StringUtils.str_filesize(torrent.rateDownload)
                    upspeed = StringUtils.str_filesize(torrent.rateUpload)
                    speed = "%s%sB/s %s%sB/s" % (chr(8595),
                                                 dlspeed, chr(8593), upspeed)
                # 进度
                progress = round(torrent.progress, 1)
                # 主键
                key = torrent.id

            torrent_info = {'id': key, 'speed': speed,
                            'state': state, 'progress': progress}
            if torrent_info not in DispTorrents:
                DispTorrents.append(torrent_info)
        return {"retcode": 0, "torrents": DispTorrents}

    @staticmethod
    def test_connection(data):
        """
        测试连通性
        """
        ALLOWED_TESTS = {
            "qbittorrent": Qbittorrent,
            "transmission": Transmission,
        }
        command = data.get("command")
        ret = None
        if command:
            try:
                module_obj = None
                commands = command if isinstance(command, list) else [command]
                for cmd_str in commands:
                    client_type = ALLOWED_TESTS.get(cmd_str)
                    if not client_type:
                        ret = None
                        break
                    module_obj = client_type()
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
                    ret = module_obj.get_status()
                # 重载配置
                Config().init_config()
                if module_obj:
                    if hasattr(module_obj, "init_config"):
                        module_obj.init_config()
            except Exception as e:
                ret = None
                ExceptionUtils.exception_traceback(e)
            return {"code": 0 if ret else 1}
        return {"code": 0}

    def add_downloader(self, data):
        """
        添加自定义下载器
        """
        test = data.get("test")
        dl_id = data.get("id")
        dl_name = data.get("name")
        dl_type = data.get("type")
        if dl_type not in {"qbittorrent", "transmission"}:
            return {"code": 1, "msg": "不支持的下载器类型"}
        password = data.get("password")
        if dl_id and not password:
            existing = self.dbhelper.get_user_downloaders(dl_id)
            if existing:
                password = existing.password
        if test:
            # 测试
            if dl_type == "qbittorrent":
                downloader = Qbittorrent(
                    config={
                        "qbhost": data.get("host"),
                        "qbport": data.get("port"),
                        "qbusername": data.get("username"),
                        "qbpassword": password
                    })
            else:
                downloader = Transmission(
                    config={
                        "trhost": data.get("host"),
                        "trport": data.get("port"),
                        "trusername": data.get("username"),
                        "trpassword": password
                    })
            if downloader.get_status():
                return {"code": 0}
            else:
                return {"code": 1}
        else:
            # 保存
            self.dbhelper.update_user_downloader(
                did=dl_id,
                name=dl_name,
                dtype=dl_type,
                user_config={
                    "host": data.get("host"),
                    "port": data.get("port"),
                    "username": data.get("username"),
                    "password": password,
                    "save_dir": data.get("save_dir")
                },
                note=None)
            BrushTask().init_config()
            return {"code": 0}

    def delete_downloader(self, data):
        """
        删除自定义下载器
        """
        dl_id = data.get("id")
        if dl_id:
            self.dbhelper.delete_user_downloader(dl_id)
            BrushTask().init_config()
        return {"code": 0}

    def get_downloader(self, data):
        """
        查询自定义下载器
        """
        dl_id = data.get("id")
        if dl_id:
            info = self.dbhelper.get_user_downloaders(dl_id)
            if info:
                return {"code": 0, "info": sanitize_downloader(info.as_dict())}
        return {"code": 1}

    def get_downloaded(self, data):
        page = data.get("page")
        Items = self.dbhelper.get_download_history(page=page)
        if Items:
            return {"code": 0, "Items": [{
                'id': item.tmdbid,
                'orgid': item.tmdbid,
                'tmdbid': item.tmdbid,
                'title': item.title,
                'type': 'MOV' if item.type == "电影" else "TV",
                'media_type': item.type,
                'year': item.year,
                'vote': item.vote,
                'image': item.poster,
                'overview': item.torrent,
                "date": item.date,
                "site": item.site
            } for item in Items]}
        else:
            return {"code": 0, "Items": []}

    @staticmethod
    def get_downloading(data=None):
        """
        查询正在下载的任务
        """
        torrents = Downloader().get_downloading_progress()
        MediaHander = Media()
        for torrent in torrents:
            # 识别
            name = torrent.get("name")
            media_info = MediaHander.get_media_info(title=name)
            if not media_info:
                torrent.update({
                    "title": name,
                    "image": ""
                })
                continue
            if not media_info.tmdb_info:
                year = media_info.year
                if year:
                    title = "%s (%s) %s" % (media_info.get_name(),
                                            year, media_info.get_season_episode_string())
                else:
                    title = "%s %s" % (media_info.get_name(),
                                       media_info.get_season_episode_string())
            else:
                title = "%s %s" % (media_info.get_title_string(
                ), media_info.get_season_episode_string())
            poster_path = media_info.get_poster_image()
            torrent.update({
                "title": title,
                "image": poster_path or ""
            })
        return {"code": 0, "result": torrents}

    @staticmethod
    def get_download_setting(data):
        sid = data.get("sid")
        if sid:
            download_setting = Downloader().get_download_setting(sid=sid)
        else:
            download_setting = list(
                Downloader().get_download_setting().values())
        return {"code": 0, "data": download_setting}

    def update_download_setting(self, data):
        sid = data.get("sid")
        name = data.get("name")
        category = data.get("category")
        tags = data.get("tags")
        content_layout = data.get("content_layout")
        is_paused = data.get("is_paused")
        upload_limit = data.get("upload_limit")
        download_limit = data.get("download_limit")
        ratio_limit = data.get("ratio_limit")
        seeding_time_limit = data.get("seeding_time_limit")
        downloader = data.get("downloader")
        if downloader not in {"", None, DownloaderType.QB.value, DownloaderType.TR.value}:
            return {"code": 1, "msg": "不支持的下载器类型"}
        self.dbhelper.update_download_setting(sid=sid,
                                              name=name,
                                              category=category,
                                              tags=tags,
                                              content_layout=content_layout,
                                              is_paused=is_paused,
                                              upload_limit=upload_limit or 0,
                                              download_limit=download_limit or 0,
                                              ratio_limit=ratio_limit or 0,
                                              seeding_time_limit=seeding_time_limit or 0,
                                              downloader=downloader)
        Downloader().init_config()
        return {"code": 0}

    def delete_download_setting(self, data):
        sid = data.get("sid")
        self.dbhelper.delete_download_setting(sid=sid)
        Downloader().init_config()
        return {"code": 0}

    @staticmethod
    def get_download_dirs(data):
        """
        获取下载目录
        """
        sid = data.get("sid")
        site = data.get("site")
        if not sid and site:
            sid = Sites().get_site_download_setting(site_name=site)
        dirs = Downloader().get_download_dirs(setting=sid)
        return {"code": 0, "paths": dirs}

    @staticmethod
    def update_torrent_remove_task(data):
        """
        更新自动删种任务
        """
        flag, msg = TorrentRemover().update_torrent_remove_task(data=data)
        if not flag:
            return {"code": 1, "msg": msg}
        else:
            TorrentRemover().init_config()
            return {"code": 0}

    @staticmethod
    def get_torrent_remove_task(data=None):
        """
        获取自动删种任务
        """
        if data:
            tid = data.get("tid")
        else:
            tid = None
        return {"code": 0, "detail": TorrentRemover().get_torrent_remove_tasks(taskid=tid)}

    @staticmethod
    def delete_torrent_remove_task(data):
        """
        删除自动删种任务
        """
        tid = data.get("tid")
        flag = TorrentRemover().delete_torrent_remove_task(taskid=tid)
        if flag:
            TorrentRemover().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def get_remove_torrents(data):
        """
        获取满足自动删种任务的种子
        """
        tid = data.get("tid")
        flag, torrents = TorrentRemover().get_remove_torrents(taskid=tid)
        if not flag or not torrents:
            return {"code": 1, "msg": "未获取到符合处理条件种子"}
        return {"code": 0, "data": torrents}

    @staticmethod
    def auto_remove_torrents(data):
        """
        执行自动删种任务
        """
        tid = data.get("tid")
        TorrentRemover().auto_remove_torrents(taskids=tid)
        return {"code": 0}

    @staticmethod
    def sch(data):
        """
        启动定时服务
        """
        commands = {
            "autoremovetorrents": TorrentRemover().auto_remove_torrents,
        }
        sch_item = data.get("item")
        command = commands.get(sch_item)
        if not command:
            return {"code": 1, "msg": "不支持的服务", "item": sch_item}
        ThreadHelper().start_thread(command, ())
        return {"code": 0, "msg": "服务已启动", "item": sch_item}
