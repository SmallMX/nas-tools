"""Public streaming catalog adapters used by the discovery pages."""

import math
import re
from copy import deepcopy
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from cacheout import Cache

from app.utils import RequestUtils


class StreamingDiscoveryError(ValueError):
    """A catalog request could not produce a valid page."""


class StreamingDiscovery:
    """Normalize public catalog pages without treating platform IDs as TMDB IDs."""

    _cache = Cache(maxsize=128, ttl=300)
    _names = {"tencent": "腾讯视频", "iqiyi": "爱奇艺", "mgtv": "芒果视频"}
    _categories = {
        "tencent": {"tv": "100113", "movie": "100173", "variety": "100109",
                    "anime": "100119", "children": "100150", "documentary": "100105"},
        "iqiyi": {"tv": "2", "movie": "1", "variety": "6", "anime": "4"},
        "mgtv": {"tv": "2", "movie": "3", "variety": "1", "anime": "50",
                 "children": "10", "documentary": "51", "education": "115"},
    }
    _sorts = {
        "tencent": {"hot": "75", "new": "79", "score": "85"},
        "iqiyi": {"hot": "11", "new": "4", "score": "8"},
        "mgtv": {"hot": "c2", "new": "c1"},
    }
    _tencent_sorts = {
        "tv": {"hot": "75", "new": "79", "score": "85"},
        "movie": {"hot": "75", "new": "83", "score": "81"},
        "variety": {"hot": "75", "new": "23", "score": "85"},
        "anime": {"hot": "75", "new": "23", "score": "85"},
        "children": {"hot": "75", "new": "76"},
        "documentary": {"hot": "75", "new": "74", "score": "85"},
    }
    _labels = {"tv": "电视剧", "movie": "电影", "variety": "综艺", "anime": "动漫",
               "children": "少儿", "documentary": "纪录片", "education": "教育"}
    _origins = {"tencent": "https://v.qq.com/", "iqiyi": "https://www.iqiyi.com/",
                "mgtv": "https://www.mgtv.com/"}
    _ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    def discover(self, source, page=1, params=None):
        """Return one validated page, caching successful responses for five minutes."""
        if not isinstance(source, str) or source not in self._categories:
            raise StreamingDiscoveryError("不支持的探索来源")
        if isinstance(page, bool) or not re.fullmatch(r"[0-9]+", str(page)) or not 1 <= int(page) <= 10:
            raise StreamingDiscoveryError("页码必须是 1 到 10 的整数")
        page = int(page)
        if params is None:
            params = {}
        if not isinstance(params, dict) or set(params) - {"category", "sort"}:
            raise StreamingDiscoveryError("不支持的探索筛选参数")
        category = params.get("category") or "tv"
        sort = params.get("sort") or "hot"
        if not isinstance(category, str) or category not in self._categories[source]:
            raise StreamingDiscoveryError("不支持的影视分类")
        if not isinstance(sort, str) or sort not in self._sorts[source]:
            raise StreamingDiscoveryError("不支持的排序方式")
        if source == "tencent" and sort not in self._tencent_sorts[category]:
            raise StreamingDiscoveryError("该分类不支持此排序方式")
        key = (source, category, sort, page)
        cached = self._cache.get(key)
        if cached is not None:
            return deepcopy(cached)
        items, has_more = getattr(self, f"_{source}")(category, sort, page)
        unique = {}
        for item in items:
            if item and item["source_id"] not in unique:
                unique[item["source_id"]] = item
        result = {"Items": list(unique.values()), "has_more": has_more}
        self._cache.set(key, deepcopy(result))
        return result

    def _request(self, source, url, params=None, body=None):
        """Check transport and JSON failures without exposing remote response bodies."""
        client = RequestUtils(headers={"User-Agent": self._ua,
                                       "Referer": self._origins[source],
                                       "Content-Type": "application/json"}, timeout=15)
        response = client.post(url, json=body) if body is not None else client.get_res(url, params=params)
        name = self._names[source]
        if response is None:
            raise StreamingDiscoveryError(f"无法连接{name}，请稍后重试")
        if response.status_code != 200:
            raise StreamingDiscoveryError(f"{name}请求失败（HTTP {response.status_code}），请稍后重试")
        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            raise StreamingDiscoveryError(f"{name}返回了无效数据，请稍后重试") from error
        if not isinstance(payload, dict):
            raise StreamingDiscoveryError(f"{name}返回的数据格式异常，请稍后重试")
        return payload

    @staticmethod
    def _url(value, domain=None):
        """Keep web URLs only; detail links must belong to the selected platform."""
        if not isinstance(value, str) or not value.strip():
            return ""
        value = value.strip()
        if value.startswith("//"):
            value = "https:" + value
        try:
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                return ""
            if domain and parsed.hostname != domain and not parsed.hostname.endswith("." + domain):
                return ""
            return urlunsplit(parsed._replace(scheme="https"))
        except ValueError:
            return ""

    def _item(self, source, category, source_id, title, image="", year="", vote=0, overview="", detail_url=""):
        """Produce the existing media-card contract with a separate source identity."""
        if not isinstance(source_id, (str, int)) or isinstance(source_id, bool) or not source_id:
            return None
        if not isinstance(title, str) or not title.strip():
            return None
        source_id = str(source_id)
        try:
            score = float(vote or 0)
            score = round(score, 1) if math.isfinite(score) and 0 <= score <= 10 else 0
        except (TypeError, ValueError):
            score = 0
        year_match = re.match(r"(?:19|20)\d{2}", str(year or ""))
        return {"id": "", "source_id": source_id, "title": title.strip(),
                "type": "MOV" if category == "movie" else "TV", "media_type": self._labels[category],
                "year": year_match.group() if year_match else "", "image": self._url(image),
                "vote": score, "overview": overview if isinstance(overview, str) else "",
                "site": self._names[source], "detail_url": detail_url}

    def _tencent(self, category, sort, page):
        """Use the returned page-context key instead of a hard-coded dataset ID."""
        url = ("https://pbaccess.video.qq.com/trpc.universal_backend_service."
               "page_server_rpc.PageServer/GetPageData?" + urlencode({
                   "video_appid": "1000005", "vplatform": "2", "vversion_name": "8.9.10",
                   "new_mark_label_enabled": "1"}))
        body = {"page_params": {"channel_id": self._categories["tencent"][category],
                                "page_type": "channel_operation", "page_id": "channel_list_second_page",
                                "filter_params": urlencode({"sort": self._tencent_sorts[category][sort]})}}

        def fetch():
            payload = self._request("tencent", url, body=body)
            data = payload.get("data")
            if str(payload.get("ret")) != "0" or not isinstance(data, dict):
                raise StreamingDiscoveryError("腾讯视频片库暂不可用，请稍后重试")
            return data

        data = fetch()
        if page > 1:
            context = data.get("next_page_context")
            if not isinstance(context, dict):
                raise StreamingDiscoveryError("腾讯视频分页信息异常，请稍后重试")
            key = next((key for key in context if key.startswith("_ds_cli_") and key.endswith("_page")), None)
            if key is None:
                if not data.get("has_next_page"):
                    return [], False
                raise StreamingDiscoveryError("腾讯视频分页信息异常，请稍后重试")
            body["page_context"] = {key: str(page - 1)}
            data = fetch()
        modules = data.get("module_list_datas")
        if not isinstance(modules, list):
            raise StreamingDiscoveryError("腾讯视频片库数据格式异常，请稍后重试")
        result = []
        for group in modules:
            if not isinstance(group, dict):
                continue
            module_datas = group.get("module_datas") or []
            if not isinstance(module_datas, list):
                raise StreamingDiscoveryError("腾讯视频片库数据格式异常，请稍后重试")
            for module in module_datas:
                if not isinstance(module, dict):
                    continue
                listing = module.get("item_data_lists") or {}
                if not isinstance(listing, dict):
                    continue
                item_datas = listing.get("item_datas") or []
                if not isinstance(item_datas, list):
                    raise StreamingDiscoveryError("腾讯视频片库数据格式异常，请稍后重试")
                for entry in item_datas:
                    if not isinstance(entry, dict) or str(entry.get("item_type")) != "2":
                        continue
                    item = entry.get("item_params")
                    if not isinstance(item, dict):
                        continue
                    cid = item.get("cid")
                    result.append(self._item(
                        "tencent", category, cid, item.get("title"),
                        image=item.get("new_pic_vt") or item.get("pic_url") or item.get("image_url"),
                        year=item.get("year"), vote=item.get("score"),
                        overview=item.get("description") or item.get("second_title"),
                        detail_url=f"https://v.qq.com/x/cover/{quote(str(cid), safe='')}.html" if cid else ""))
        context = data.get("next_page_context") or {}
        has_context = isinstance(context, dict) and any(
            key.startswith("_ds_cli_") and key.endswith("_page") for key in context)
        return result, bool(any(result) and has_context and data.get("has_next_page") in (True, 1, "1"))

    def _iqiyi(self, category, sort, page):
        """Use the public PC catalog endpoint, which does not require account cookies."""
        channel = self._categories["iqiyi"][category]
        payload = self._request("iqiyi", "https://pcw-api.iqiyi.com/search/recommend/list", params={
            "channel_id": channel, "data_type": "1", "mode": self._sorts["iqiyi"][sort],
            "page_id": str(page), "ret_num": "30"})
        data = payload.get("data")
        if payload.get("code") != "A00000" or not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise StreamingDiscoveryError("爱奇艺片库暂不可用，请稍后重试")
        result = []
        for item in data["list"]:
            if not isinstance(item, dict) or str(item.get("channelId")) != channel:
                continue
            title = item.get("name") or item.get("title")
            if category == "tv" and re.search(r"第\s*\d+\s*集", str(item.get("title") or "")):
                continue
            image = item.get("imageUrl")
            sizes = item.get("imageSize")
            if isinstance(image, str) and isinstance(sizes, list) and "579_772" in sizes:
                image = re.sub(r"(?:_\d+_\d+)?\.(jpg|png|webp)$", r"_579_772.\1", image)
            detail_url = self._url(item.get("playUrl"), "iqiyi.com")
            # Keep a useful official destination even when a catalog omits its play URL.
            if not detail_url and title:
                detail_url = "https://so.iqiyi.com/so/q_" + quote(str(title), safe="")
            result.append(self._item(
                "iqiyi", category, item.get("albumId"), title, image=image,
                year=item.get("period"), vote=item.get("score"), overview=item.get("description"),
                detail_url=detail_url))
        return result, data.get("has_next") in (True, 1, "1")

    def _mgtv(self, category, sort, page):
        """Read Mango TV's explicit end-of-list marker."""
        payload = self._request("mgtv", "https://pianku.api.mgtv.com/rider/list/pcweb/v3", params={
            "allowedRC": "1", "platform": "pcweb", "channelId": self._categories["mgtv"][category],
            "pn": str(page), "pc": "30", "hudong": "1", "_support": "10000000",
            "sort": self._sorts["mgtv"][sort]})
        data = payload.get("data")
        if str(payload.get("code")) != "200" or not isinstance(data, dict) or not isinstance(data.get("hitDocs"), list):
            raise StreamingDiscoveryError("芒果视频片库暂不可用，请稍后重试")
        result = []
        for item in data["hitDocs"]:
            if not isinstance(item, dict):
                continue
            cid = item.get("clipId")
            result.append(self._item(
                "mgtv", category, cid, item.get("title"), image=item.get("img"),
                year=item.get("year"), vote=item.get("score") or item.get("zhihuScore"),
                overview=item.get("story"),
                detail_url=f"https://www.mgtv.com/b/{quote(str(cid), safe='')}/" if cid else ""))
        return result, data.get("hasMore") in (True, 1, "1", "true")
