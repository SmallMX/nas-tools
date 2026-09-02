import re

from app.conf import ModuleConf
from app.media.meta import ReleaseGroupsMatcher
from app.utils.commons import singleton


@singleton
class Filter:
    rg_matcher = None

    def __init__(self):
        self.rg_matcher = ReleaseGroupsMatcher()

    @staticmethod
    def is_torrent_match_sey(media_info, s_num, e_num, year_str):
        """
        种子名称关键字匹配
        :param media_info: 已识别的种子信息
        :param s_num: 要匹配的季号，为空则不匹配
        :param e_num: 要匹配的集号，为空则不匹配
        :param year_str: 要匹配的年份，为空则不匹配
        :return: 是否命中
        """
        if s_num:
            if not media_info.get_season_list():
                return False
            if not isinstance(s_num, list):
                s_num = [s_num]
            if not set(s_num).issuperset(set(media_info.get_season_list())):
                return False
        if e_num:
            if not isinstance(e_num, list):
                e_num = [e_num]
            if not set(e_num).issuperset(set(media_info.get_episode_list())):
                return False
        if year_str:
            if str(media_info.year) != str(year_str):
                return False
        return True

    def check_torrent_filter(self,
                             meta_info,
                             filter_args,
                             uploadvolumefactor=None,
                             downloadvolumefactor=None):
        """
        对种子进行过滤
        :param meta_info: 名称识别后的MetaBase对象
        :param filter_args: 过滤条件的字典
        :param uploadvolumefactor: 种子的上传因子 传空不过滤
        :param downloadvolumefactor: 种子的下载因子 传空不过滤
        :return: 是否匹配，匹配的优先值，匹配信息，值越大越优先
        """
        # 过滤质量
        if filter_args.get("restype"):
            restype_re = ModuleConf.TORRENT_SEARCH_PARAMS["restype"].get(filter_args.get("restype"))
            if not meta_info.get_edtion_string():
                return False, 0, f"{meta_info.org_string} 不符合质量 {filter_args.get('restype')} 要求"
            if restype_re and not re.search(r"%s" % restype_re, meta_info.get_edtion_string(), re.I):
                return False, 0, f"{meta_info.org_string} 不符合质量 {filter_args.get('restype')} 要求"
        # 过滤分辨率
        if filter_args.get("pix"):
            pix_re = ModuleConf.TORRENT_SEARCH_PARAMS["pix"].get(filter_args.get("pix"))
            if not meta_info.resource_pix:
                return False, 0, f"{meta_info.org_string} 不符合分辨率 {filter_args.get('pix')} 要求"
            if pix_re and not re.search(r"%s" % pix_re, meta_info.resource_pix, re.I):
                return False, 0, f"{meta_info.org_string} 不符合分辨率 {filter_args.get('pix')} 要求"
        # 过滤制作组/字幕组
        if filter_args.get("team"):
            team = filter_args.get("team")
            if not meta_info.resource_team:
                resource_team = self.rg_matcher.match(
                    title=meta_info.org_string,
                    groups=team)
                if not resource_team:
                    return False, 0, f"{meta_info.org_string} 不符合制作组/字幕组 {team} 要求"
                else:
                    meta_info.resource_team = resource_team
            elif not re.search(r"%s" % team, meta_info.resource_team, re.I):
                return False, 0, f"{meta_info.org_string} 不符合制作组/字幕组 {team} 要求"
        # 过滤促销
        if filter_args.get("sp_state"):
            ul_factor, dl_factor = filter_args.get("sp_state").split()
            if uploadvolumefactor and ul_factor not in ("*", str(uploadvolumefactor)):
                return False, 0, f"{meta_info.org_string} 不符合促销要求"
            if downloadvolumefactor and dl_factor not in ("*", str(downloadvolumefactor)):
                return False, 0, f"{meta_info.org_string} 不符合促销要求"
        # 过滤包含
        if filter_args.get("include"):
            include = filter_args.get("include")
            if not re.search(r"%s" % include, meta_info.org_string, re.I):
                return False, 0, f"{meta_info.org_string} 不符合包含 {include} 要求"
        # 过滤排除
        if filter_args.get("exclude"):
            exclude = filter_args.get("exclude")
            if re.search(r"%s" % exclude, meta_info.org_string, re.I):
                return False, 0, f"{meta_info.org_string} 不符合排除 {exclude} 要求"
        # 过滤关键字
        if filter_args.get("key"):
            key = filter_args.get("key")
            if not re.search(r"%s" % key, meta_info.org_string, re.I):
                return False, 0, f"{meta_info.org_string} 不符合 {key} 要求"
        return True, 0, ""
