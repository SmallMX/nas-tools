import base64
import json
import re
from urllib.parse import urlencode, urljoin

import log

from app.utils import RequestUtils, StringUtils
from app.utils.types import MediaType
from config import Config


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _timestamp(value):
    if value is None or value == "":
        return value
    if isinstance(value, str) and not value.isdigit():
        return value
    timestamp = _int(value)
    if timestamp > 100000000000:
        timestamp //= 1000
    return StringUtils.timestamp_to_date(timestamp)


def _dynamic_download_url(url, method="get", headers=None, params=None,
                          result=None, cookie=False, proxy=False):
    request = {
        "method": method,
        "header": headers or {},
        "cookie": cookie,
        "proxy": proxy
    }
    if params:
        request["params"] = params
    if result:
        request["result"] = result
    encoded = base64.b64encode(json.dumps(request).encode("utf-8")).decode("utf-8")
    return f"[{encoded}]{url}"


class _ApiSpider:
    def __init__(self, indexer):
        self.indexer = indexer
        self.indexer_id = indexer.id
        self.name = indexer.name
        self.domain = indexer.domain.rstrip("/") + "/"
        self.host = StringUtils.get_url_domain(self.domain)
        self.cookie = indexer.cookie
        self.ua = indexer.ua or Config().get_ua()
        self.apikey = indexer.apikey
        self.proxy = Config().get_proxies() if indexer.proxy else None
        self.timeout = indexer.timeout or 15
        self.result_num = _int(Config().get_config("pt").get("site_search_result_num")) or 100

    def _request(self, headers=None, cookie=True):
        return RequestUtils(headers=headers or self.ua,
                            cookies=self.cookie if cookie else None,
                            proxies=self.proxy,
                            timeout=self.timeout)

    def _warn(self, response, action="搜索"):
        if response is None:
            log.warn(f"【INDEXER】{self.name} {action}失败，无法连接 {self.host}")
        else:
            log.warn(f"【INDEXER】{self.name} {action}失败，错误码：{response.status_code}")

    def _json(self, response):
        try:
            return response.json()
        except (TypeError, ValueError) as err:
            log.warn(f"【INDEXER】{self.name} 返回数据不是有效 JSON：{err}")
            return {}

    @staticmethod
    def _category(value, movie_categories, tv_categories):
        if value in tv_categories and value not in movie_categories:
            return MediaType.TV.value
        if value in movie_categories:
            return MediaType.MOVIE.value
        return MediaType.UNKNOWN.value


