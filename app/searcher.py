import copy

import log
from app.helper import DbHelper
from app.indexer import Indexer
from config import Config
from app.message import Message
from app.downloader import Downloader
from app.media import Media
from app.helper import ProgressHelper
from app.utils.types import SearchType


class Searcher:
    downloader = None
    media = None
    message = None
    indexer = None
    progress = None
    dbhelper = None

    _search_auto = True

    def __init__(self):
        self.downloader = Downloader()
        self.media = Media()
        self.message = Message()
        self.progress = ProgressHelper()
        self.dbhelper = DbHelper()
        self.indexer = Indexer()
        self.init_config()

    def init_config(self):
        self._search_auto = Config().get_config("pt").get('search_auto', True)

    def search_medias(self,
                      key_word: [str, list],
                      filter_args: dict,
                      match_media=None,
                      in_from: SearchType = None):
        """
        根据关键字调用索引器检查媒体
        :param key_word: 检索的关键字，不能为空
        :param filter_args: 过滤条件
        :param match_media: 区配的媒体信息
        :param in_from: 搜索渠道
        :return: 命中的资源媒体信息列表
        """
        if not key_word:
            return []
        if not self.indexer:
            return []
        return self.indexer.search_by_keyword(key_word=key_word,
                                              filter_args=filter_args,
                                              match_media=match_media,
                                              in_from=in_from)

    def search_media_resources(self, media_info, filters=None, in_from: SearchType = None,
                               *, use_media_keyword=True, on_retry=None):
        """准备已识别媒体的条件和名称，首轮无结果时用备用名称重搜。

        filters 覆盖媒体推导的条件；显式关键词仅在 use_media_keyword 开启时优先。
        on_retry 在第二轮前接收重搜提示；进度收尾、保存和下载由调用方负责。
        """
        search_season = media_info.get_season_list() if media_info.begin_season is not None else None
        search_episode = media_info.get_episode_list()
        if search_episode and not search_season:
            search_season = [1]
        filter_args = {"season": search_season,
                       "episode": search_episode,
                       "year": media_info.year,
                       "type": media_info.type}
        if filters:
            filter_args.update(filters)

        second_search_name = None
        if use_media_keyword and media_info.keyword:
            first_search_name = media_info.keyword
        else:
            search_cn_name = media_info.cn_name or media_info.title
            search_en_name = media_info.en_name
            if not search_en_name:
                if media_info.original_language == "en":
                    search_en_name = media_info.original_title
                else:
                    # 使用独立媒体对象补查，查询方法会恢复临时切换的语言。
                    search_en_name = Media().get_tmdb_en_title(media_info)
            if search_en_name and not media_info.en_name:
                # 各站点复用本次补查的英文名，不改写媒体识别缓存。
                media_info = copy.copy(media_info)
                media_info.en_name = search_en_name
            if Config().get_config("laboratory").get("search_en_title") and search_en_name:
                first_search_name = search_en_name
                second_search_name = search_cn_name
            else:
                first_search_name = search_cn_name
                second_search_name = search_en_name

        log.info("【Searcher】开始检索 %s ..." % first_search_name)
        media_list = self.search_medias(key_word=first_search_name,
                                        filter_args=filter_args,
                                        match_media=media_info,
                                        in_from=in_from)
        if len(media_list) == 0 and second_search_name and second_search_name != first_search_name:
            retry_message = "%s 未检索到资源,尝试通过 %s 重新检索 ..." % (
                first_search_name, second_search_name
            )
            if on_retry:
                on_retry(retry_message)
            log.info("【Searcher】%s" % retry_message)
            media_list = self.search_medias(key_word=second_search_name,
                                            filter_args=filter_args,
                                            match_media=media_info,
                                            in_from=in_from)
        return media_list

    def search_one_media(self, media_info,
                         in_from: SearchType,
                         no_exists: dict,
                         sites: list = None,
                         filters: dict = None,
                         user_name=None):
        """
        只检索和下载一个资源，用于精确检索下载，由Telegram或豆瓣调用
        :param media_info: 已识别的媒体信息
        :param in_from: 搜索渠道
        :param no_exists: 缺失的剧集清单
        :param sites: 检索哪些站点
        :param filters: 过滤条件，为空则不过滤
        :param user_name: 用户名
        :return: 请求的资源是否全部下载完整，如完整则返回媒体信息
                 请求的资源如果是剧集则返回下载后仍然缺失的季集信息
                 搜索到的结果数量
                 下载到的结果数量，如为None则表示未开启自动下载
        """
        if not media_info:
            return None, {}, 0, 0
        # 进度计数重置
        self.progress.start('search')
        try:
            filter_args = {"site": sites, "seeders": True}
            if filters:
                filter_args.update(filters)
            media_list = self.search_media_resources(media_info=media_info,
                                                     filters=filter_args,
                                                     in_from=in_from)

            if len(media_list) == 0:
                log.info("【Searcher】%s 未搜索到任何资源" % media_info.title)
                return None, no_exists, 0, 0
            else:
                if in_from in self.message.get_search_types():
                    # 保存搜索记录
                    self.dbhelper.delete_all_search_torrents()
                    # 搜索结果排序
                    media_list = sorted(media_list, key=lambda x: "%s%s%s%s" % (str(x.title).ljust(100, ' '),
                                                                                str(x.res_order).rjust(3, '0'),
                                                                                str(x.site_order).rjust(3, '0'),
                                                                                str(x.seeders).rjust(10, '0')),
                                        reverse=True)
                    # 插入数据库
                    self.dbhelper.insert_search_results(media_list)
                    # 远程渠道未开自动下载时返回
                    if not self._search_auto:
                        return None, no_exists, len(media_list), None
                # 择优下载
                download_items, left_medias = self.downloader.batch_download(in_from=in_from,
                                                                             media_list=media_list,
                                                                             need_tvs=no_exists,
                                                                             user_name=user_name)
                # 统计下载情况，下全了返回True，没下全返回False
                if not download_items:
                    log.info("【Searcher】%s 未下载到资源" % media_info.title)
                    return None, left_medias, len(media_list), 0
                else:
                    log.info("【Searcher】实际下载了 %s 个资源" % len(download_items))
                    # 还有剩下的缺失，说明没下完，返回False
                    if left_medias:
                        return None, left_medias, len(media_list), len(download_items)
                    # 全部下完了
                    else:
                        return download_items[0], no_exists, len(media_list), len(download_items)
        finally:
            self.progress.end('search')
