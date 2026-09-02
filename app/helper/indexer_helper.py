import copy
import glob
import os.path
import pickle

import log
import ruamel.yaml

from app.utils import StringUtils, ExceptionUtils
from app.utils.commons import singleton
from config import Config


@singleton
class IndexerHelper:
    _indexers = []

    def __init__(self):
        self.init_config()

    def init_config(self):
        indexers = []
        try:
            with open(os.path.join(Config().get_inner_config_path(),
                                   "sites.dat"),
                      "rb") as f:
                indexers = pickle.load(f)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
        self._indexers = self.__load_site_overlays(indexers)

    @classmethod
    def __merge_dict(cls, base, overlay):
        """
        递归合并站点配置，便于只维护域名、解析器等发生变化的字段。
        """
        result = copy.deepcopy(base) if isinstance(base, dict) else {}
        for key, value in (overlay or {}).items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = cls.__merge_dict(result.get(key), value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    @staticmethod
    def __yaml_sites(content):
        if isinstance(content, list):
            return content
        if isinstance(content, dict) and isinstance(content.get("sites"), list):
            return content.get("sites")
        if isinstance(content, dict):
            return [content]
        return []

    def __load_site_overlays(self, indexers):
        """
        在历史 sites.dat 之上加载 YAML 增量配置。

        内置配置先加载，用户配置目录下的 sites/*.yml 最后加载，因此用户可以
        覆盖内置站点而不必重新生成 pickle 文件。
        """
        merged = [copy.deepcopy(item) for item in (indexers or []) if isinstance(item, dict)]
        positions = {item.get("id"): pos for pos, item in enumerate(merged) if item.get("id")}
        config_dirs = [os.path.join(Config().get_inner_config_path(), "sites")]
        custom_dir = os.path.join(Config().get_config_path(), "sites")
        if os.path.realpath(custom_dir) != os.path.realpath(config_dirs[0]):
            config_dirs.append(custom_dir)

        yaml_loader = ruamel.yaml.YAML(typ="safe")
        for config_dir in config_dirs:
            files = sorted(glob.glob(os.path.join(config_dir, "*.yml")))
            files.extend(sorted(glob.glob(os.path.join(config_dir, "*.yaml"))))
            for config_file in files:
                try:
                    with open(config_file, mode="r", encoding="utf-8") as stream:
                        overlays = self.__yaml_sites(yaml_loader.load(stream))
                    for overlay in overlays:
                        if not isinstance(overlay, dict) or not overlay.get("id"):
                            log.warn(f"【Indexer】忽略缺少 id 的站点配置：{config_file}")
                            continue
                        site_id = overlay.get("id")
                        if site_id in positions:
                            position = positions[site_id]
                            merged[position] = self.__merge_dict(merged[position], overlay)
                        else:
                            positions[site_id] = len(merged)
                            merged.append(copy.deepcopy(overlay))
                except Exception as err:
                    log.error(f"【Indexer】加载站点配置失败：{config_file}，{err}")
        return merged

    def get_all_indexers(self):
        return self._indexers

    def get_indexer(self,
                    url,
                    cookie=None,
                    name=None,
                    public=None,
                    proxy=False,
                    parser=None,
                    ua=None,
                    render=None,
                    language=None,
                    pri=None,
                    apikey=None):
        if not url:
            return None
        for indexer in self._indexers:
            if not indexer.get("domain"):
                continue
            primary_domain = indexer.get("domain")
            aliases = indexer.get("aliases") or indexer.get("domains") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            domains = [primary_domain, *aliases]
            if any(StringUtils.url_equal(domain, url) for domain in domains if domain):
                runtime_domain = StringUtils.get_base_url(url) \
                    if StringUtils.url_equal(primary_domain, url) else primary_domain
                return IndexerConf(datas=indexer,
                                   cookie=cookie,
                                   name=name,
                                   public=public,
                                   proxy=proxy,
                                   parser=parser,
                                   ua=ua,
                                   render=render,
                                   builtin=True,
                                   language=language,
                                   pri=pri,
                                   apikey=apikey,
                                   domain=runtime_domain)
        return None


class IndexerConf(object):

    def __init__(self,
                 datas=None,
                 cookie=None,
                 name=None,
                 public=None,
                 proxy=False,
                 parser=None,
                 ua=None,
                 render=None,
                 builtin=True,
                 language=None,
                 pri=None,
                 apikey=None,
                 domain=None):
        if not datas:
            return
        # ID
        self.id = datas.get('id')
        # 名称
        self.name = datas.get('name') if not name else name
        # 是否内置站点
        self.builtin = builtin
        # 域名
        self.domain = domain or datas.get('domain')
        # 搜索
        self.search = datas.get('search', {})
        # 批量搜索，如果为空对象则表示不支持批量搜索
        self.batch = self.search.get("batch", {}) if builtin else {}
        # 解析器
        self.parser = parser if parser is not None else datas.get('parser')
        # 是否启用渲染
        self.render = render if render is not None else datas.get("render")
        # 浏览
        self.browse = datas.get('browse', {})
        # 种子过滤
        self.torrents = datas.get('torrents', {})
        # 分类
        self.category = datas.get('category', {})
        # Cookie
        self.cookie = cookie
        # User-Agent
        self.ua = ua
        # API Key / Passkey
        self.apikey = apikey
        # API超时时间
        self.timeout = datas.get('timeout') or 15
        # 是否公开站点
        self.public = public
        # 是否使用代理
        self.proxy = proxy
        # 仅支持的特定语种
        self.language = language
        # 索引器优先级
        self.pri = pri if pri else 0
