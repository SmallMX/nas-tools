"""Public streaming catalog adapters used by the discovery pages."""

import math
import json
import re
from copy import deepcopy
from datetime import date
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from cacheout import Cache
from lxml import etree, html

from app.utils import RequestUtils


class StreamingDiscoveryError(ValueError):
    """A catalog request could not produce a valid page."""


class StreamingDiscovery:
    """Normalize public catalog pages without treating platform IDs as TMDB IDs."""

    _cache = Cache(maxsize=128, ttl=300)
    _filters_cache = Cache(maxsize=64, ttl=1800)
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
    _filter_keys = {
        "tencent": {"itype", "ipay", "iarea", "iyear", "theater", "award", "recommend", "recommend_1",
                    "recommend_2", "recommend_3", "producer", "characteristic", "exclusive", "anime_status",
                    "item", "all", "gender", "language", "child_ip", "itrailer", "iregion", "pay"},
        "mgtv": {"kind", "area", "year", "feature", "chargeInfo", "edition", "fitAge"},
        "iqiyi": {"tag_18000", "tag_18001", "tag_27396", "tag_18002", "tag_18003", "tag_18005",
                  "tag_30219", "tag_30225", "tag_32795", "tag_18013", "tag_18014", "tag_33162",
                  "market_release_date_level", "is_purchase", "is_album_finished"},
    }

    def filters(self, source, category="tv"):
        """Read category-specific choices from the same public catalogs as MoviePilot."""
        if not isinstance(source, str) or source not in self._categories:
            raise StreamingDiscoveryError("不支持的探索来源")
        if not isinstance(category, str) or category not in self._categories[source]:
            raise StreamingDiscoveryError("不支持的影视分类")
        cache_key = (source, category)
        cached = self._filters_cache.get(cache_key)
        if cached is not None:
            return deepcopy(cached)
        sorts = self._tencent_sorts[category] if source == "tencent" else self._sorts[source]
        names = {"hot": "最热", "new": "最新", "score": "高分"}
        result = [
            {"key": "category", "name": "种类", "default": "tv", "options": [
                {"value": key, "name": self._labels[key]} for key in self._categories[source]]},
            {"key": "sort", "name": "排序", "default": "hot", "options": [
                {"value": key, "name": names[key]} for key in sorts]},
        ]
        groups = getattr(self, f"_{source}_filters")(category)
        if not groups:
            raise StreamingDiscoveryError(f"{self._names[source]}筛选信息暂不可用，请稍后重试")
        result.extend(groups)
        self._filters_cache.set(cache_key, deepcopy(result))
        return result

    @staticmethod
    def _filter_group(key, name, options):
        """Keep a stable, explicit all-option and discard malformed choices."""
        choices = {"": {"value": "", "name": "全部"}}
        for value, label in options:
            if isinstance(value, (str, int)) and isinstance(label, str) and label and value not in (None, "", "-1"):
                if label.startswith("全部"):
                    continue
                choices[str(value)] = {"value": str(value), "name": label}
        if len(choices) < 2:
            return None
        return {"key": key, "name": name if isinstance(name, str) else key,
                "default": "", "options": list(choices.values())}

    def _tencent_filters(self, category):
        payload = self._request("tencent", self._tencent_url(), body={"page_params": {
            "channel_id": self._categories["tencent"][category], "page_type": "channel_operation",
            "page_id": "channel_list_second_page"}})
        data = payload.get("data")
        if str(payload.get("ret")) != "0" or not isinstance(data, dict):
            raise StreamingDiscoveryError("腾讯视频筛选信息暂不可用，请稍后重试")
        groups = {}
        for entry in self._tencent_entries(data):
            item = entry.get("item_params")
            if str(entry.get("item_type")) != "11" or not isinstance(item, dict):
                continue
            key = item.get("index_item_key")
            if not isinstance(key, str) or key not in self._filter_keys["tencent"]:
                continue
            group = groups.setdefault(key, {"name": item.get("index_name") or key, "options": []})
            group["options"].append((item.get("option_value"), item.get("option_name")))
        return [row for key, group in groups.items()
                if (row := self._filter_group(key, group["name"], group["options"]))]

    def _mgtv_filters(self, category):
        payload = self._request("mgtv", "https://pianku.api.mgtv.com/rider/config/channel/v1", params={
            "allowedRC": "1", "platform": "pcweb", "channelId": self._categories["mgtv"][category],
            "_support": "10000000"})
        data = payload.get("data")
        if str(payload.get("code")) != "200" or not isinstance(data, dict) or not isinstance(data.get("listItems"), list):
            raise StreamingDiscoveryError("芒果视频筛选信息暂不可用，请稍后重试")
        result = []
        for item in data["listItems"]:
            if (not isinstance(item, dict) or not isinstance(item.get("eName"), str)
                    or item["eName"] not in self._filter_keys["mgtv"]):
                continue
            options = item.get("items")
            if not isinstance(options, list):
                raise StreamingDiscoveryError("芒果视频筛选信息格式异常，请稍后重试")
            group = self._filter_group(item["eName"], item.get("typeName") or item["eName"],
                                       [(option.get("tagId"), option.get("tagName"))
                                        for option in options if isinstance(option, dict)])
            if group:
                result.append(group)
        return result

    def _iqiyi_filters(self, category):
        channel = self._categories["iqiyi"][category]
        page = self._request("iqiyi", f"https://list.iqiyi.com/www/{channel}/-------------11-1-1-iqiyi--.html",
                             text=True)
        try:
            nodes = html.fromstring(page).xpath('//*[@is="i71-list-category"]')
            if not nodes:
                raise ValueError("Missing catalog categories")
            attributes = nodes[0].attrib
            categories = json.loads(attributes.get(":first-category-list", "null"))
            if not isinstance(categories, list):
                raise ValueError("Invalid catalog categories")
            result = []
            for item in categories:
                if not isinstance(item, dict):
                    continue
                key = f"tag_{item.get('id')}"
                if key not in self._filter_keys["iqiyi"] or not isinstance(item.get("child"), list):
                    continue
                group = self._filter_group(key, item.get("name") or "类型", [
                    (child.get("id"), child.get("name")) for child in item["child"] if isinstance(child, dict)])
                if group:
                    result.append(group)
            for attribute, key, name in ((":my-year", "market_release_date_level", "年份"),
                                          (":pay-status", "is_purchase", "资费"),
                                          (":comic-status", "is_album_finished", "状态")):
                definition = json.loads(attributes.get(attribute, "{}"))
                if not isinstance(definition, dict) or channel not in definition.get("cid", []):
                    continue
                values = definition.get("list")
                if not isinstance(values, list):
                    raise ValueError("Invalid catalog choices")
                options = [(item.get("id"), item.get("name")) for item in values if isinstance(item, dict)]
                # The legacy page still works but its year menu can lag behind its catalog.
                if key == "market_release_date_level":
                    latest = max((int(value) for value, _ in options if str(value).isdigit()), default=date.today().year)
                    options = [(str(year), str(year)) for year in range(date.today().year, latest, -1)] + options
                group = self._filter_group(key, name, options)
                if group:
                    result.append(group)
            return result
        except (ValueError, TypeError, etree.ParserError) as error:
            raise StreamingDiscoveryError("爱奇艺筛选信息格式异常，请稍后重试") from error

    def discover(self, source, page=1, params=None):
        """Return one validated page, caching successful responses for five minutes."""
        if not isinstance(source, str) or source not in self._categories:
            raise StreamingDiscoveryError("不支持的探索来源")
        if isinstance(page, bool) or not re.fullmatch(r"[0-9]+", str(page)) or not 1 <= int(page) <= 10:
            raise StreamingDiscoveryError("页码必须是 1 到 10 的整数")
        page = int(page)
        if params is None:
            params = {}
        if not isinstance(params, dict) or set(params) - {"category", "sort"} - self._filter_keys[source]:
            raise StreamingDiscoveryError("不支持的探索筛选参数")
        category = params.get("category") or "tv"
        sort = params.get("sort") or "hot"
        if not isinstance(category, str) or category not in self._categories[source]:
            raise StreamingDiscoveryError("不支持的影视分类")
        if not isinstance(sort, str) or sort not in self._sorts[source]:
            raise StreamingDiscoveryError("不支持的排序方式")
        if source == "tencent" and sort not in self._tencent_sorts[category]:
            raise StreamingDiscoveryError("该分类不支持此排序方式")
        selected = {}
        for name, value in params.items():
            if name in ("category", "sort"):
                continue
            if not isinstance(value, str):
                raise StreamingDiscoveryError("筛选值必须为字符串")
            if value:
                selected[name] = value
        if selected:
            choices = {group["key"]: {option["value"] for option in group["options"]}
                       for group in self.filters(source, category)}
            if any(value not in choices.get(name, set()) for name, value in selected.items()):
                raise StreamingDiscoveryError("当前分类不支持所选筛选条件，请重置筛选后重试")
        key = (source, category, sort, page, tuple(sorted(selected.items())))
        cached = self._cache.get(key)
        if cached is not None:
            return deepcopy(cached)
        items, has_more = getattr(self, f"_{source}")(category, sort, page, selected)
        unique = {}
        for item in items:
            if item and item["source_id"] not in unique:
                unique[item["source_id"]] = item
        result = {"Items": list(unique.values()), "has_more": has_more}
        self._cache.set(key, deepcopy(result))
        return result

    def _request(self, source, url, params=None, body=None, text=False):
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
        if text:
            return response.text
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

    @staticmethod
    def _tencent_url():
        return ("https://pbaccess.video.qq.com/trpc.universal_backend_service."
               "page_server_rpc.PageServer/GetPageData?" + urlencode({
                   "video_appid": "1000005", "vplatform": "2", "vversion_name": "8.9.10",
                   "new_mark_label_enabled": "1"}))

    def _tencent(self, category, sort, page, filters=None):
        """Use the returned page-context key instead of a hard-coded dataset ID."""
        url = self._tencent_url()
        body = {"page_params": {"channel_id": self._categories["tencent"][category],
                                "page_type": "channel_operation", "page_id": "channel_list_second_page",
                                "filter_params": urlencode({"sort": self._tencent_sorts[category][sort], **(filters or {})})}}

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
        result = []
        for entry in self._tencent_entries(data):
            if str(entry.get("item_type")) != "2":
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

    @staticmethod
    def _tencent_entries(data):
        modules = data.get("module_list_datas")
        if not isinstance(modules, list):
            raise StreamingDiscoveryError("腾讯视频片库数据格式异常，请稍后重试")
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
                    if isinstance(entry, dict):
                        yield entry

    def _iqiyi(self, category, sort, page, filters=None):
        """Use the public PC catalog endpoint, which does not require account cookies."""
        channel = self._categories["iqiyi"][category]
        params = {
            "channel_id": channel, "data_type": "1", "mode": self._sorts["iqiyi"][sort],
            "page_id": str(page), "ret_num": "30"}
        filters = filters or {}
        tags = [value + ";must" for key, value in sorted(filters.items()) if key.startswith("tag_")]
        if tags:
            params["three_category_id"] = ",".join(tags)
        if filters.get("market_release_date_level"):
            params["market_release_date_level"] = filters["market_release_date_level"].replace("_", "-")
        if filters.get("is_purchase"):
            params["is_purchase"] = "0" if filters["is_purchase"] == "0" else "1"
        if filters.get("is_album_finished"):
            params["is_album_finished"] = filters["is_album_finished"]
        payload = self._request("iqiyi", "https://pcw-api.iqiyi.com/search/recommend/list", params=params)
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

    def _mgtv(self, category, sort, page, filters=None):
        """Read Mango TV's explicit end-of-list marker."""
        payload = self._request("mgtv", "https://pianku.api.mgtv.com/rider/list/pcweb/v3", params={
            "allowedRC": "1", "platform": "pcweb", "channelId": self._categories["mgtv"][category],
            "pn": str(page), "pc": "30", "hudong": "1", "_support": "10000000",
            "sort": self._sorts["mgtv"][sort], **(filters or {})})
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