class MTorrentSpider(_ApiSpider):
    _movie_categories = {"401", "404", "405", "419", "420", "421", "439"}
    _tv_categories = {"402", "403", "404", "405", "435", "438"}
    _labels = {
        "0": "", "1": "DIY", "2": "国配", "3": "DIY 国配",
        "4": "中字", "5": "DIY 中字", "6": "国配 中字", "7": "DIY 国配 中字"
    }

    @staticmethod
    def _download_factor(discount):
        return {
            "FREE": 0, "PERCENT_50": 0.5, "PERCENT_70": 0.3,
            "_2X_FREE": 0, "_2X_PERCENT_50": 0.5
        }.get(discount, 1)

    @staticmethod
    def _upload_factor(discount):
        return {"_2X": 2, "_2X_FREE": 2, "_2X_PERCENT_50": 2}.get(discount, 1)

    @staticmethod
    def _imdb_id(value):
        match = re.search(r"tt\d+", value or "")
        return match.group(0) if match else ""

    def _download_url(self, torrent_id):
        url = f"https://api.{self.host}/api/torrent/genDlToken"
        headers = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "x-api-key": "{apikey}"
        }
        return _dynamic_download_url(url=url,
                                     method="post",
                                     headers=headers,
                                     params={"id": torrent_id},
                                     result="data",
                                     proxy=bool(self.proxy))

    def search(self, keyword=None, mtype=None, page=0):
        if not self.apikey:
            log.warn(f"【INDEXER】{self.name} 未配置 API Key，无法搜索")
            return []
        if mtype in (MediaType.TV, MediaType.ANIME):
            categories = sorted(self._tv_categories)
        elif mtype == MediaType.MOVIE:
            categories = sorted(self._movie_categories)
        else:
            categories = []
        if keyword and keyword.startswith("tt"):
            keyword = f"https://www.imdb.com/title/{keyword}"
        params = {
            "keyword": keyword or "",
            "categories": categories,
            "pageNumber": int(page or 0) + 1,
            "pageSize": min(self.result_num, 100),
            "visible": 1
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.ua,
            "x-api-key": self.apikey
        }
        response = self._request(headers=headers, cookie=False).post_res(
            url=f"https://api.{self.host}/api/torrent/search", json=params)
        if not response or response.status_code != 200:
            self._warn(response)
            return []
        results = self._json(response).get("data", {}).get("data") or []
        torrents = []
        for item in results:
            status = item.get("status") or {}
            discount = status.get("discount")
            labels = item.get("labelsNew") or []
            if not labels:
                labels = (self._labels.get(str(item.get("labels") or "0")) or "").split()
            torrent = {
                "indexer": self.indexer_id,
                "title": item.get("name"),
                "description": item.get("smallDescr"),
                "enclosure": self._download_url(item.get("id")),
                "pubdate": _timestamp(item.get("createdDate")),
                "size": _int(item.get("size")),
                "seeders": _int(status.get("seeders")),
                "peers": _int(status.get("leechers")),
                "grabs": _int(status.get("timesCompleted")),
                "downloadvolumefactor": self._download_factor(discount),
                "uploadvolumefactor": self._upload_factor(discount),
                "page_url": urljoin(self.domain, f"detail/{item.get('id')}"),
                "imdbid": self._imdb_id(item.get("imdb")),
                "labels": labels,
                "category": self._category(str(item.get("category")),
                                             self._movie_categories,
                                             self._tv_categories)
            }
            if status.get("discountEndTime"):
                torrent["freedate"] = _timestamp(status.get("discountEndTime"))
            promotion = status.get("promotionRule") or {}
            if promotion:
                torrent["downloadvolumefactor"] = self._download_factor(promotion.get("discount"))
                if promotion.get("endTime"):
                    torrent["freedate"] = _timestamp(promotion.get("endTime"))
            single_free = status.get("mallSingleFree") or {}
            if single_free.get("status") == "ONGOING":
                torrent["downloadvolumefactor"] = 0
                if single_free.get("endDate"):
                    torrent["freedate"] = _timestamp(single_free.get("endDate"))
            torrents.append(torrent)
        return torrents


class YemaSpider(_ApiSpider):
    _movie_categories = {4}
    _tv_categories = {5, 6, 13, 14, 15, 16, 17}
    _labels = {
        "1": "禁转", "2": "首发", "3": "官方", "4": "自制",
        "5": "国语", "6": "中字", "7": "粤语", "8": "英字",
        "9": "HDR10", "10": "杜比视界", "11": "分集", "12": "完结"
    }

    def search(self, keyword=None, mtype=None, page=0):
        params = {
            "pageParam": {
                "current": int(page or 0) + 1,
                "pageSize": min(self.result_num, 40),
                "total": min(self.result_num, 40)
            },
            "sorter": {}
        }
        if keyword:
            params["keyword"] = keyword
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*"
        }
        response = self._request(headers=headers).post_res(
            url=urljoin(self.domain, "api/torrent/fetchOpenTorrentList"), json=params)
        if not response or response.status_code != 200:
            self._warn(response)
            return []
        torrents = []
        for item in self._json(response).get("data") or []:
            labels = [self._labels.get(str(label)) for label in (item.get("tagList") or [])]
            torrents.append({
                "indexer": self.indexer_id,
                "title": item.get("showName"),
                "description": item.get("shortDesc"),
                "enclosure": urljoin(self.domain, f"api/torrent/download?id={item.get('id')}"),
                "pubdate": StringUtils.unify_datetime_str(item.get("listingTime")),
                "size": _int(item.get("fileSize")),
                "seeders": _int(item.get("seedNum")),
                "peers": _int(item.get("leechNum")),
                "grabs": _int(item.get("completedNum")),
                "downloadvolumefactor": {"free": 0, "half": 0.5}.get(
                    item.get("downloadPromotion"), 1),
                "uploadvolumefactor": {"one_half": 1.5, "double_upload": 2}.get(
                    item.get("uploadPromotion"), 1),
                "freedate": StringUtils.unify_datetime_str(item.get("downloadPromotionEndTime")),
                "page_url": urljoin(self.domain, f"#/torrent/detail/{item.get('id')}/"),
                "labels": [label for label in labels if label],
                "category": self._category(item.get("categoryId"),
                                             self._movie_categories,
                                             self._tv_categories)
            })
        return torrents


