import datetime
import time
import json
from sqlalchemy import cast, func

from app.db import MainDb, DbPersist
from app.db.models import *
from app.utils import StringUtils
from app.utils.types import MediaType


class DbHelper:
    _db = MainDb()

    @DbPersist(_db)
    def insert_search_results(self, media_items: list, title=None, ident_flag=True):
        """
        将返回信息插入数据库
        """
        if not media_items:
            return
        data_list = []
        for media_item in media_items:
            if media_item.type == MediaType.TV:
                mtype = "TV"
            elif media_item.type == MediaType.MOVIE:
                mtype = "MOV"
            else:
                mtype = "ANI"
            data_list.append(
                SearchResultInfo(
                    torrent_name=media_item.org_string,
                    enclosure=media_item.enclosure,
                    description=media_item.description,
                    type=mtype if ident_flag else '',
                    title=media_item.title if ident_flag else title,
                    year=media_item.year if ident_flag else '',
                    season=media_item.get_season_string() if ident_flag else '',
                    episode=media_item.get_episode_string() if ident_flag else '',
                    es_string=media_item.get_season_episode_string() if ident_flag else '',
                    vote=media_item.vote_average or "0",
                    image=media_item.get_backdrop_image(default=False, original=True),
                    poster=media_item.get_poster_image(),
                    tmdbid=media_item.tmdb_id,
                    overview=media_item.overview,
                    res_type=json.dumps({
                        "respix": media_item.resource_pix,
                        "restype": media_item.resource_type,
                        "reseffect": media_item.resource_effect,
                        "video_encode": media_item.video_encode
                    }),
                    res_order=media_item.res_order,
                    size=StringUtils.str_filesize(int(media_item.size)),
                    seeders=media_item.seeders,
                    peers=media_item.peers,
                    site=media_item.site,
                    site_order=media_item.site_order,
                    pageurl=media_item.page_url,
                    otherinfo=media_item.resource_team,
                    upload_volume_factor=media_item.upload_volume_factor,
                    download_volume_factor=media_item.download_volume_factor
                ))
        self._db.insert(data_list)

    def get_search_result_by_id(self, dl_id):
        """
        根据ID从数据库中查询检索结果的一条记录
        """
        return self._db.query(SearchResultInfo).filter(SearchResultInfo.id == dl_id).all()

    def get_search_results(self, ):
        """
        查询检索结果的所有记录
        """
        return self._db.query(SearchResultInfo).all()

    @DbPersist(_db)
    def delete_all_search_torrents(self, ):
        """
        删除所有搜索的记录
        """
        self._db.query(SearchResultInfo).delete()

    def get_config_site(self, ):
        """
        查询所有站点信息
        """
        return self._db.query(ConfigSite).order_by(cast(ConfigSite.pri, Integer).asc())

    def get_site_by_id(self, tid):
        """
        查询1个站点信息
        """
        return self._db.query(ConfigSite).filter(ConfigSite.id == int(tid)).all()

    def get_site_by_name(self, name):
        """
        基于站点名称查询站点信息
        :return:
        """
        return self._db.query(ConfigSite).filter(ConfigSite.name == name).all()

    @DbPersist(_db)
    def insert_config_site(self, name, site_pri, rssurl, signurl, cookie, note, rss_uses):
        """
        插入站点信息
        """
        if not name:
            return
        self._db.insert(ConfigSite(
            name=name,
            pri=site_pri,
            rssurl=rssurl,
            signurl=signurl,
            cookie=cookie,
            note=note,
            include=rss_uses
        ))

    @DbPersist(_db)
    def delete_config_site(self, tid):
        """
        删除站点信息
        """
        if not tid:
            return
        self._db.query(ConfigSite).filter(ConfigSite.id == int(tid)).delete()

    @DbPersist(_db)
    def update_config_site(self, tid, name, site_pri, rssurl, signurl, cookie, note, rss_uses):
        """
        更新站点信息
        """
        if not tid:
            return
        self._db.query(ConfigSite).filter(ConfigSite.id == int(tid)).update(
            {
                "name": name,
                "pri": site_pri,
                "rssurl": rssurl,
                "signurl": signurl,
                "cookie": cookie,
                "note": note,
                "include": rss_uses
            }
        )

    @DbPersist(_db)
    def update_config_site_note(self, tid, note):
        """
        更新站点属性
        """
        if not tid:
            return
        self._db.query(ConfigSite).filter(ConfigSite.id == int(tid)).update(
            {
                "note": note
            }
        )

    @DbPersist(_db)
    def update_site_cookie_ua(self, tid, cookie, ua=None):
        """
        更新站点Cookie和ua
        """
        if not tid:
            return
        rec = self._db.query(ConfigSite).filter(ConfigSite.id == int(tid)).first()
        if rec.note:
            note = json.loads(rec.note)
            if ua:
                note['ua'] = ua
        else:
            note = {}
        self._db.query(ConfigSite).filter(ConfigSite.id == int(tid)).update(
            {
                "cookie": cookie,
                "note": json.dumps(note)
            }
        )

    @DbPersist(_db)
    def insert_site_signin_history(self, site_id, site, action, success, message, duration=0):
        now = datetime.datetime.now()
        self._db.insert(SiteSigninHistory(
            site_id=int(site_id),
            site=site,
            action=action,
            success=1 if success else 0,
            message=message,
            duration=int(duration or 0),
            date=now.strftime("%Y-%m-%d"),
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        ))

    def get_site_signin_history(self, date=None, limit=200):
        query = self._db.query(SiteSigninHistory)
        if date:
            query = query.filter(SiteSigninHistory.date == date)
        return query.order_by(SiteSigninHistory.id.desc()).limit(max(1, min(int(limit), 1000))).all()

    def get_latest_site_signin_history(self, date):
        latest = {}
        for item in self.get_site_signin_history(date=date, limit=1000):
            key = (int(item.site_id), item.action)
            if key not in latest:
                latest[key] = item
        return latest

    @DbPersist(_db)
    def cleanup_site_signin_history(self, days=30):
        keep_days = max(1, min(int(days), 365))
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=keep_days)).strftime("%Y-%m-%d")
        self._db.query(SiteSigninHistory).filter(SiteSigninHistory.date < cutoff).delete()

    @DbPersist(_db)
    def delete_site_signin_history(self, site_ids=None):
        query = self._db.query(SiteSigninHistory)
        if site_ids:
            if not isinstance(site_ids, (list, tuple, set)):
                site_ids = [site_ids]
            normalized_ids = [int(site_id) for site_id in site_ids]
            query = query.filter(SiteSigninHistory.site_id.in_(normalized_ids))
        query.delete(synchronize_session=False)



























    def get_users(self, ):
        """
        查询用户列表
        """
        return self._db.query(ConfigUsers).all()

    def is_user_exists(self, name):
        """
        判断用户是否存在
        """
        if not name:
            return False
        count = self._db.query(ConfigUsers).filter(ConfigUsers.name == name).count()
        if count > 0:
            return True
        else:
            return False

    @DbPersist(_db)
    def insert_user(self, name, password, pris):
        """
        新增用户
        """
        if not name or not password:
            return False
        if self.is_user_exists(name):
            return False
        self._db.insert(ConfigUsers(
            name=name,
            password=password,
            pris=pris
        ))
        return True

    @DbPersist(_db)
    def delete_user(self, name):
        """
        删除用户
        """
        if not name:
            return False
        return self._db.query(ConfigUsers).filter(ConfigUsers.name == name).delete() == 1

    @DbPersist(_db)
    def update_site_user_statistics_site_name(self, new_name, old_name):
        """
        更新站点用户数据中站点名称
        """
        self._db.query(SiteUserInfoStats).filter(SiteUserInfoStats.site == old_name).update(
            {
                "site": new_name
            }
        )

    @DbPersist(_db)
    def update_site_user_statistics(self, site_user_infos: list):
        """
        更新站点用户粒度数据
        """
        if not site_user_infos:
            return
        update_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        for site_user_info in site_user_infos:
            site = site_user_info.site_name
            username = site_user_info.username
            user_level = site_user_info.user_level
            join_at = site_user_info.join_at
            upload = site_user_info.upload
            download = site_user_info.download
            ratio = site_user_info.ratio
            seeding = site_user_info.seeding
            seeding_size = site_user_info.seeding_size
            leeching = site_user_info.leeching
            bonus = site_user_info.bonus
            url = site_user_info.site_url
            msg_unread = site_user_info.message_unread
            if not self.is_exists_site_user_statistics(url):
                self._db.insert(SiteUserInfoStats(
                    site=site,
                    username=username,
                    user_level=user_level,
                    join_at=join_at,
                    update_at=update_at,
                    upload=upload,
                    download=download,
                    ratio=ratio,
                    seeding=seeding,
                    leeching=leeching,
                    seeding_size=seeding_size,
                    bonus=bonus,
                    url=url,
                    msg_unread=msg_unread
                ))
            else:
                self._db.query(SiteUserInfoStats).filter(SiteUserInfoStats.url == url).update(
                    {
                        "site": site,
                        "username": username,
                        "user_level": user_level,
                        "join_at": join_at,
                        "update_at": update_at,
                        "upload": upload,
                        "download": download,
                        "ratio": ratio,
                        "seeding": seeding,
                        "leeching": leeching,
                        "seeding_size": seeding_size,
                        "bonus": bonus,
                        "msg_unread": msg_unread
                    }
                )

    def is_exists_site_user_statistics(self, url):
        """
        判断站点数据是滞存在
        """
        count = self._db.query(SiteUserInfoStats).filter(SiteUserInfoStats.url == url).count()
        if count > 0:
            return True
        else:
            return False

    @DbPersist(_db)
    def update_site_favicon(self, site_user_infos: list):
        """
        更新站点图标数据
        """
        if not site_user_infos:
            return
        for site_user_info in site_user_infos:
            site_icon = "data:image/ico;base64," + \
                        site_user_info.site_favicon if site_user_info.site_favicon else site_user_info.site_url \
                                                                                        + "/favicon.ico"
            if not self.is_exists_site_favicon(site_user_info.site_name):
                self._db.insert(SiteFavicon(
                    site=site_user_info.site_name,
                    url=site_user_info.site_url,
                    favicon=site_icon
                ))
            elif site_user_info.site_favicon:
                self._db.query(SiteFavicon).filter(SiteFavicon.site == site_user_info.site_name).update(
                    {
                        "url": site_user_info.site_url,
                        "favicon": site_icon
                    }
                )

    def is_exists_site_favicon(self, site):
        """
        判断站点图标是否存在
        """
        count = self._db.query(SiteFavicon).filter(SiteFavicon.site == site).count()
        if count > 0:
            return True
        else:
            return False

    def get_site_favicons(self, site=None):
        """
        查询站点数据历史
        """
        if site:
            return self._db.query(SiteFavicon).filter(SiteFavicon.site == site).all()
        else:
            return self._db.query(SiteFavicon).all()

    @DbPersist(_db)
    def update_site_seed_info_site_name(self, new_name, old_name):
        """
        更新站点做种数据中站点名称
        :param new_name: 新的站点名称
        :param old_name: 原始站点名称
        :return:
        """
        self._db.query(SiteUserSeedingInfo).filter(SiteUserSeedingInfo.site == old_name).update(
            {
                "site": new_name
            }
        )

    @DbPersist(_db)
    def update_site_seed_info(self, site_user_infos: list):
        """
        更新站点做种数据
        """
        if not site_user_infos:
            return
        update_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        for site_user_info in site_user_infos:
            if not self.is_site_seeding_info_exist(url=site_user_info.site_url):
                self._db.insert(SiteUserSeedingInfo(
                    site=site_user_info.site_name,
                    update_at=update_at,
                    seeding_info=site_user_info.seeding_info,
                    url=site_user_info.site_url
                ))
            else:
                self._db.query(SiteUserSeedingInfo).filter(SiteUserSeedingInfo.url == site_user_info.site_url).update(
                    {
                        "site": site_user_info.site_name,
                        "update_at": update_at,
                        "seeding_info": site_user_info.seeding_info
                    }
                )

    def is_site_user_statistics_exists(self, url):
        """
        判断站点用户数据是否存在
        """
        if not url:
            return False
        count = self._db.query(SiteUserInfoStats).filter(SiteUserInfoStats.url == url).count()
        if count > 0:
            return True
        else:
            return False

    def get_site_user_statistics(self, num=100, strict_urls=None):
        """
        查询站点数据历史
        """
        if strict_urls:
            # 根据站点优先级排序
            return self._db.query(SiteUserInfoStats) \
                .join(ConfigSite, SiteUserInfoStats.site == ConfigSite.name) \
                .filter(SiteUserInfoStats.url.in_(tuple(strict_urls + ["__DUMMY__"]))) \
                .order_by(cast(ConfigSite.pri, Integer).asc()).limit(num).all()
        else:
            return self._db.query(SiteUserInfoStats).limit(num).all()

    def is_site_statistics_history_exists(self, url, date):
        """
        判断站点历史数据是否存在
        """
        if not url or not date:
            return False
        count = self._db.query(SiteStatisticsHistory).filter(SiteStatisticsHistory.url == url,
                                                             SiteStatisticsHistory.date == date).count()
        if count > 0:
            return True
        else:
            return False

    @DbPersist(_db)
    def update_site_statistics_site_name(self, new_name, old_name):
        """
        更新站点做种数据中站点名称
        :param new_name: 新站点名称
        :param old_name: 原始站点名称
        :return:
        """
        self._db.query(SiteStatisticsHistory).filter(SiteStatisticsHistory.site == old_name).update(
            {
                "site": new_name
            }
        )

    @DbPersist(_db)
    def insert_site_statistics_history(self, site_user_infos: list):
        """
        插入站点数据
        """
        if not site_user_infos:
            return
        date_now = time.strftime('%Y-%m-%d', time.localtime(time.time()))
        for site_user_info in site_user_infos:
            site = site_user_info.site_name
            upload = site_user_info.upload
            user_level = site_user_info.user_level
            download = site_user_info.download
            ratio = site_user_info.ratio
            seeding = site_user_info.seeding
            seeding_size = site_user_info.seeding_size
            leeching = site_user_info.leeching
            bonus = site_user_info.bonus
            url = site_user_info.site_url
            if not self.is_site_statistics_history_exists(date=date_now, url=url):
                self._db.insert(SiteStatisticsHistory(
                    site=site,
                    user_level=user_level,
                    date=date_now,
                    upload=upload,
                    download=download,
                    ratio=ratio,
                    seeding=seeding,
                    leeching=leeching,
                    seeding_size=seeding_size,
                    bonus=bonus,
                    url=url
                ))
            else:
                self._db.query(SiteStatisticsHistory).filter(SiteStatisticsHistory.date == date_now,
                                                             SiteStatisticsHistory.url == url).update(
                    {
                        "site": site,
                        "user_level": user_level,
                        "upload": upload,
                        "download": download,
                        "ratio": ratio,
                        "seeding": seeding,
                        "leeching": leeching,
                        "seeding_size": seeding_size,
                        "bonus": bonus
                    }
                )

    def get_site_statistics_history(self, site, days=30):
        """
        查询站点数据历史
        """
        return self._db.query(SiteStatisticsHistory).filter(
            SiteStatisticsHistory.site == site).order_by(
            SiteStatisticsHistory.date.asc()
        ).limit(days)

    def get_site_seeding_info(self, site):
        """
        查询站点做种信息
        """
        return self._db.query(SiteUserSeedingInfo.seeding_info).filter(
            SiteUserSeedingInfo.site == site).first()

    def is_site_seeding_info_exist(self, url):
        """
        判断做种数据是否已存在
        """
        count = self._db.query(SiteUserSeedingInfo).filter(
            SiteUserSeedingInfo.url == url).count()
        if count > 0:
            return True
        else:
            return False

    def get_site_statistics_recent_sites(self, days=7, strict_urls=None):
        """
        查询近期上传下载量
        """
        # 查询最大最小日期
        if strict_urls is None:
            strict_urls = []

        b_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        date_ret = self._db.query(func.max(SiteStatisticsHistory.date),
                                  func.MIN(SiteStatisticsHistory.date)).filter(
            SiteStatisticsHistory.date > b_date).all()
        if date_ret and date_ret[0][0]:
            total_upload = 0
            total_download = 0
            ret_site_uploads = []
            ret_site_downloads = []
            min_date = date_ret[0][1]
            # 查询开始值
            if strict_urls:
                subquery = self._db.query(SiteStatisticsHistory.site.label("site"),
                                          SiteStatisticsHistory.date.label("date"),
                                          func.sum(SiteStatisticsHistory.upload).label("upload"),
                                          func.sum(SiteStatisticsHistory.download).label("download")).filter(
                    SiteStatisticsHistory.date >= min_date,
                    SiteStatisticsHistory.url.in_(tuple(strict_urls + ["__DUMMY__"]))).group_by(
                    SiteStatisticsHistory.site, SiteStatisticsHistory.date).subquery()
            else:
                subquery = self._db.query(SiteStatisticsHistory.site.label("site"),
                                          SiteStatisticsHistory.date.label("date"),
                                          func.sum(SiteStatisticsHistory.upload).label("upload"),
                                          func.sum(SiteStatisticsHistory.download).label("download")).filter(
                    SiteStatisticsHistory.date >= min_date).group_by(
                    SiteStatisticsHistory.site, SiteStatisticsHistory.date).subquery()
            rets = self._db.query(subquery.c.site,
                                  func.min(subquery.c.upload),
                                  func.min(subquery.c.download),
                                  func.max(subquery.c.upload),
                                  func.max(subquery.c.download)).group_by(subquery.c.site).all()
            ret_sites = []
            for ret_b in rets:
                # 如果最小值都是0，可能时由于近几日没有更新数据，或者cookie过期，正常有数据的话，第二天能正常
                ret_b = list(ret_b)
                if ret_b[1] == 0 and ret_b[2] == 0:
                    ret_b[1] = ret_b[3]
                    ret_b[2] = ret_b[4]
                ret_sites.append(ret_b[0])
                if int(ret_b[1]) < int(ret_b[3]):
                    total_upload += int(ret_b[3]) - int(ret_b[1])
                    ret_site_uploads.append(int(ret_b[3]) - int(ret_b[1]))
                else:
                    ret_site_uploads.append(0)
                if int(ret_b[2]) < int(ret_b[4]):
                    total_download += int(ret_b[4]) - int(ret_b[2])
                    ret_site_downloads.append(int(ret_b[4]) - int(ret_b[2]))
                else:
                    ret_site_downloads.append(0)
            return total_upload, total_download, ret_sites, ret_site_uploads, ret_site_downloads
        else:
            return 0, 0, [], [], []

    def is_exists_download_history(self, title, tmdbid, mtype=None):
        """
        查询下载历史是否存在
        """
        if not title or not tmdbid:
            return False
        if mtype:
            count = self._db.query(DownloadHistory).filter(
                (DownloadHistory.title == title) | (DownloadHistory.tmdbid == tmdbid),
                DownloadHistory.type == mtype).count()
        else:
            count = self._db.query(DownloadHistory).filter(
                (DownloadHistory.title == title) | (DownloadHistory.tmdbid == tmdbid)).count()
        if count > 0:
            return True
        else:
            return False

    @DbPersist(_db)
    def insert_download_history(self, media_info):
        """
        新增下载历史
        """
        if not media_info:
            return
        if not media_info.title or not media_info.tmdb_id:
            return
        if self.is_exists_download_history(media_info.title, media_info.tmdb_id, media_info.type.value):
            self._db.query(DownloadHistory).filter(DownloadHistory.title == media_info.title,
                                                   DownloadHistory.tmdbid == media_info.tmdb_id,
                                                   DownloadHistory.type == media_info.type.value).update(
                {
                    "torrent": media_info.org_string,
                    "enclosure": media_info.enclosure,
                    "desc": media_info.description,
                    "date": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
                    "site": media_info.site
                }
            )
        else:
            self._db.insert(DownloadHistory(
                title=media_info.title,
                year=media_info.year,
                type=media_info.type.value,
                tmdbid=media_info.tmdb_id,
                vote=media_info.vote_average,
                poster=media_info.get_poster_image(),
                overview=media_info.overview,
                torrent=media_info.org_string,
                enclosure=media_info.enclosure,
                desc=media_info.description,
                date=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
                site=media_info.site
            ))

    def get_download_history(self, date=None, hid=None, num=30, page=1):
        """
        查询下载历史
        """
        if hid:
            return self._db.query(DownloadHistory).filter(DownloadHistory.id == int(hid)).all()
        elif date:
            return self._db.query(DownloadHistory).filter(
                DownloadHistory.date > date).order_by(DownloadHistory.date.desc()).all()
        else:
            offset = (int(page) - 1) * int(num)
            return self._db.query(DownloadHistory).order_by(
                DownloadHistory.date.desc()).limit(num).offset(offset).all()

    def is_media_downloaded(self, title, tmdbid):
        """
        根据标题和年份检查是否下载过
        """
        return self.is_exists_download_history(title, tmdbid)

    @DbPersist(_db)
    def insert_brushtask(self, brush_id, item):
        """
        新增刷流任务
        """
        if not brush_id:
            self._db.insert(SiteBrushTask(
                name=item.get('name'),
                site=item.get('site'),
                freeleech=item.get('free'),
                rss_rule=str(item.get('rss_rule')),
                remove_rule=str(item.get('remove_rule')),
                seed_size=item.get('seed_size'),
                inteval=item.get('interval'),
                downloader=item.get('downloader'),
                download_count='0',
                remove_count='0',
                download_size='0',
                upload_size='0',
                state=item.get('state'),
                lst_mod_date=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
                sendmessage=item.get('sendmessage'),
                forceupload=item.get('forceupload')
            ))
        else:
            self._db.query(SiteBrushTask).filter(SiteBrushTask.id == int(brush_id)).update(
                {
                    "name": item.get('name'),
                    "site": item.get('site'),
                    "freeleech": item.get('free'),
                    "rss_rule": str(item.get('rss_rule')),
                    "remove_rule": str(item.get('remove_rule')),
                    "seed_size": item.get('seed_size'),
                    "inteval": item.get('interval'),
                    "downloader": item.get('downloader'),
                    "state": item.get('state'),
                    "lst_mod_date": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())),
                    "sendmessage": item.get('sendmessage'),
                    "forceupload": item.get('forceupload')
                }
            )

    @DbPersist(_db)
    def delete_brushtask(self, brush_id):
        """
        删除刷流任务
        """
        self._db.query(SiteBrushTask).filter(SiteBrushTask.id == int(brush_id)).delete()
        self._db.query(SiteBrushTorrents).filter(SiteBrushTorrents.task_id == brush_id).delete()

    def get_brushtasks(self, brush_id=None):
        """
        查询刷流任务
        """
        if brush_id:
            return self._db.query(SiteBrushTask).filter(SiteBrushTask.id == int(brush_id)).first()
        else:
            # 根据站点优先级排序
            return self._db.query(SiteBrushTask) \
                .join(ConfigSite, SiteBrushTask.site == ConfigSite.id) \
                .order_by(cast(ConfigSite.pri, Integer).asc()).all()

    def get_brushtask_totalsize(self, brush_id):
        """
        查询刷流任务总体积
        """
        if not brush_id:
            return 0
        ret = self._db.query(func.sum(cast(SiteBrushTorrents.torrent_size,
                                           Integer))).filter(SiteBrushTorrents.task_id == brush_id,
                                                             SiteBrushTorrents.download_id != '0').first()
        if ret:
            return ret[0] or 0
        else:
            return 0

    @DbPersist(_db)
    def add_brushtask_download_count(self, brush_id):
        """
        增加刷流下载数
        """
        if not brush_id:
            return
        self._db.query(SiteBrushTask).filter(SiteBrushTask.id == int(brush_id)).update(
            {
                "download_count": SiteBrushTask.download_count + 1,
                "lst_mod_date": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
            }
        )

    def get_brushtask_remove_size(self, brush_id):
        """
        获取已删除种子的上传量
        """
        if not brush_id:
            return 0
        return self._db.query(SiteBrushTorrents.torrent_size).filter(SiteBrushTorrents.task_id == brush_id,
                                                                     SiteBrushTorrents.download_id == '0').all()

    @DbPersist(_db)
    def add_brushtask_upload_count(self, brush_id, upload_size, download_size, remove_count):
        """
        更新上传下载量和删除种子数
        """
        if not brush_id:
            return
        delete_upsize = 0
        delete_dlsize = 0
        remove_sizes = self.get_brushtask_remove_size(brush_id)
        for remove_size in remove_sizes:
            if not remove_size[0]:
                continue
            if str(remove_size[0]).find(",") != -1:
                sizes = str(remove_size[0]).split(",")
                delete_upsize += int(sizes[0] or 0)
                if len(sizes) > 1:
                    delete_dlsize += int(sizes[1] or 0)
            else:
                delete_upsize += int(remove_size[0])
        self._db.query(SiteBrushTask).filter(SiteBrushTask.id == int(brush_id)).update({
            "remove_count": SiteBrushTask.remove_count + remove_count,
            "upload_size": int(upload_size) + delete_upsize,
            "download_size": int(download_size) + delete_dlsize,
        })

    @DbPersist(_db)
    def insert_brushtask_torrent(self, brush_id, title, enclosure, downloader, download_id, size):
        """
        增加刷流下载的种子信息
        """
        if not brush_id:
            return
        if self.is_brushtask_torrent_exists(brush_id, title, enclosure):
            return
        self._db.insert(SiteBrushTorrents(
            task_id=brush_id,
            torrent_name=title,
            torrent_size=size,
            enclosure=enclosure,
            downloader=downloader,
            download_id=download_id,
            lst_mod_date=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        ))

    def get_brushtask_torrents(self, brush_id, active=True):
        """
        查询刷流任务所有种子
        """
        if not brush_id:
            return []
        if active:
            return self._db.query(SiteBrushTorrents).filter(
                SiteBrushTorrents.task_id == int(brush_id),
                SiteBrushTorrents.download_id != '0').all()
        else:
            return self._db.query(SiteBrushTorrents).filter(
                SiteBrushTorrents.task_id == int(brush_id)
            ).order_by(SiteBrushTorrents.lst_mod_date.desc()).all()

    def is_brushtask_torrent_exists(self, brush_id, title, enclosure):
        """
        查询刷流任务种子是否已存在
        """
        if not brush_id:
            return False
        count = self._db.query(SiteBrushTorrents).filter(SiteBrushTorrents.task_id == brush_id,
                                                         SiteBrushTorrents.torrent_name == title,
                                                         SiteBrushTorrents.enclosure == enclosure).count()
        if count > 0:
            return True
        else:
            return False

    @DbPersist(_db)
    def update_brushtask_torrent_state(self, ids: list):
        """
        更新刷流种子的状态
        """
        if not ids:
            return
        for _id in ids:
            self._db.query(SiteBrushTorrents).filter(SiteBrushTorrents.task_id == _id[1],
                                                     SiteBrushTorrents.download_id == _id[2]).update(
                {
                    "torrent_size": _id[0],
                    "download_id": '0'
                }
            )

    @DbPersist(_db)
    def delete_brushtask_torrent(self, brush_id, download_id):
        """
        删除刷流种子记录
        """
        if not download_id or not brush_id:
            return
        self._db.query(SiteBrushTorrents).filter(SiteBrushTorrents.task_id == brush_id,
                                                 SiteBrushTorrents.download_id == download_id).delete()

    def get_user_downloaders(self, did=None):
        """
        查询自定义下载器
        """
        if did:
            return self._db.query(SiteBrushDownloaders).filter(SiteBrushDownloaders.id == int(did)).first()
        else:
            return self._db.query(SiteBrushDownloaders).all()

    @DbPersist(_db)
    def update_user_downloader(self, did, name, dtype, user_config, note):
        """
        新增自定义下载器
        """
        if did:
            self._db.query(SiteBrushDownloaders).filter(SiteBrushDownloaders.id == int(did)).update(
                {
                    "name": name,
                    "type": dtype,
                    "host": user_config.get("host"),
                    "port": user_config.get("port"),
                    "username": user_config.get("username"),
                    "password": user_config.get("password"),
                    "save_dir": user_config.get("save_dir"),
                    "note": note
                }
            )
        else:
            self._db.insert(SiteBrushDownloaders(
                name=name,
                type=dtype,
                host=user_config.get("host"),
                port=user_config.get("port"),
                username=user_config.get("username"),
                password=user_config.get("password"),
                save_dir=user_config.get("save_dir"),
                note=note
            ))

    @DbPersist(_db)
    def delete_user_downloader(self, did):
        """
        删除自定义下载器
        """
        self._db.query(SiteBrushDownloaders).filter(SiteBrushDownloaders.id == int(did)).delete()

    @DbPersist(_db)
    def delete_download_setting(self, sid):
        """
        删除下载设置
        """
        if not sid:
            return
        self._db.query(DownloadSetting).filter(DownloadSetting.id == int(sid)).delete()

    def get_download_setting(self, sid=None):
        """
        查询下载设置
        """
        if sid:
            return self._db.query(DownloadSetting).filter(DownloadSetting.id == int(sid)).all()
        return self._db.query(DownloadSetting).all()

    @DbPersist(_db)
    def update_download_setting(self,
                                sid,
                                name,
                                category,
                                tags,
                                content_layout,
                                is_paused,
                                upload_limit,
                                download_limit,
                                ratio_limit,
                                seeding_time_limit,
                                downloader):
        """
        设置下载设置
        """
        if sid:
            self._db.query(DownloadSetting).filter(DownloadSetting.id == int(sid)).update(
                {
                    "name": name,
                    "category": category,
                    "tags": tags,
                    "content_layout": int(content_layout),
                    "is_paused": int(is_paused),
                    "upload_limit": int(float(upload_limit)),
                    "download_limit": int(float(download_limit)),
                    "ratio_limit": int(round(float(ratio_limit), 2) * 100),
                    "seeding_time_limit": int(float(seeding_time_limit)),
                    "downloader": downloader
                }
            )
        else:
            self._db.insert(DownloadSetting(
                name=name,
                category=category,
                tags=tags,
                content_layout=int(content_layout),
                is_paused=int(is_paused),
                upload_limit=int(float(upload_limit)),
                download_limit=int(float(download_limit)),
                ratio_limit=int(round(float(ratio_limit), 2) * 100),
                seeding_time_limit=int(float(seeding_time_limit)),
                downloader=downloader
            ))

    @DbPersist(_db)
    def delete_message_client(self, cid):
        """
        删除消息服务器
        """
        if not cid:
            return
        self._db.query(MessageClient).filter(MessageClient.id == int(cid)).delete()

    def get_message_client(self, cid=None):
        """
        查询消息服务器
        """
        if cid:
            return self._db.query(MessageClient).filter(MessageClient.id == int(cid)).all()
        return self._db.query(MessageClient).order_by(MessageClient.type).all()

    @DbPersist(_db)
    def insert_message_client(self,
                              name,
                              ctype,
                              config,
                              switchs: list,
                              interactive,
                              enabled,
                              note='',
                              cid=None):
        """
        在单个事务中新增或更新消息服务器，更新时保留原记录 ID。
        """
        values = {
            "name": name,
            "type": ctype,
            "config": config,
            "switchs": json.dumps(switchs),
            "interactive": int(interactive),
            "enabled": int(enabled),
            "note": note,
        }
        if cid:
            updated = self._db.query(MessageClient).filter(
                MessageClient.id == int(cid)
            ).update(values)
            if updated != 1:
                raise ValueError("消息服务器不存在，无法更新：%s" % cid)
            return
        self._db.insert(MessageClient(**values))

    @DbPersist(_db)
    def check_message_client(self, cid=None, interactive=None, enabled=None, ctype=None):
        """
        设置消息客户端状态
        """
        if cid and interactive is not None:
            self._db.query(MessageClient).filter(MessageClient.id == int(cid)).update(
                {
                    "interactive": int(interactive)
                }
            )
        elif cid and enabled is not None:
            self._db.query(MessageClient).filter(MessageClient.id == int(cid)).update(
                {
                    "enabled": int(enabled)
                }
            )
        elif not cid and int(interactive) == 0 and ctype:
            self._db.query(MessageClient).filter(MessageClient.interactive == 1,
                                                 MessageClient.type == ctype).update(
                {
                    "interactive": 0
                }
            )

    @DbPersist(_db)
    def delete_torrent_remove_task(self, tid):
        """
        删除自动删种策略
        """
        if not tid:
            return
        self._db.query(TorrentRemoveTask).filter(TorrentRemoveTask.id == int(tid)).delete()

    def get_torrent_remove_tasks(self, tid=None):
        """
        查询自动删种策略
        """
        if tid:
            return self._db.query(TorrentRemoveTask).filter(TorrentRemoveTask.id == int(tid)).all()
        return self._db.query(TorrentRemoveTask).order_by(TorrentRemoveTask.name).all()

    @DbPersist(_db)
    def insert_torrent_remove_task(self,
                                   name,
                                   action,
                                   interval,
                                   enabled,
                                   samedata,
                                   onlynastool,
                                   downloader,
                                   config: dict,
                                   note=None):
        """
        设置自动删种策略
        """
        self._db.insert(TorrentRemoveTask(
            name=name,
            action=int(action),
            interval=int(interval),
            enabled=int(enabled),
            samedata=int(samedata),
            onlynastool=int(onlynastool),
            downloader=downloader,
            config=json.dumps(config),
            note=note
        ))
