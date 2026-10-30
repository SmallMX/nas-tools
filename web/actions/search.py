import json
import os.path
import re
import cn2an
import requests
from app.helper import MetaHelper
from app.media import Category, Media, Bangumi, DouBan
from app.media.bangumi import BangumiRecommendationError
from app.media.doubanapi import DoubanRecommendationError
from app.media.tmdbv3api import TMDbException
from app.media.meta import MetaInfo, MetaBase
from app.media.streaming import StreamingDiscovery, StreamingDiscoveryError
from app.utils import StringUtils, ExceptionUtils
from app.utils.types import MediaType, MovieTypes
from web.backend.search_torrents import search_medias_for_web
from web.backend.web_utils import WebUtils


class SearchActions:
    """搜索、媒体识别与探索动作。"""

    def __init__(self, dbhelper, downloads):
        self.dbhelper = dbhelper
        self.downloads = downloads

    @staticmethod
    def search(data):
        """
        WEB检索资源
        """
        search_word = data.get("search_word")
        ident_flag = False if data.get("unident") else True
        filters = data.get("filters")
        tmdbid = data.get("tmdbid")
        media_type = data.get("media_type")
        if media_type:
            if media_type in MovieTypes:
                media_type = MediaType.MOVIE
            else:
                media_type = MediaType.TV
        if search_word:
            ret, ret_msg = search_medias_for_web(content=search_word,
                                                 ident_flag=ident_flag,
                                                 filters=filters,
                                                 tmdbid=tmdbid,
                                                 media_type=media_type)
            if ret != 0:
                return {"code": ret, "msg": ret_msg}
        return {"code": 0}

    def media_info(self, data):
        """
        查询媒体信息
        """
        mediaid = data.get("id")
        mtype = data.get("type")
        title = data.get("title")
        year = data.get("year")
        seasons = []
        link_url = ""
        vote_average = 0
        poster_path = ""
        release_date = ""
        overview = ""
        # 类型
        if mtype in MovieTypes:
            media_type = MediaType.MOVIE
        else:
            media_type = MediaType.TV

        if mediaid:
            media = WebUtils.get_mediainfo_from_id(
                mtype=media_type, mediaid=mediaid)
        else:
            media = Media().get_media_info(
                title=f"{title} {year}", mtype=media_type)
        if not media or not media.tmdb_info:
            return {
                "code": 1,
                "retmsg": "无法查询到TMDB信息",
                "type_str": media_type.value
            }
        if not mediaid:
            mediaid = media.tmdb_id
        link_url = media.get_detail_url()
        overview = media.overview
        poster_path = media.get_poster_image()
        title = media.title
        vote_average = round(float(media.vote_average or 0), 1)
        year = media.year
        if media_type != MediaType.MOVIE:
            release_date = media.tmdb_info.get('first_air_date')
            seasons = [{
                "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                "num": season.get("season_number")} for season in
                Media().get_tmdb_tv_seasons(tv_info=media.tmdb_info)]
        else:
            release_date = media.tmdb_info.get('release_date')

        return {
            "code": 0,
            "type": mtype,
            "type_str": media_type.value,
            "title": title,
            "vote_average": vote_average,
            "poster_path": poster_path,
            "release_date": release_date,
            "year": year,
            "overview": overview,
            "link_url": link_url,
            "tmdbid": mediaid,
            "seasons": seasons
        }

    def name_test(self, data):
        """
        名称识别测试
        """
        name = data.get("name")
        if not name:
            return {"code": -1}
        media_info = Media().get_media_info(title=name)
        if not media_info:
            return {"code": 0, "data": {"name": "无法识别"}}
        return {"code": 0, "data": self.mediainfo_dict(media_info)}

    @staticmethod
    def mediainfo_dict(media_info):
        if not media_info:
            return {}
        tmdb_id = media_info.tmdb_id
        tmdb_link = media_info.get_detail_url()
        tmdb_S_E_link = ""
        if tmdb_id:
            if media_info.get_season_string():
                tmdb_S_E_link = "%s/season/%s" % (tmdb_link,
                                                  media_info.get_season_seq())
                if media_info.get_episode_string():
                    tmdb_S_E_link = "%s/episode/%s" % (
                        tmdb_S_E_link, media_info.get_episode_seq())
        return {
            "type": media_info.type.value if media_info.type else "",
            "name": media_info.get_name(),
            "title": media_info.title,
            "year": media_info.year,
            "season_episode": media_info.get_season_episode_string(),
            "part": media_info.part,
            "tmdbid": tmdb_id,
            "tmdblink": tmdb_link,
            "tmdb_S_E_link": tmdb_S_E_link,
            "category": media_info.category,
            "restype": media_info.resource_type,
            "effect": media_info.resource_effect,
            "pix": media_info.resource_pix,
            "team": media_info.resource_team,
            "video_codec": media_info.video_encode,
            "audio_codec": media_info.audio_encode,
            "org_string": media_info.org_string
        }

    @staticmethod
    def get_streaming_filters(data):
        """获取当前平台和种类对应的筛选标签。"""
        try:
            fields = StreamingDiscovery().filters(data.get("source"), data.get("category") or "tv")
        except StreamingDiscoveryError as error:
            return {"code": 1, "msg": str(error)}
        return {"code": 0, "Filters": fields}

    def get_recommend(self, data):
        Type = data.get("type")
        SubType = data.get("subtype")
        CurrentPage = data.get("page")
        if Type == "STREAMING":
            try:
                result = StreamingDiscovery().discover(SubType, page=CurrentPage if CurrentPage is not None else 1,
                                                       params=data.get("params"))
            except StreamingDiscoveryError as error:
                return {"code": 1, "msg": str(error), "Items": []}
            return {"code": 0, **result}
        try:
            CurrentPage = int(CurrentPage or 1)
        except (TypeError, ValueError):
            return {"code": 1, "msg": "页码必须是整数", "Items": []}
        if not 1 <= CurrentPage <= 10000:
            return {"code": 1, "msg": "页码超出允许范围", "Items": []}

        douban_charts = {
            "dbom": "get_douban_online_movie", "dbhm": "get_douban_hot_movie",
            "dbht": "get_douban_hot_tv", "dbdh": "get_douban_hot_anime",
            "dbnm": "get_douban_new_movie", "dbtop": "get_douban_top250_movie",
            "dbzy": "get_douban_hot_show", "dbct": "get_douban_chinese_weekly_tv",
            "dbgt": "get_douban_weekly_tv_global", "dbnewmovie": "get_douban_latest_movie",
            "dbnewtv": "get_douban_latest_tv",
        }
        tmdb_charts = {
            "hm": ("movie", "get_tmdb_hot_movies"), "ht": ("tv", "get_tmdb_hot_tvs"),
            "nm": ("movie", "get_tmdb_new_movies"), "nt": ("tv", "get_tmdb_new_tvs"),
        }
        if Type in ("MOV", "TV") and SubType in douban_charts:
            try:
                items = getattr(DouBan(), douban_charts[SubType])(CurrentPage)
            except DoubanRecommendationError as error:
                return {"code": 1, "msg": str(error), "Items": []}
            return {"code": 0, "Items": items}
        if Type == "TRENDING" or (Type in ("MOV", "TV") and SubType in tmdb_charts):
            component, method = ("trending", "get_tmdb_trending_all_week") if Type == "TRENDING" else tmdb_charts[SubType]
            media = Media()
            if getattr(media, component, None) is None:
                return {"code": 1, "msg": "尚未配置 TMDB API Key，请在媒体设置中配置后重试。", "Items": []}
            try:
                items = getattr(media, method)(CurrentPage)
            except (TMDbException, requests.RequestException, ValueError, TypeError):
                # The TMDB client caches HTTP responses, including unsuccessful ones.
                # Evict a failed response so the section's retry reaches the service again.
                media.tmdb.cache_clear()
                return {"code": 1, "msg": "TMDB 榜单加载失败，请检查网络和 API 配置后重试。", "Items": []}
            return {"code": 0, "Items": items}

        res_list = []
        if Type in ['MOV', 'TV']:
            if SubType == "sim":
                # 相似推荐
                TmdbId = data.get("tmdbid")
                res_list = self.media_similar({
                    "tmdbid": TmdbId,
                    "page": CurrentPage,
                    "type": Type
                }).get("data")
            elif SubType == "more":
                # 更多推荐
                TmdbId = data.get("tmdbid")
                res_list = self.media_recommendations({
                    "tmdbid": TmdbId,
                    "page": CurrentPage,
                    "type": Type
                }).get("data")
            elif SubType == "person":
                # 人物作品
                PersonId = data.get("personid")
                res_list = self.person_medias({
                    "personid": PersonId,
                    "type": Type,
                    "page": CurrentPage
                }).get("data")
            elif SubType == "bangumi":
                # Bangumi每日放送
                Week = data.get("week")
                try:
                    res_list = Bangumi().get_bangumi_calendar(page=CurrentPage, week=Week)
                except BangumiRecommendationError as error:
                    return {"code": 1, "msg": str(error), "Items": []}
        elif Type == "SEARCH":
            # 搜索词条
            Keyword = data.get("keyword")
            Source = data.get("source")
            medias = WebUtils.search_media_infos(
                keyword=Keyword, source=Source, page=CurrentPage)
            res_list = [media.to_dict() for media in medias]
        elif Type == "DOWNLOADED":
            # 近期下载
            res_list = self.downloads.get_downloaded({
                "page": CurrentPage
            }).get("Items")
        elif Type == "DISCOVER":
            # TMDB发现
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            # 过滤参数 with_genres with_original_language
            params = data.get("params") or {}
            res_list = Media().get_tmdb_discover(mtype=mtype, page=CurrentPage, params=params)
        elif Type == "DOUBANTAG":
            # 豆瓣发现
            mtype = MediaType.MOVIE if SubType in MovieTypes else MediaType.TV
            # 参数
            params = data.get("params") or {}
            # 排序
            sort = params.get("sort") or "T"
            # 选中的分类
            tags = params.get("tags") or ""
            # 过滤参数
            try:
                res_list = DouBan().get_douban_disover(mtype=mtype,
                                                       sort=sort,
                                                       tags=tags,
                                                       page=CurrentPage)
            except DoubanRecommendationError as error:
                return {"code": 1, "msg": str(error), "Items": []}

        return {"code": 0, "Items": res_list}

    def get_search_result(self, data=None):
        """
        查询所有搜索结果
        """
        SearchResults = {}
        res = self.dbhelper.get_search_results()
        total = len(res)
        for item in res:
            # 质量(来源、效果)、分辨率
            if item.res_type:
                try:
                    res_mix = json.loads(item.res_type)
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
                respix = res_mix.get("respix") or ""
                video_encode = res_mix.get("video_encode") or ""
                restype = res_mix.get("restype") or ""
                reseffect = res_mix.get("reseffect") or ""
            else:
                restype = ""
                respix = ""
                reseffect = ""
                video_encode = ""
            # 分组标识 (来源，分辨率)
            group_key = re.sub(r"[-.\s@|]", "", f"{respix}_{restype}").lower()
            # 分组信息
            group_info = {
                "respix": respix,
                "restype": restype,
            }
            # 种子唯一标识 （大小，质量(来源、效果)，制作组组成）
            unique_key = re.sub(r"[-.\s@|]", "",
                                f"{respix}_{restype}_{video_encode}_{reseffect}_{item.size}_{item.otherinfo}").lower()
            # 标识信息
            unique_info = {
                "video_encode": video_encode,
                "size": item.size,
                "reseffect": reseffect,
                "releasegroup": item.otherinfo
            }
            # 结果
            title_string = f"{item.title}"
            if item.year:
                title_string = f"{title_string} ({item.year})"
            # 电视剧季集标识
            mtype = item.type or ""
            SE_key = item.es_string if item.es_string and mtype != "MOV" else "MOV"
            media_type = {"MOV": "电影", "TV": "电视剧", "ANI": "动漫"}.get(mtype)
            # 种子信息
            torrent_item = {
                "id": item.id,
                "seeders": item.seeders,
                "enclosure": item.enclosure,
                "site": item.site,
                "torrent_name": item.torrent_name,
                "description": item.description,
                "pageurl": item.pageurl,
                "uploadvalue": item.upload_volume_factor,
                "downloadvalue": item.download_volume_factor,
                "size": item.size,
                "respix": respix,
                "restype": restype,
                "reseffect": reseffect,
                "releasegroup": item.otherinfo,
                "video_encode": video_encode
            }
            # 促销
            free_item = {
                "value": f"{item.upload_volume_factor} {item.download_volume_factor}",
                "name": MetaBase.get_free_string(item.upload_volume_factor, item.download_volume_factor)
            }
            # 季
            filter_season = SE_key.split()[0] if SE_key and SE_key not in [
                "MOV", "TV"] else None
            # 媒体展示信息保留首条记录，各层分组只在首次遇到时创建。
            if title_string not in SearchResults:
                SearchResults[title_string] = {
                    "key": item.id,
                    "title": item.title,
                    "year": item.year,
                    "type_key": mtype,
                    "image": item.image,
                    "type": media_type,
                    "vote": item.vote,
                    "tmdbid": item.tmdbid,
                    "backdrop": item.image,
                    "poster": item.poster,
                    "overview": item.overview,
                    "exist": False,
                    "torrent_dict": {},
                    "filter": {"site": [], "free": [], "video": [], "season": []},
                }
            result_item = SearchResults[title_string]
            season_group = result_item["torrent_dict"].setdefault(SE_key, {})
            group = season_group.setdefault(group_key, {
                "group_info": group_info, "group_total": 0, "group_torrents": {},
            })
            unique = group["group_torrents"].setdefault(unique_key, {
                "unique_info": unique_info, "torrent_list": [],
            })
            unique["torrent_list"].append(torrent_item)
            group["group_total"] += 1

            torrent_filter = result_item["filter"]
            if free_item not in torrent_filter["free"]:
                torrent_filter["free"].append(free_item)
            if item.site not in torrent_filter["site"]:
                torrent_filter["site"].append(item.site)
            if video_encode and video_encode not in torrent_filter["video"]:
                torrent_filter["video"].append(video_encode)
            if filter_season and filter_season not in torrent_filter["season"]:
                torrent_filter["season"].append(filter_season)

        # 提升整季的顺序到顶层
        def se_sort(k):
            k = re.sub(r" +|(?<=s\d)\D*?(?=e)|(?<=s\d\d)\D*?(?=e)",
                       " ", k[0], flags=re.I).split()
            return (k[0], k[1]) if len(k) > 1 else ("Z" + k[0], "ZZZ")

        # 开始排序季集顺序
        for title, item in SearchResults.items():
            # 排序筛选器 季
            item["filter"]["season"].sort(reverse=True)
            # 排序种子列 集
            item["torrent_dict"] = sorted(item["torrent_dict"].items(),
                                          key=se_sort,
                                          reverse=True)
        return {"code": 0, "total": total, "result": SearchResults}

    @staticmethod
    def search_media_infos(data):
        """
        根据关键字搜索相似词条
        """
        SearchWord = data.get("keyword")
        if not SearchWord:
            return []
        SearchSourceType = data.get("searchtype")
        medias = WebUtils.search_media_infos(keyword=SearchWord,
                                             source=SearchSourceType)

        return {"code": 0, "result": [media.to_dict() for media in medias]}

    @staticmethod
    def get_tvseason_list(data):
        """
        获取剧集季列表
        """
        tmdbid = data.get("tmdbid")
        title = data.get("title")
        if title:
            title_season = MetaInfo(title=title).begin_season
        else:
            title_season = None
        if not str(tmdbid).isdigit():
            media_info = WebUtils.get_mediainfo_from_id(mtype=MediaType.TV,
                                                        mediaid=tmdbid)
            season_infos = Media().get_tmdb_tv_seasons(media_info.tmdb_info)
        else:
            season_infos = Media().get_tmdb_tv_seasons_byid(tmdbid=tmdbid)
        if title_season:
            seasons = [
                {
                    "text": "第%s季" % title_season,
                    "num": title_season
                }
            ]
        else:
            seasons = [
                {
                    "text": "第%s季" % cn2an.an2cn(season.get("season_number"), mode='low'),
                    "num": season.get("season_number")
                }
                for season in season_infos
            ]
        return {"code": 0, "seasons": seasons}

    @staticmethod
    def get_categories(data):
        if data.get("type") == "电影":
            categories = Category().get_movie_categorys()
        elif data.get("type") == "电视剧":
            categories = Category().get_tv_categorys()
        else:
            categories = Category().get_anime_categorys()
        return {"code": 0, "category": list(categories), "id": data.get("id"), "value": data.get("value")}

    @staticmethod
    def clear_tmdb_cache(data):
        """
        清空TMDB缓存
        """
        try:
            MetaHelper().clear_meta_data()
            os.remove(MetaHelper().get_meta_data_path())
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {"code": 0, "msg": str(e)}
        return {"code": 0}

    @staticmethod
    def delete_tmdb_cache(data):
        """
        删除tmdb缓存
        """
        if MetaHelper().delete_meta_data(data.get("cache_key")):
            MetaHelper().save_meta_data()
        return {"code": 0}

    @staticmethod
    def modify_tmdb_cache(data):
        """
        修改TMDB缓存的标题
        """
        if MetaHelper().modify_meta_data(data.get("key"), data.get("title")):
            MetaHelper().save_meta_data(force=True)
        return {"code": 0}

    @staticmethod
    def media_detail(data):
        """
        获取媒体详情
        """
        # TMDBID 或 DB:豆瓣ID
        tmdbid = data.get("tmdbid")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定媒体ID"}
        media_info = WebUtils.get_mediainfo_from_id(
            mtype=mtype, mediaid=tmdbid)
        # 检查TMDB信息
        if not media_info or not media_info.tmdb_info:
            return {
                "code": 1,
                "msg": "无法查询到TMDB信息"
            }
        MediaHander = Media()
        return {
            "code": 0,
            "data": {
                "tmdbid": media_info.tmdb_id,
                "douban_id": media_info.douban_id,
                "background": MediaHander.get_tmdb_backdrops(tmdbinfo=media_info.tmdb_info),
                "image": media_info.get_poster_image(),
                "vote": media_info.vote_average,
                "year": media_info.year,
                "title": media_info.title,
                "genres": MediaHander.get_tmdb_genres_names(tmdbinfo=media_info.tmdb_info),
                "overview": media_info.overview,
                "runtime": StringUtils.str_timehours(media_info.runtime),
                "fact": MediaHander.get_tmdb_factinfo(media_info),
                "crews": MediaHander.get_tmdb_crews(tmdbinfo=media_info.tmdb_info, nums=6),
                "actors": MediaHander.get_tmdb_cats(mtype=mtype, tmdbid=media_info.tmdb_id),
                "link": media_info.get_detail_url(),
                "douban_link": media_info.get_douban_detail_url()
            }
        }

    @staticmethod
    def media_similar(data):
        """
        查询TMDB相似媒体
        """
        tmdbid = data.get("tmdbid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定TMDBID"}
        if mtype == MediaType.MOVIE:
            result = Media().get_movie_similar(tmdbid=tmdbid, page=page)
        else:
            result = Media().get_tv_similar(tmdbid=tmdbid, page=page)
        return {"code": 0, "data": result}

    @staticmethod
    def media_recommendations(data):
        """
        查询TMDB同类推荐媒体
        """
        tmdbid = data.get("tmdbid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定TMDBID"}
        if mtype == MediaType.MOVIE:
            result = Media().get_movie_recommendations(tmdbid=tmdbid, page=page)
        else:
            result = Media().get_tv_recommendations(tmdbid=tmdbid, page=page)
        return {"code": 0, "data": result}

    @staticmethod
    def media_person(data):
        """
        查询TMDB媒体所有演员
        """
        tmdbid = data.get("tmdbid")
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not tmdbid:
            return {"code": 1, "msg": "未指定TMDBID"}
        return {"code": 0, "data": Media().get_tmdb_cats(tmdbid=tmdbid,
                                                         mtype=mtype)}

    @staticmethod
    def person_medias(data):
        """
        查询演员参演作品
        """
        personid = data.get("personid")
        page = data.get("page") or 1
        mtype = MediaType.MOVIE if data.get(
            "type") in MovieTypes else MediaType.TV
        if not personid:
            return {"code": 1, "msg": "未指定演员ID"}
        return {"code": 0, "data": Media().get_person_medias(personid=personid,
                                                             mtype=mtype,
                                                             page=page)}