class HaiDanSpider(_ApiSpider):
    _movie_categories = {"401", "404", "405"}
    _tv_categories = {"402", "403", "404", "405"}
    _download_factors = {"1": 1, "2": 0, "3": 1, "4": 0, "5": 0.5, "6": 0.5, "7": 0.3}
    _upload_factors = {"1": 1, "2": 1, "3": 2, "4": 2, "5": 1, "6": 2, "7": 1}

    def search(self, keyword=None, mtype=None, page=0):
        if not self.cookie:
            log.warn(f"【INDEXER】{self.name} 未配置 Cookie，无法搜索")
            return []
        if mtype in (MediaType.TV, MediaType.ANIME):
            categories = sorted(self._tv_categories)
        elif mtype == MediaType.MOVIE:
            categories = sorted(self._movie_categories)
        else:
            categories = []
        params = urlencode({
            "isapi": "1",
            "search_area": "4" if keyword and keyword.startswith("tt") else "0",
            "search": keyword or "",
            "search_mode": "0",
            "cat": ",".join(categories)
        })
        response = self._request().get_res(url=f"{urljoin(self.domain, 'torrents.php')}?{params}")
        if not response or response.status_code != 200:
            self._warn(response)
            return []
        result = self._json(response)
        if result.get("code") != 0:
            log.warn(f"【INDEXER】{self.name} 搜索失败：{result.get('msg')}")
            return []
        torrents = []
        for torrent_id, item in (result.get("data") or {}).items():
            category_id = str(item.get("category") or "")
            torrents.append({
                "indexer": self.indexer_id,
                "title": item.get("name"),
                "description": item.get("small_descr"),
                "enclosure": urljoin(self.domain, item.get("url") or ""),
                "pubdate": _timestamp(item.get("added")),
                "size": _int(item.get("size")),
                "seeders": _int(item.get("seeders")),
                "peers": _int(item.get("leechers")),
                "grabs": _int(item.get("times_completed")),
                "downloadvolumefactor": self._download_factors.get(str(item.get("sp_state")), 1),
                "uploadvolumefactor": self._upload_factors.get(str(item.get("sp_state")), 1),
                "page_url": urljoin(self.domain,
                                    f"details.php?group_id={item.get('group_id')}&torrent_id={torrent_id}"),
                "labels": [],
                "category": self._category(category_id,
                                             self._movie_categories,
                                             self._tv_categories)
            })
        return torrents


