from functools import lru_cache

import requests
from lxml import etree

from app.utils import RequestUtils, ExceptionUtils
from app.utils.commons import singleton


@singleton
class DoubanWeb(object):

    _session = requests.Session()

    _movie_base = "https://movie.douban.com"
    _search_base = "https://search.douban.com"
    _page_limit = 50
    _timout = 5

    _weburls = {
        # 详情
        "detail": f"{_movie_base}/subject/%s",
        # 正在热映
        "nowplaying": f"{_movie_base}/cinema/nowplaying",
        # 即将上映
        "later": f"{_movie_base}/cinema/later",
        # 搜索
        "search": f"{_search_base}/movie/subject_search?search_text=%s",
        # TOP 250
        "top250": f"{_movie_base}/top250",
    }

    _webparsers = {
        "detail": {
            "title": "//span[@property='v:itemreviewed']/text()",
            "year": "//div[@id='content']//span[@class='year']/text()",
            "intro": "//span[@property='v:summary']/text()",
            "cover": "//div[@id='mainpic']//img/@src",
            "rate": "//strong[@property='v:average']/text()",
            "imdb": "//div[@id='info']/span[contains(text(), 'IMDb:')]/following-sibling::text()",
            "season": "//div[@id='info']/span[contains(text(), '季数')]/following-sibling::text()",
            "episode_num": "//div[@id='info']/span[contains(text(), '集数')]/following-sibling::text()"
        },
        "nowplaying": {
            "list": "//div[@id='nowplaying']//ul[@class='lists']/li",
            "item": {
                "id": "./@data-subject",
                "title": "./@data-title",
                "rate": "./@data-score",
                "cover": "./li[@class='poster']/a/img/@src",
                "year": "./@data-release"
            }
        },
        "later": {
            "list": "//div[@id='showing-soon']/div",
            "item": {
                "id": "./@data-subject",
                "title": "./div[@class='intro']/h3/a/text()]",
                "cover": "./a[class='thumb']/img/@src",
                "url": "./div[@class='intro']/h3/a/@href"
            }
        },
        "top250": {
            "list": "//ol[@class='grid_view']/li",
            "dates": "//div[@class='info']//span[@class='date']/text()",
            "item": {
                "title": "./div[@class='item']/div[@class='pic']/a/img/@alt",
                "cover": "./div[@class='item']/div[@class='pic']/a/img/@src",
                "url": "./div[@class='item']/div[@class='pic']/a/@href"
            }
        },
        "search": {
            "list": "//div[@class='item-root']",
            "item": {
                "title": "./div[@class='title']/a/text()",
                "url": "./div[@class='detail']/div[@class='title']/a/@href",
                "cover": "./a/img[class='cover']/@src",
                "intro": "./div[@class='detail']/div[@class='meta abstract']/text()",
                "rate": "./div[@class='detail']/div[@class='rating']/span[@class='rating_nums']/text()",
                "actor": "./div[@class='detail']/div[@class='meta abstract_2']/text()"
            }
        }
    }

    _jsonurls = {
        # 最新电影
        "movie_new": f"{_movie_base}/j/search_subjects?type=movie&tag=最新&page_limit={_page_limit}&page_start=%s",
        # 热门电影
        "movie_hot": f"{_movie_base}/j/search_subjects?type=movie&tag=热门&page_limit={_page_limit}&page_start=%s",
        # 高分电影
        "movie_rate": f"{_movie_base}/j/search_subjects?type=movie&tag=豆瓣高分&page_limit={_page_limit}&page_start=%s",
        # 热门电视剧
        "tv_hot": f"{_movie_base}/j/search_subjects?type=tv&tag=热门&page_limit={_page_limit}&page_start=%s",
        # 热门动漫
        "anime_hot": f"{_movie_base}/j/search_subjects?type=tv&tag=日本动画&page_limit={_page_limit}&page_start=%s",
        # 热门综艺
        "variety_hot": f"{_movie_base}/j/search_subjects?type=tv&tag=综艺&page_limit={_page_limit}&page_start=%s",
    }

    def __int__(self, cookie=None):
        pass

    @classmethod
    def __invoke_web(cls, url, cookie, *kwargs):
        req_url = cls._weburls.get(url)
        if not req_url:
            return None
        return RequestUtils(cookies=cookie,
                            session=cls._session,
                            timeout=cls._timout).get(url=req_url % kwargs)

    @classmethod
    def __invoke_json(cls, url, *kwargs):
        req_url = cls._jsonurls.get(url)
        if not req_url:
            return None
        req = RequestUtils(session=cls._session,
                           timeout=cls._timout).get_res(url=req_url % kwargs)
        return req.json() if req else None

    @staticmethod
    def __get_json(json):
        if not json:
            return None
        return json.get("subjects")

    @classmethod
    def __get_list(cls, url, html):
        if not url or not html:
            return None
        xpaths = cls._webparsers.get(url)
        if not xpaths:
            return None
        items = etree.HTML(html).xpath(xpaths.get("list"))
        if not items:
            return None
        result = []
        for item in items:
            obj = {}
            for key, value in xpaths.get("item").items():
                text = item.xpath(value)
                if text:
                    obj[key] = text[0]
            if obj:
                result.append(obj)
        return result

    @classmethod
    def __get_obj(cls, url, html):
        if not url or not html:
            return None
        xpaths = cls._webparsers.get(url)
        if not xpaths:
            return None
        obj = {}
        for key, value in xpaths.items():
            try:
                text = etree.HTML(html).xpath(value)
                if text:
                    obj[key] = text[0]
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return obj

    @classmethod
    @lru_cache(maxsize=256)
    def detail(cls, cookie, doubanid):
        """
        查询详情
        """
        return cls.__get_obj("detail", cls.__invoke_web("detail", cookie, doubanid))

    def nowplaying(self, cookie):
        """
        正在热映
        """
        return self.__get_list("nowplaying", self.__invoke_web("nowplaying", cookie))

    def later(self, cookie):
        """
        即将上映
        """
        return self.__get_list("later", self.__invoke_web("later", cookie))

    def search(self, cookie, keyword):
        """
        搜索
        """
        return self.__get_list("search", self.__invoke_web("search", cookie, keyword))

    def top250(self, cookie):
        """
        TOP 250
        """
        return self.__get_list("top250", self.__invoke_web("top250", cookie))

    def movie_new(self, start=0):
        """
        最新电影
        """
        return self.__get_json(self.__invoke_json("movie_new", start))

    def movie_hot(self, start=0):
        """
        热门电影
        """
        return self.__get_json(self.__invoke_json("movie_hot", start))

    def movie_rate(self, start=0):
        """
        高分电影
        """
        return self.__get_json(self.__invoke_json("movie_rate", start))

    def tv_hot(self, start=0):
        """
        热门电视剧
        """
        return self.__get_json(self.__invoke_json("tv_hot", start))

    def anime_hot(self, start=0):
        """
        热门动漫
        """
        return self.__get_json(self.__invoke_json("anime_hot", start))

    def variety_hot(self, start=0):
        """
        热门综艺
        """
        return self.__get_json(self.__invoke_json("variety_hot", start))
