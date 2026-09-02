import base64
import json
import os
import re
import tempfile
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from bencoder import bdecode

from app.utils.http_utils import RequestUtils
from config import Config

# Trackers列表
trackers = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://9.rarbg.com:2810/announce",
    "udp://opentracker.i2p.rocks:6969/announce",
    "https://opentracker.i2p.rocks:443/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker1.bt.moack.co.kr:80/announce",
    "udp://tracker.pomf.se:80/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://p4p.arenabg.com:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://movies.zsw.ca:6969/announce",
    "udp://ipv4.tracker.harry.lu:80/announce",
    "udp://explodie.org:6969/announce",
    "udp://exodus.desync.com:6969/announce",
    "https://tracker.nanoha.org:443/announce",
    "https://tracker.lilithraws.org:443/announce",
    "https://tr.burnabyhighstar.com:443/announce",
    "http://tracker.mywaifu.best:6969/announce",
    "http://bt.okmp3.ru:2710/announce"
]


class Torrent:
    _torrent_temp_path = None
    _dynamic_url_pattern = re.compile(r"^\[([A-Za-z0-9+/=]+)](https?://.+)$")
    _MAX_TORRENT_SIZE = 20 * 1024 * 1024
    _MAX_REDIRECTS = 5
    _REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
    _SENSITIVE_REDIRECT_HEADERS = frozenset({
        "api-key",
        "authorization",
        "cookie",
        "proxy-authorization",
        "referer",
        "x-api-key",
        "x-auth-token",
        "x-access-token",
    })

    def __init__(self):
        self._torrent_temp_path = Config().get_temp_path()
        if not os.path.exists(self._torrent_temp_path):
            os.makedirs(self._torrent_temp_path)

    def get_torrent_info(self, url, cookie=None, ua=None, referer=None, proxy=False,
                         apikey=None, source_url=None):
        """
        把种子下载到本地，返回种子内容
        :param url: 种子链接
        :param cookie: 站点Cookie
        :param ua: 站点UserAgent
        :param referer: 关联地址，有的网站需要这个否则无法下载
        :param proxy: 是否使用内置代理
        :return: 种子保存路径、种子内容、种子文件列表主目录、种子文件列表、错误信息
        """
        if not url:
            return None, None, "", [], "URL为空"
        url, resolve_error = self.resolve_dynamic_download_url(url=url,
                                                               cookie=cookie,
                                                               ua=ua,
                                                               proxy=proxy,
                                                               apikey=apikey,
                                                               source_url=source_url)
        if resolve_error:
            return None, None, "", [], resolve_error
        if url.startswith("magnet:"):
            return None, url, "", [], "获取到磁力链接"
        try:
            # 下载保存种子文件
            file_path, content, errmsg = self.save_torrent_file(url=url,
                                                                cookie=cookie,
                                                                ua=ua,
                                                                referer=referer,
                                                                proxy=proxy)
            if not file_path:
                return None, content, "", [], errmsg
            # 解析种子文件
            files_folder, files, retmsg = self.get_torrent_files(file_path)
            # 种子文件路径、种子内容、种子文件列表主目录、种子文件列表、错误信息
            return file_path, content, files_folder, files, retmsg

        except Exception as err:
            return None, None, "", [], "下载种子文件出现异常：%s" % str(err)

    @classmethod
    def is_dynamic_download_url(cls, url):
        """
        判断是否为 API 站点使用的动态下载描述符。
        """
        return bool(url and cls._dynamic_url_pattern.match(url))

    @staticmethod
    def _parse_download_url(value):
        normalized = str(value or "").strip()
        try:
            parsed = urlparse(normalized)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            return None, None
        scheme = parsed.scheme.lower()
        if scheme == "magnet":
            return normalized, None
        if scheme not in {"http", "https"} or not hostname:
            return None, None
        return normalized, hostname.rstrip(".").lower()

    @staticmethod
    def _download_origin(value):
        try:
            parsed = urlparse(value)
            scheme = parsed.scheme.lower()
            hostname = (parsed.hostname or "").rstrip(".").lower()
            port = parsed.port
        except (TypeError, ValueError):
            return None
        if scheme not in {"http", "https"} or not hostname:
            return None
        return scheme, hostname, port or (443 if scheme == "https" else 80)

    @classmethod
    def _resolve_redirect_url(cls, current_url, location):
        try:
            return cls._parse_download_url(
                urljoin(current_url, str(location).strip())
            )
        except (TypeError, ValueError):
            return None, None

    @classmethod
    def _strip_sensitive_redirect_headers(cls, headers):
        if not isinstance(headers, dict):
            return headers
        return {
            key: value
            for key, value in headers.items()
            if str(key).lower() not in cls._SENSITIVE_REDIRECT_HEADERS
        }

    @staticmethod
    def _close_response(response):
        close = getattr(response, "close", None)
        if callable(close):
            close()

    @classmethod
    def resolve_dynamic_download_url(cls, url, cookie=None, ua=None, proxy=False,
                                     apikey=None, source_url=None):
        """
        解析 ``[base64-json]URL`` 格式，先请求 API 再取得真实种子地址。
        """
        match = cls._dynamic_url_pattern.match(url or "")
        if not match:
            return url, ""
        try:
            if len(match.group(1)) > 8192:
                return None, "动态下载参数过长"
            descriptor = json.loads(base64.b64decode(match.group(1), validate=True).decode("utf-8"))
            if not isinstance(descriptor, dict):
                return None, "动态下载参数格式错误"
            method = str(descriptor.get("method") or "get").lower()
            if method not in ("get", "post"):
                return None, f"不支持的动态下载请求方式：{method}"
            headers = descriptor.get("header") or ua
            if headers is not None and not isinstance(headers, (dict, str)):
                return None, "动态下载请求头格式错误"
            if isinstance(headers, dict):
                expanded_headers = {}
                for key, value in headers.items():
                    if isinstance(value, str) and "{apikey}" in value:
                        if not apikey:
                            return None, "动态下载缺少 API Key/Passkey"
                        value = value.replace("{apikey}", apikey)
                    expanded_headers[key] = value
                headers = expanded_headers
            params = descriptor.get("params")
            if params is not None and not isinstance(params, dict):
                return None, "动态下载请求参数格式错误"
            api_url = match.group(2)
            request_cookie = cookie if descriptor.get("cookie") else None
            if request_cookie:
                if not source_url:
                    return None, "动态下载缺少可信站点来源，已拒绝发送 Cookie"
                source_host = (urlparse(source_url).hostname or "").lower()
                api_host = (urlparse(api_url).hostname or "").lower()
                if not (source_host == api_host
                        or source_host.endswith(f".{api_host}")
                        or api_host.endswith(f".{source_host}")):
                    return None, "动态下载接口与站点域名不一致，已拒绝发送 Cookie"
            current_url, current_hostname = cls._parse_download_url(api_url)
            if not current_url or current_hostname is None:
                return None, "动态下载接口仅支持 HTTP(S)"
            current_origin = cls._download_origin(current_url)

            request_headers = headers
            request_method = method
            request_params = params
            request_proxies = Config().get_proxies() \
                if descriptor.get("proxy") or proxy else None
            visited_urls = {current_url}
            redirect_count = 0

            while True:
                request = RequestUtils(
                    headers=request_headers,
                    cookies=request_cookie,
                    proxies=request_proxies,
                )
                if request_method == "post":
                    response = request.post_res(
                        url=current_url,
                        params=request_params,
                        allow_redirects=False,
                    )
                else:
                    response = request.get_res(
                        url=current_url,
                        params=request_params,
                        allow_redirects=False,
                    )
                if response is None:
                    return None, "动态下载接口无法连接"
                if response.status_code not in cls._REDIRECT_STATUS_CODES:
                    break
                if redirect_count >= cls._MAX_REDIRECTS:
                    cls._close_response(response)
                    return None, "动态下载重定向次数超过限制"

                try:
                    location = (getattr(response, "headers", {}) or {}).get("Location")
                    redirect_status = response.status_code
                finally:
                    cls._close_response(response)
                if not location:
                    return None, "动态下载重定向缺少 Location"
                next_url, next_hostname = cls._resolve_redirect_url(current_url, location)
                if not next_url:
                    return None, "动态下载重定向仅支持 HTTP(S) 或磁力链接"
                if next_hostname is None:
                    return next_url, ""
                if next_url in visited_urls:
                    return None, "动态下载发生循环重定向"

                next_origin = cls._download_origin(next_url)
                if next_origin != current_origin:
                    request_cookie = None
                    request_headers = cls._strip_sensitive_redirect_headers(request_headers)
                    request_params = None

                if redirect_status == 303 \
                        or redirect_status in {301, 302} and request_method == "post":
                    request_method = "get"
                    request_params = None
                elif request_method == "get":
                    request_params = None

                visited_urls.add(next_url)
                current_url = next_url
                current_hostname = next_hostname
                current_origin = next_origin
                redirect_count += 1

            if response.status_code != 200:
                status_code = response.status_code
                cls._close_response(response)
                return None, f"动态下载接口返回状态码：{status_code}"

            try:
                result_path = descriptor.get("result")
                if result_path:
                    result = response.json()
                    for key in str(result_path).split("."):
                        if isinstance(result, dict):
                            result = result.get(key)
                        elif isinstance(result, list) and key.isdigit() and int(key) < len(result):
                            result = result[int(key)]
                        else:
                            result = None
                            break
                else:
                    result = response.text.strip()
            finally:
                cls._close_response(response)
            if not isinstance(result, str) or not result:
                return None, "动态下载接口未返回有效地址"
            if not result.startswith(("http://", "https://", "magnet:")):
                return None, "动态下载接口返回了不支持的地址"
            return result, ""
        except (ValueError, TypeError, json.JSONDecodeError) as err:
            return None, f"解析动态下载参数失败：{err}"
        except Exception as err:
            return None, f"获取动态下载地址失败：{err}"

    def save_torrent_file(self, url, cookie=None, ua=None, referer=None, proxy=False):
        """
        把种子下载到本地
        :return: 种子保存路径，错误信息
        """
        current_url, current_hostname = self._parse_download_url(url)
        if not current_url:
            return None, None, "种子下载链接仅支持 HTTP(S) 或磁力链接"
        if current_hostname is None:
            return None, current_url, "获取到磁力链接"
        current_origin = self._download_origin(current_url)

        request_headers = ua
        request_cookie = cookie
        request_referer = referer
        request_proxies = Config().get_proxies() if proxy else None
        visited_urls = {current_url}
        redirect_count = 0

        while True:
            req = RequestUtils(
                headers=request_headers,
                cookies=request_cookie,
                referer=request_referer,
                proxies=request_proxies,
            ).get_res(url=current_url, allow_redirects=False, stream=True)
            if req is None:
                return None, None, "无法打开种子下载链接"
            if req.status_code not in self._REDIRECT_STATUS_CODES:
                break
            if redirect_count >= self._MAX_REDIRECTS:
                self._close_response(req)
                return None, None, "种子下载重定向次数超过限制"

            try:
                location = (getattr(req, "headers", {}) or {}).get("Location")
            finally:
                self._close_response(req)
            if not location:
                return None, None, "种子下载重定向缺少 Location"
            next_url, next_hostname = self._resolve_redirect_url(current_url, location)
            if not next_url:
                return None, None, "种子下载重定向仅支持 HTTP(S) 或磁力链接"
            if next_hostname is None:
                return None, next_url, "获取到磁力链接"
            if next_url in visited_urls:
                return None, None, "种子下载发生循环重定向"

            next_origin = self._download_origin(next_url)
            if next_origin != current_origin:
                request_cookie = None
                request_referer = None
                request_headers = self._strip_sensitive_redirect_headers(request_headers)

            visited_urls.add(next_url)
            current_url = next_url
            current_hostname = next_hostname
            current_origin = next_origin
            redirect_count += 1

        if req and req.status_code == 200:
            content_length = (getattr(req, "headers", {}) or {}).get("Content-Length")
            try:
                if content_length is not None and int(content_length) > self._MAX_TORRENT_SIZE:
                    self._close_response(req)
                    return None, None, "种子文件超过 20MB 限制"
            except (TypeError, ValueError):
                pass

            content_buffer = bytearray()
            try:
                for chunk in req.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if not isinstance(chunk, (bytes, bytearray)):
                        return None, None, "种子响应体格式不合法"
                    if len(content_buffer) + len(chunk) > self._MAX_TORRENT_SIZE:
                        return None, None, "种子文件超过 20MB 限制"
                    content_buffer.extend(chunk)
            except requests.exceptions.RequestException:
                return None, None, "读取种子响应体失败"
            finally:
                self._close_response(req)

            if not content_buffer:
                return None, None, "未下载到种子数据"
            file_content = bytes(content_buffer)
            if file_content.startswith(b"magnet:"):
                try:
                    magnet = file_content.decode("utf-8").strip()
                except UnicodeDecodeError:
                    return None, None, "磁力链接编码不合法"
                return None, magnet, "获取到磁力链接"

            try:
                bdecode(file_content)
            except Exception:
                return None, None, "种子数据有误，请确认链接是否正确，如为PT站点则需手工在站点下载一次种子"

            file_descriptor = None
            file_path = None
            try:
                file_descriptor, file_path = tempfile.mkstemp(
                    prefix="torrent-",
                    suffix=".torrent",
                    dir=self._torrent_temp_path,
                )
                os.fchmod(file_descriptor, 0o600)
                with os.fdopen(file_descriptor, "wb") as torrent_file:
                    file_descriptor = None
                    torrent_file.write(file_content)
            except Exception:
                if file_descriptor is not None:
                    os.close(file_descriptor)
                if file_path and os.path.exists(file_path):
                    os.unlink(file_path)
                raise
        else:
            status_code = req.status_code
            self._close_response(req)
            return None, None, "下载种子出错，状态码：%s" % status_code

        return file_path, file_content, ""

    @staticmethod
    def convert_hash_to_magnet(hash_text, title):
        """
        根据hash值，转换为磁力链，自动添加tracker
        :param hash_text: 种子Hash值
        :param title: 种子标题
        """
        if not hash_text or not title:
            return None
        hash_text = re.search(r'[0-9a-z]+', hash_text, re.IGNORECASE)
        if not hash_text:
            return None
        hash_text = hash_text.group(0)
        ret_magnet = f'magnet:?xt=urn:btih:{hash_text}&dn={quote(title)}'
        for tracker in trackers:
            ret_magnet = f'{ret_magnet}&tr={quote(tracker)}'
        return ret_magnet

    @staticmethod
    def add_trackers_to_magnet(url, title=None):
        """
        添加tracker和标题到磁力链接
        """
        if not url or not title:
            return None
        ret_magnet = url
        if title and url.find("&dn=") == -1:
            ret_magnet = f'{ret_magnet}&dn={quote(title)}'
        for tracker in trackers:
            ret_magnet = f'{ret_magnet}&tr={quote(tracker)}'
        return ret_magnet

    @staticmethod
    def get_torrent_files(path):
        """
        解析Torrent文件，获取文件清单
        :return: 种子文件列表主目录、种子文件列表、错误信息
        """
        if not path or not os.path.exists(path):
            return "", [], f"种子文件不存在：{path}"
        file_names = []
        file_folder = ""
        try:
            with open(path, 'rb') as torrent_file:
                torrent = bdecode(torrent_file.read())
            info = torrent.get("info") or torrent.get(b"info") or {}
            if info:
                files = info.get("files") or info.get(b"files") or []
                if files:
                    for item in files:
                        file_path = item.get("path") or item.get(b"path") or []
                        if file_path:
                            file_names.append(Torrent.__torrent_text(file_path[0]))
                    file_folder = Torrent.__torrent_text(info.get("name") or info.get(b"name"))
                else:
                    file_names.append(Torrent.__torrent_text(info.get("name") or info.get(b"name")))
        except Exception as err:
            return file_folder, file_names, "解析种子文件异常：%s" % str(err)
        return file_folder, file_names, ""

    @staticmethod
    def __torrent_text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def read_torrent_content(self, path):
        """
        读取本地种子文件的内容
        :return: 种子内容、种子文件列表主目录、种子文件列表、错误信息
        """
        if not path or not os.path.exists(path):
            return None, "", [], "种子文件不存在：%s" % path
        content, retmsg, file_folder, files = None, "", "", []
        try:
            # 读取种子文件内容
            with open(path, 'rb') as f:
                content = f.read()
            # 解析种子文件
            file_folder, files, retmsg = self.get_torrent_files(path)
        except Exception as e:
            retmsg = "读取种子文件出错：%s" % str(e)
        return content, file_folder, files, retmsg

    @staticmethod
    def get_magnet_title(url):
        """
        从磁力链接中获取标题
        """
        if not url:
            return ""
        title = re.findall(r"dn=(.+)&?", url)
        return unquote(title[0]) if title else ""

    @staticmethod
    def get_intersection_episodes(target, source, title):
        """
        对两个季集字典进行判重，有相同项目的取集的交集
        """
        if not source or not title:
            return target
        if not source.get(title):
            return target
        if not target.get(title):
            target[title] = source.get(title)
            return target
        index = -1
        for target_info in target.get(title):
            index += 1
            source_info = None
            for info in source.get(title):
                if info.get("season") == target_info.get("season"):
                    source_info = info
                    break
            if not source_info:
                continue
            if not source_info.get("episodes"):
                continue
            if not target_info.get("episodes"):
                target_episodes = source_info.get("episodes")
                target[title][index]["episodes"] = target_episodes
                continue
            target_episodes = list(set(target_info.get("episodes")).intersection(set(source_info.get("episodes"))))
            target[title][index]["episodes"] = target_episodes
        return target