class HDDolbySpider(_ApiSpider):
    _movie_categories = {401, 405}
    _tv_categories = {402, 403, 404, 405}
    _labels = {
        "gf": "官方", "gy": "国语", "yy": "粤语", "ja": "日语", "ko": "韩语",
        "zz": "中文字幕", "jz": "禁转", "xz": "限转", "diy": "DIY", "sf": "首发",
        "yq": "应求", "m0": "零魔", "yc": "原创", "gz": "官字", "db": "Dolby Vision",
        "hdr10": "HDR10", "hdrm": "HDR10+", "tx": "特效", "lz": "连载", "wj": "完结",
        "hdrv": "HDR Vivid", "hlg": "HLG", "hq": "高码率", "hfr": "高帧率"
    }

    def search(self, keyword=None, mtype=None, page=0):
        if not self.apikey:
            log.warn(f"【INDEXER】{self.name} 未配置 API Key，无法搜索")
            return []
        if mtype in (MediaType.TV, MediaType.ANIME):
            categories = sorted(self._tv_categories)
        elif mtype == MediaType.MOVIE:
            categories = sorted(self._movie_categories)
        else:
            categories = sorted(self._movie_categories | self._tv_categories)
        params = {
            "keyword": keyword or "",
            "page_number": int(page or 0),
            "page_size": min(self.result_num, 100),
            "categories": categories,
            "visible": 1
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": self.ua,
            "x-api-key": self.apikey
        }
        response = self._request(headers=headers).post_res(
            url=f"https://api.{self.host}/api/v1/torrent/search", json=params)
        if not response or response.status_code != 200:
            self._warn(response)
            return []
        result = self._json(response)
        if result.get("error"):
            log.warn(f"【INDEXER】{self.name} 搜索失败：{result.get('error')}")
            return []
        torrents = []
        for item in result.get("data") or []:
            promotion = _int(item.get("promotion_time_type"))
            labels = [self._labels.get(label) for label in str(item.get("tags") or "").split(";")]
            torrents.append({
                "indexer": self.indexer_id,
                "title": item.get("name"),
                "description": item.get("small_descr"),
                "enclosure": urljoin(
                    self.domain, f"download.php?id={item.get('id')}&downhash={item.get('downhash')}"),
                "pubdate": item.get("added"),
                "size": _int(item.get("size")),
                "seeders": _int(item.get("seeders")),
                "peers": _int(item.get("leechers")),
                "grabs": _int(item.get("times_completed")),
                "downloadvolumefactor": {2: 0, 5: 0.5, 7: 0.3}.get(promotion, 1),
                "uploadvolumefactor": {3: 2, 4: 2, 6: 2}.get(promotion, 1),
                "freedate": item.get("promotion_until"),
                "page_url": urljoin(self.domain, f"details.php?id={item.get('id')}&hit=1"),
                "labels": [label for label in labels if label],
                "category": self._category(item.get("category"),
                                             self._movie_categories,
                                             self._tv_categories)
            })
        return torrents


class RousiSpider(_ApiSpider):
    def _download_url(self, torrent_id):
        headers = {"Authorization": "Bearer {apikey}", "Accept": "application/json"}
        return _dynamic_download_url(
            url=f"https://{self.host}/api/v1/torrents/{torrent_id}",
            headers=headers,
            result="data.download_url",
            proxy=bool(self.proxy))

    def search(self, keyword=None, mtype=None, page=0):
        if not self.apikey:
            log.warn(f"【INDEXER】{self.name} 未配置 API Key/Passkey，无法搜索")
            return []
        params = {"page": int(page or 0) + 1, "page_size": min(self.result_num, 100)}
        if keyword:
            params["keyword"] = keyword
        if mtype == MediaType.MOVIE:
            params["category"] = "movie"
        elif mtype in (MediaType.TV, MediaType.ANIME):
            params["category"] = "tv"
        headers = {"Authorization": f"Bearer {self.apikey}", "Accept": "application/json"}
        response = self._request(headers=headers, cookie=False).get_res(
            url=f"https://{self.host}/api/v1/torrents", params=params)
        if not response or response.status_code != 200:
            self._warn(response)
            return []
        result = self._json(response)
        if result.get("code") != 0:
            log.warn(f"【INDEXER】{self.name} 搜索失败：{result.get('message')}")
            return []
        torrents = []
        for item in result.get("data", {}).get("torrents") or []:
            category = item.get("category")
            if isinstance(category, dict):
                category = category.get("slug") or category.get("name")
            category = str(category or "").lower()
            if category == "movie":
                media_type = MediaType.MOVIE.value
            elif category == "tv":
                media_type = MediaType.TV.value
            else:
                media_type = MediaType.UNKNOWN.value
            promotion = item.get("promotion") or {}
            active = promotion.get("is_active")
            torrents.append({
                "indexer": self.indexer_id,
                "title": item.get("title"),
                "description": item.get("subtitle"),
                "enclosure": self._download_url(item.get("id")),
                "pubdate": StringUtils.unify_datetime_str(item.get("created_at")),
                "size": _int(item.get("size")),
                "seeders": _int(item.get("seeders")),
                "peers": _int(item.get("leechers")),
                "grabs": _int(item.get("downloads")),
                "downloadvolumefactor": _float(promotion.get("down_multiplier")) if active else 1,
                "uploadvolumefactor": _float(promotion.get("up_multiplier")) if active else 1,
                "freedate": StringUtils.unify_datetime_str(promotion.get("until")) if active else None,
                "page_url": f"https://{self.host}/torrent/{item.get('uuid')}",
                "labels": [],
                "category": media_type
            })
        return torrents
