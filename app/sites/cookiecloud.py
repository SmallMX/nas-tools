"""从内置站点目录识别 CookieCloud 中可以新增的站点地址。"""

from urllib.parse import urlsplit, urlunsplit


def _host(value):
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        value = value.strip().lstrip(".")
        parsed = urlsplit(value if "://" in value else "//" + value)
        hostname = parsed.hostname
        if not hostname or any(char.isspace() for char in hostname):
            return ""
        return hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError):
        return ""


def _same_host(first, second):
    return bool(first and second and first.removeprefix("www.") == second.removeprefix("www."))


def _site_url(value, hostname=None):
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        value = value.strip()
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return ""
        host = hostname or _host(value)
        if not host:
            return ""
        netloc = f"[{host}]" if ":" in host else host
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))
    except (ValueError, UnicodeError):
        return ""


def cookiecloud_site_candidates(indexers, contents, existing_sites):
    """返回已知且未维护的 ``name/signurl`` 候选，由调用方验证 Cookie 后保存。

    同一站点可返回多个地址，让调用方在主域 Cookie 失效时尝试别名；成功
    保存后应按名称跳过其余候选。此处不启用站点用途，也不联网验证登录。
    """
    catalog = []
    for position, indexer in enumerate(indexers or []):
        if not isinstance(indexer, dict):
            continue
        name = indexer.get("name") or indexer.get("id")
        if not isinstance(name, str) or not name.strip():
            continue
        urls = [indexer.get("domain")]
        for key in ("aliases", "domains"):
            aliases = indexer.get(key) or []
            if isinstance(aliases, str):
                aliases = [aliases]
            if isinstance(aliases, (list, tuple)):
                urls.extend(aliases)
        urls = list(dict.fromkeys(url for value in urls if (url := _site_url(value))))
        if urls:
            catalog.append({"name": name.strip(), "urls": urls,
                            "identity": indexer.get("id") or position})

    existing_names = set()
    existing_hosts = set()
    for site in existing_sites or []:
        if not isinstance(site, dict):
            continue
        if isinstance(site.get("name"), str):
            existing_names.add(site["name"].strip().casefold())
        existing_hosts.update(_host(site.get(key)) for key in ("signurl", "rssurl", "strict_url"))
    existing_hosts.discard("")

    cookies = []
    for bucket, entries in (contents or {}).items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            domain = _host(entry.get("domain") or bucket)
            if domain:
                cookies.append((domain, bool(entry.get("hostOnly")), _host(bucket)))

    candidates = []
    seen = set()
    for site in catalog:
        if site["name"].casefold() in existing_names or any(
                _same_host(_host(url), saved_host) for url in site["urls"] for saved_host in existing_hosts):
            continue
        direct, inferred = [], []
        for url in site["urls"]:
            hostname = _host(url)
            for domain, host_only, bucket in cookies:
                if _same_host(hostname, domain):
                    direct.append(_site_url(url, domain))
                bucket_matches = _same_host(hostname, bucket) and (
                    bucket == domain or not host_only and bucket.endswith("." + domain))
                if bucket_matches:
                    direct.append(_site_url(url, bucket))
                if host_only or "." not in domain or not hostname.endswith("." + domain):
                    continue
                # 明确来自其它子域的父域 Cookie，不能据此添加未观测的站点。
                if bucket != domain and bucket.endswith("." + domain) and not bucket_matches:
                    continue
                identities = {known["identity"] for known in catalog if any(
                    _host(known_url) == domain or _host(known_url).endswith("." + domain)
                    for known_url in known["urls"])}
                if len(identities) == 1:
                    inferred.append(url)
        for url in direct + inferred:
            key = (site["name"].casefold(), url)
            if url and key not in seen:
                seen.add(key)
                candidates.append({"name": site["name"], "signurl": url})
    return candidates
