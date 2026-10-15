import html as html_lib
from app.brushtask import BrushTask
from app.conf import SystemConfig
from app.helper import CookieCloudHelper
from app.indexer import Indexer
from app.sites import Sites, SiteUserInfo, SiteCookie
from app.utils import StringUtils
from web.actions.validation import parse_brush_rule, prepare_site_note, validate_site_config_url


def _site_capabilities(attributes):
    return {
        "site_free": bool(attributes.get("FREE")),
        "site_2xfree": bool(attributes.get("2XFREE")),
        "site_hr": bool(attributes.get("HR")),
    }


class SiteActions:
    """站点管理、统计、Cookie 与刷流动作。"""

    def __init__(self, dbhelper):
        self.dbhelper = dbhelper

    def update_site(self, data):
        """
        维护站点信息
        """

        def __is_site_duplicate(query_name, query_tid):
            # 检查是否重名
            _sites = self.dbhelper.get_site_by_name(name=query_name)
            for site in _sites:
                site_id = site.id
                if str(site_id) != str(query_tid):
                    return True
            return False

        tid = data.get('site_id')
        name = data.get('site_name')
        site_pri = data.get('site_pri')
        try:
            rssurl = validate_site_config_url(data.get('site_rssurl'), "站点 RSS 地址")
            signurl = validate_site_config_url(data.get('site_signurl'), "站点签到地址")
            note = prepare_site_note(data.get('site_note'))
        except ValueError as error:
            return {"code": 400, "msg": str(error)}
        cookie = data.get('site_cookie')
        rss_uses = data.get('site_include')

        if __is_site_duplicate(name, tid):
            return {"code": 400, "msg": "站点名称重复"}

        if tid:
            sites = self.dbhelper.get_site_by_id(tid)
            # 站点不存在
            if not sites:
                return {"code": 400, "msg": "站点不存在"}

            old_name = sites[0].name
            old_cookie = sites[0].cookie

            if cookie == "******":
                cookie = old_cookie

            ret = self.dbhelper.update_config_site(tid=tid,
                                                   name=name,
                                                   site_pri=site_pri,
                                                   rssurl=rssurl,
                                                   signurl=signurl,
                                                   cookie=cookie,
                                                   note=note,
                                                   rss_uses=rss_uses)
            if ret and (name != old_name):
                # 更新历史站点数据信息
                self.dbhelper.update_site_user_statistics_site_name(
                    name, old_name)
                self.dbhelper.update_site_seed_info_site_name(name, old_name)
                self.dbhelper.update_site_statistics_site_name(name, old_name)

        else:
            ret = self.dbhelper.insert_config_site(name=name,
                                                   site_pri=site_pri,
                                                   rssurl=rssurl,
                                                   signurl=signurl,
                                                   cookie=cookie,
                                                   note=note,
                                                   rss_uses=rss_uses)
        # 生效站点配置
        Sites().init_config()
        # 初始化刷流任务
        BrushTask().init_config()
        return {"code": ret}

    @staticmethod
    def get_site(data):
        """
        查询单个站点信息
        """
        tid = data.get("id")
        site_attr = {}
        if tid:
            ret = Sites().get_sites(siteid=tid)
            if ret.get("rssurl"):
                site_attr = Sites().get_grapsite_conf(ret.get("rssurl"))
        else:
            ret = []
        return {"code": 0, "site": ret, **_site_capabilities(site_attr)}

    @staticmethod
    def get_brush_site_capabilities(data):
        """返回刷流页面所需能力，不暴露 Cookie、RSS URL 等站点配置。"""
        tid = data.get("id") if isinstance(data, dict) else None
        site_attr = {}
        if tid:
            site = Sites().get_sites(siteid=tid) or {}
            rss_url = site.get("rssurl")
            if rss_url:
                site_attr = Sites().get_grapsite_conf(rss_url) or {}
        return {"code": 0, **_site_capabilities(site_attr)}

    @staticmethod
    def get_sites(data):
        """
        查询多个站点信息
        """
        filters = {key: bool(data.get(key)) for key in ("rss", "brush", "signin", "statistic")}
        if data.get("basic"):
            sites = Sites().get_site_dict(**filters)
        else:
            sites = Sites().get_sites(**filters)
            desensitized_sites = []
            for site in sites:
                site_copy = dict(site)
                for field in ("cookie", "apikey"):
                    if site_copy.get(field):
                        site_copy[field] = "******"
                desensitized_sites.append(site_copy)
            sites = desensitized_sites
        return {"code": 0, "sites": sites}

    def del_site(self, data):
        """
        删除单个站点信息
        """
        tid = data.get("id")
        if tid:
            ret = self.dbhelper.delete_config_site(tid)
            self.dbhelper.delete_site_signin_history(tid)
            Sites().init_config()
            BrushTask().init_config()
            return {"code": ret}
        else:
            return {"code": 0}

    @staticmethod
    def get_site_favicon(data):
        """
        获取站点图标
        """
        sitename = data.get("name")
        return {"code": 0, "icon": Sites().get_site_favicon(site_name=sitename)}

    @staticmethod
    def get_site_activity(data):
        """
        查询site活动[上传，下载，魔力值]
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return {"code": 1, "msg": "查询参数错误"}

        resp = {"code": 0}

        resp.update(
            {"dataset": SiteUserInfo().get_pt_site_activity_history(data["name"])})
        return resp

    @staticmethod
    def get_site_history(data):
        """
        查询site 历史[上传，下载]
        :param data: {"days":累计时间}
        :return:
        """
        if not data or "days" not in data or not isinstance(data["days"], int):
            return {"code": 1, "msg": "查询参数错误"}

        resp = {"code": 0}
        _, _, site, upload, download = SiteUserInfo().get_pt_site_statistics_history(data["days"] + 1)

        # 调整为dataset组织数据
        dataset = [["site", "upload", "download"]]
        dataset.extend([[site, upload, download]
                       for site, upload, download in zip(site, upload, download)])
        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def get_site_seeding_info(data):
        """
        查询site 做种分布信息 大小，做种数
        :param data: {"name":site_name}
        :return:
        """
        if not data or "name" not in data:
            return {"code": 1, "msg": "查询参数错误"}

        resp = {"code": 0}

        seeding_info = SiteUserInfo().get_pt_site_seeding_info(
            data["name"]).get("seeding_info", [])
        # 调整为dataset组织数据
        dataset = [["seeders", "size"]]
        dataset.extend(seeding_info)

        resp.update({"dataset": dataset})
        return resp

    @staticmethod
    def check_site_attr(data):
        """
        检查站点标识
        """
        site_attr = Sites().get_grapsite_conf(data.get("url"))
        return {"code": 0, **_site_capabilities(site_attr)}

    @staticmethod
    def list_site_resources(data):
        resources = Indexer().list_builtin_resources(index_id=data.get("id"),
                                                     page=data.get("page"),
                                                     keyword=data.get("keyword"))
        if not resources:
            return {"code": 1, "msg": "获取站点资源出现错误，无法连接到站点！"}
        else:
            return {"code": 0, "data": resources}

    @staticmethod
    def test_site(data):
        """
        测试站点连通性
        """
        flag, msg, times = Sites().test_connection(data.get("id"))
        code = 0 if flag else -1
        return {"code": code, "msg": msg, "time": times}

    @staticmethod
    def get_indexers(data=None):
        """
        获取索引器
        """
        return {"code": 0, "indexers": Indexer().get_indexer_dict()}

    @staticmethod
    def update_sites_cookie_ua(data):
        """
        更新所有站点的Cookie和UA
        """
        siteid = data.get("siteid")
        username = data.get("username")
        password = data.get("password")
        twostepcode = data.get("two_step_code")
        ocrflag = data.get("ocrflag")
        # 保存设置
        SystemConfig().set_system_config(key="CookieUserInfo",
                                         value={
                                             "username": username,
                                             "password": password,
                                             "two_step_code": twostepcode
                                         })
        retcode, messages = SiteCookie().update_sites_cookie_ua(siteid=siteid,
                                                                username=username,
                                                                password=password,
                                                                twostepcode=twostepcode,
                                                                ocrflag=ocrflag)
        if retcode == 0:
            Sites().init_config()
        return {"code": retcode, "messages": messages}

    @staticmethod
    def set_site_captcha_code(data):
        """
        设置站点验证码
        """
        code = data.get("code")
        value = data.get("value")
        SiteCookie().set_code(code=code, value=value)
        return {"code": 0}

    @staticmethod
    def get_site_user_statistics(data):
        """
        获取站点用户统计信息
        """
        sites = data.get("sites")
        encoding = data.get("encoding") or "RAW"
        sort_by = data.get("sort_by")
        sort_on = data.get("sort_on")
        site_hash = data.get("site_hash")
        statistics = SiteUserInfo().get_site_user_statistics(sites=sites, encoding=encoding)
        if sort_by and sort_on in ["asc", "desc"]:
            if sort_on == "asc":
                statistics.sort(key=lambda x: x[sort_by])
            else:
                statistics.sort(key=lambda x: x[sort_by], reverse=True)
        if site_hash == "Y":
            for item in statistics:
                item["site_hash"] = StringUtils.md5_hash(item.get("site"))
        return {"code": 0, "data": statistics}

    def cookiecloud_sync(self, data):
        """
        CookieCloud数据同步
        """
        try:
            server = validate_site_config_url(
                data.get("server"), "CookieCloud服务器地址"
            ).rstrip('/')
        except ValueError as error:
            return {"code": 1, "msg": str(error)}
        key = data.get("key")
        password = data.get("password")
        # 保存设置
        SystemConfig().set_system_config(key="CookieCloud",
                                         value={
                                             "server": server,
                                             "key": key,
                                             "password": password
                                         })
        # 同步数据
        contents, retmsg = CookieCloudHelper(server=server,
                                             key=key,
                                             password=password).download_data()
        if not contents:
            return {"code": 1, "msg": retmsg}
        success_count = 0
        for domain, content_list in contents.items():
            if domain.startswith('.'):
                domain = domain[1:]
            cookie_str = ""
            for content in content_list:
                cookie_str += content.get("name") + \
                    "=" + content.get("value") + ";"
            if not cookie_str:
                continue
            site_info = Sites().get_sites(siteurl=domain)
            if not site_info:
                continue
            self.dbhelper.update_site_cookie_ua(tid=site_info.get("id"),
                                                cookie=cookie_str)
            success_count += 1
        if success_count:
            # 重载站点信息
            Sites().init_config()
            return {"code": 0, "msg": f"成功更新 {success_count} 个站点的Cookie数据"}
        return {"code": 0, "msg": "同步完成，但未更新任何站点的Cookie！"}

    def add_brushtask(self, data):
        """
        新增刷流任务
        """
        # 输入值
        brushtask_id = data.get("brushtask_id")
        brushtask_name = data.get("brushtask_name")
        brushtask_site = data.get("brushtask_site")
        brushtask_interval = data.get("brushtask_interval")
        brushtask_downloader = data.get("brushtask_downloader")
        brushtask_totalsize = data.get("brushtask_totalsize")
        brushtask_state = data.get("brushtask_state")
        brushtask_sendmessage = 'Y' if data.get(
            "brushtask_sendmessage") else 'N'
        brushtask_forceupload = 'Y' if data.get(
            "brushtask_forceupload") else 'N'
        brushtask_free = data.get("brushtask_free")
        brushtask_hr = data.get("brushtask_hr")
        brushtask_torrent_size = data.get("brushtask_torrent_size")
        brushtask_include = data.get("brushtask_include")
        brushtask_exclude = data.get("brushtask_exclude")
        brushtask_dlcount = data.get("brushtask_dlcount")
        brushtask_peercount = data.get("brushtask_peercount")
        brushtask_seedtime = data.get("brushtask_seedtime")
        brushtask_seedratio = data.get("brushtask_seedratio")
        brushtask_seedsize = data.get("brushtask_seedsize")
        brushtask_dltime = data.get("brushtask_dltime")
        brushtask_avg_upspeed = data.get("brushtask_avg_upspeed")
        brushtask_iatime = data.get("brushtask_iatime")
        brushtask_pubdate = data.get("brushtask_pubdate")
        brushtask_upspeed = data.get("brushtask_upspeed")
        brushtask_downspeed = data.get("brushtask_downspeed")
        # 选种规则
        rss_rule = {
            "free": brushtask_free,
            "hr": brushtask_hr,
            "size": brushtask_torrent_size,
            "include": brushtask_include,
            "exclude": brushtask_exclude,
            "dlcount": brushtask_dlcount,
            "peercount": brushtask_peercount,
            "pubdate": brushtask_pubdate,
            "upspeed": brushtask_upspeed,
            "downspeed": brushtask_downspeed
        }
        # 删除规则
        remove_rule = {
            "time": brushtask_seedtime,
            "ratio": brushtask_seedratio,
            "uploadsize": brushtask_seedsize,
            "dltime": brushtask_dltime,
            "avg_upspeed": brushtask_avg_upspeed,
            "iatime": brushtask_iatime
        }
        # 添加记录
        item = {
            "name": brushtask_name,
            "site": brushtask_site,
            "free": brushtask_free,
            "interval": brushtask_interval,
            "downloader": brushtask_downloader,
            "seed_size": brushtask_totalsize,
            "state": brushtask_state,
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "sendmessage": brushtask_sendmessage,
            "forceupload": brushtask_forceupload
        }
        self.dbhelper.insert_brushtask(brushtask_id, item)

        # 重新初始化任务
        BrushTask().init_config()
        return {"code": 0}

    def del_brushtask(self, data):
        """
        删除刷流任务
        """
        brush_id = data.get("id")
        if brush_id:
            self.dbhelper.delete_brushtask(brush_id)
            # 重新初始化任务
            BrushTask().init_config()
            return {"code": 0}
        return {"code": 1}

    def brushtask_detail(self, data):
        """
        查询刷流任务详情
        """
        brush_id = data.get("id")
        brushtask = self.dbhelper.get_brushtasks(brush_id)
        if not brushtask:
            return {"code": 1, "task": {}}
        site_info = Sites().get_sites(siteid=brushtask.site)
        try:
            rss_rule = parse_brush_rule(brushtask.rss_rule)
            remove_rule = parse_brush_rule(brushtask.remove_rule)
        except ValueError as error:
            return {"code": 1, "msg": str(error), "task": {}}
        task = {
            "id": brushtask.id,
            "name": brushtask.name,
            "site": brushtask.site,
            "interval": brushtask.inteval,
            "state": brushtask.state,
            "downloader": brushtask.downloader,
            "free": brushtask.freeleech,
            "rss_rule": rss_rule,
            "remove_rule": remove_rule,
            "seed_size": brushtask.seed_size,
            "download_count": brushtask.download_count,
            "remove_count": brushtask.remove_count,
            "download_size": StringUtils.str_filesize(brushtask.download_size),
            "upload_size": StringUtils.str_filesize(brushtask.upload_size),
            "lst_mod_date": brushtask.lst_mod_date,
            "site_url": StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl")),
            "sendmessage": brushtask.sendmessage,
            "forceupload": brushtask.forceupload
        }
        return {"code": 0, "task": task}

    @staticmethod
    def run_brushtask(data):
        BrushTask().check_task_rss(data.get("id"))
        return {"code": 0}

    def list_brushtask_torrents(self, data):
        """
        获取刷流任务的种子明细
        """
        results = self.dbhelper.get_brushtask_torrents(brush_id=data.get("id"),
                                                       active=False)
        if not results:
            return {"code": 1, "msg": "未下载种子或未获取到种子明细"}
        return {"code": 0, "data": [item.as_dict() for item in results]}

    @staticmethod
    def parse_brush_rule_string(rules: dict):
        if not rules:
            return ""
        if not isinstance(rules, dict):
            return ""

        def escaped(value):
            return html_lib.escape(str(value or ""), quote=True)

        def split_rule(value):
            parts = str(value or "").split("#", 1)
            return parts if len(parts) == 2 else ["", ""]

        rule_filter_string = {"gt": ">", "lt": "<", "bw": ""}
        rule_htmls = []
        if rules.get("size"):
            sizes = split_rule(rules.get("size"))
            if sizes[0]:
                if sizes[1]:
                    sizes[1] = sizes[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="种子大小">种子大小: %s %sGB</span>'
                    % (rule_filter_string.get(sizes[0]), escaped(sizes[1])))
        if rules.get("pubdate"):
            pubdates = split_rule(rules.get("pubdate"))
            if pubdates[0]:
                if pubdates[1]:
                    pubdates[1] = pubdates[1].replace(",", "-")
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="发布时间">发布时间: %s %s小时</span>'
                    % (rule_filter_string.get(pubdates[0]), escaped(pubdates[1])))
        if rules.get("upspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="上传限速">上传限速: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("upspeed")) * 1024))
        if rules.get("downspeed"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="下载限速">下载限速: %sB/s</span>'
                              % StringUtils.str_filesize(int(rules.get("downspeed")) * 1024))
        if rules.get("include"):
            rule_htmls.append(
                '<span class="badge badge-outline text-green me-1 mb-1 text-wrap text-start" title="包含规则">包含: %s</span>'
                % escaped(rules.get("include")))
        if rules.get("hr"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1" title="排除HR">排除: HR</span>')
        if rules.get("exclude"):
            rule_htmls.append(
                '<span class="badge badge-outline text-red me-1 mb-1 text-wrap text-start" title="排除规则">排除: %s</span>'
                % escaped(rules.get("exclude")))
        if rules.get("dlcount"):
            rule_htmls.append('<span class="badge badge-outline text-blue me-1 mb-1" title="同时下载数量限制">同时下载: %s</span>'
                              % escaped(rules.get("dlcount")))
        if rules.get("peercount"):
            peer_counts = None
            peer_count_parts = split_rule(rules.get("peercount"))
            if len(peer_count_parts) == 2 and peer_count_parts[1]:
                peer_count_parts[1] = peer_count_parts[1].replace(",", "-")
                peer_counts = peer_count_parts
            if peer_counts:
                rule_htmls.append(
                    '<span class="badge badge-outline text-blue me-1 mb-1" title="当前做种人数限制">做种人数: %s %s</span>'
                    % (rule_filter_string.get(peer_counts[0]), escaped(peer_counts[1])))
        if rules.get("time"):
            times = split_rule(rules.get("time"))
            if times[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="做种时间">做种时间: %s %s小时</span>'
                    % (rule_filter_string.get(times[0]), escaped(times[1])))
        if rules.get("ratio"):
            ratios = split_rule(rules.get("ratio"))
            if ratios[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="分享率">分享率: %s %s</span>'
                    % (rule_filter_string.get(ratios[0]), escaped(ratios[1])))
        if rules.get("uploadsize"):
            uploadsizes = split_rule(rules.get("uploadsize"))
            if uploadsizes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="上传量">上传量: %s %sGB</span>'
                    % (rule_filter_string.get(uploadsizes[0]), escaped(uploadsizes[1])))
        if rules.get("dltime"):
            dltimes = split_rule(rules.get("dltime"))
            if dltimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="下载耗时">下载耗时: %s %s小时</span>'
                    % (rule_filter_string.get(dltimes[0]), escaped(dltimes[1])))
        if rules.get("avg_upspeed"):
            avg_upspeeds = split_rule(rules.get("avg_upspeed"))
            if avg_upspeeds[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="平均上传速度">平均上传速度: %s %sKB/S</span>'
                    % (rule_filter_string.get(avg_upspeeds[0]), escaped(avg_upspeeds[1])))
        if rules.get("iatime"):
            iatimes = split_rule(rules.get("iatime"))
            if iatimes[0]:
                rule_htmls.append(
                    '<span class="badge badge-outline text-orange me-1 mb-1" title="未活动时间">未活动时间: %s %s小时</span>'
                    % (rule_filter_string.get(iatimes[0]), escaped(iatimes[1])))

        return "<br>".join(rule_htmls)
