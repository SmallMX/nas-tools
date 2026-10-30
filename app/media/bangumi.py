from datetime import datetime
from functools import lru_cache
from copy import deepcopy

import requests
from cacheout import Cache

from app.utils import RequestUtils
from app.utils.types import MediaType


class BangumiRecommendationError(ValueError):
    """The public calendar could not return a valid recommendation list."""


class Bangumi(object):
    """
    https://bangumi.github.io/api/
    """

    _urls = {
        "calendar": "calendar",
        "detail": "v0/subjects/%s",
    }
    _base_url = "https://api.bgm.tv/"
    _req = RequestUtils(session=requests.Session())
    _page_num = 30
    _calendar_cache = Cache(maxsize=1, ttl=300)

    def __init__(self):
        pass

    @classmethod
    @lru_cache(maxsize=128)
    def __invoke(cls, url, **kwargs):
        req_url = cls._base_url + url
        params = {}
        if kwargs:
            params.update(kwargs)
        resp = cls._req.get_res(url=req_url, params=params)
        return resp.json() if resp else None

    def calendar(self):
        """
        获取每日放送
        """
        cached = self._calendar_cache.get("calendar")
        if cached is not None:
            return deepcopy(cached)
        response = self._req.get_res(url=self._base_url + self._urls["calendar"])
        if response is None or response.status_code != 200:
            raise BangumiRecommendationError("Bangumi 每日放送加载失败，请稍后重试。")
        try:
            infos = response.json()
        except (TypeError, ValueError) as error:
            raise BangumiRecommendationError("Bangumi 返回的数据格式异常，请稍后重试。") from error
        if not isinstance(infos, list) or any(
                not isinstance(info, dict) or not isinstance(info.get("weekday"), dict)
                or not isinstance(info.get("items"), list) for info in infos):
            raise BangumiRecommendationError("Bangumi 返回的数据格式异常，请稍后重试。")
        if any(info["items"] for info in infos):
            self._calendar_cache.set("calendar", deepcopy(infos))
        return infos

    def detail(self, bid):
        """
        获取番剧详情
        """
        return self.__invoke(self._urls["detail"] % bid, _ts=datetime.strftime(datetime.now(), '%Y%m%d'))

    @staticmethod
    def __dict_item(item, weekday):
        """
        转换为字典
        """
        bid = item.get("id")
        detail = item.get("url")
        title = item.get("name_cn") or item.get("name")
        air_date = item.get("air_date")
        rating = item.get("rating")
        if rating:
            score = rating.get("score")
        else:
            score = 0
        images = item.get("images")
        if images:
            image = images.get("large")
        else:
            image = ''
        summary = item.get("summary")
        return {
            'id': "BG:%s" % bid,
            'orgid': bid,
            'title': title,
            'year': air_date[:4] if air_date else "",
            'type': 'TV',
            'media_type': MediaType.TV.value,
            'vote': score,
            'image': image,
            'overview': summary,
            'url': detail,
            'weekday': weekday
        }

    def get_bangumi_calendar(self, page=1, week=None):
        """
        获取每日放送
        """
        try:
            page = int(page)
            week = int(week) if week else None
        except (TypeError, ValueError) as error:
            raise BangumiRecommendationError("每日放送的页码或星期参数无效") from error
        if page < 1 or (week is not None and not 1 <= week <= 7):
            raise BangumiRecommendationError("每日放送的页码或星期参数无效")
        infos = self.calendar()
        start_pos = (page - 1) * self._page_num
        ret_list = []
        for info in infos:
            weeknum = info.get("weekday", {}).get("id")
            if week and str(weeknum) != str(week):
                continue
            weekday = info.get("weekday", {}).get("cn")
            items = info.get("items")
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    ret_list.append(self.__dict_item(item, weekday))
        return ret_list[start_pos:start_pos + self._page_num]
