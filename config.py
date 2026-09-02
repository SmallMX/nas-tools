import copy
import os
import tempfile
from threading import Lock, RLock

import ruamel.yaml

# ===== 1. 全局静态常量配置区 =====
# 这些变量定义了系统的一些默认规则和魔法值（Magic Numbers），通常不需要用户去修改

# 种子名/文件名要素分隔字符：当系统看到一个文件名时，会用这些符号把它切成一块块的单词，用于匹配电影名
SPLIT_CHARS = r"\.|\s+|\(|\)|\[|]|-|\+|【|】|/|～|;|&|\||#|_|「|」|（|）|~"

# 默认User-Agent：告诉别的网站我们是用 Chrome 浏览器在访问，防止被当成爬虫屏蔽
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"

# 支持的媒体文件后缀格式，用于媒体名称识别和种子文件筛选
RMT_MEDIAEXT = ['.mp4', '.mkv', '.ts', '.iso',
                '.rmvb', '.avi', '.mov', '.mpeg',
                '.mpg', '.wmv', '.3gp', '.asf',
                '.m4v', '.flv', '.m2ts', '.strm']

# 电视剧动漫的分类genre_ids (在 TMDB 的分类体系中 16 代表动漫)
ANIME_GENREIDS = ['16']

# ===== 各种定时任务的默认执行间隔（单位：秒或小时） =====
# 删种检查时间间隔：1800秒 (半小时)
AUTO_REMOVE_TORRENTS_INTERVAL = 1800
# TMDB信息缓存定时保存时间
METAINFO_SAVE_INTERVAL = 600
# 站点流量数据刷新时间间隔（小时）
REFRESH_PT_DATA_INTERVAL = 6
# 刷流删除的检查时间间隔
BRUSH_REMOVE_TORRENTS_INTERVAL = 300
# 定时清除未识别的缓存时间间隔（小时）
META_DELETE_UNKNOWN_INTERVAL = 12
# 定时刷新壁纸的间隔（小时）
REFRESH_WALLPAPER_INTERVAL = 1

# ===== 各类外部服务的 API 地址 =====
# fanart的api，用于拉取高清封面、海报图片
FANART_MOVIE_API_URL = 'https://webservice.fanart.tv/v3/movies/%s'
FANART_TV_API_URL = 'https://webservice.fanart.tv/v3/tv/%s'

# 默认背景图地址
DEFAULT_TMDB_IMAGE = 'https://s3.bmp.ovh/imgs/2022/07/10/77ef9500c851935b.webp'
# TMDB图片地址：不同的分辨率前缀
TMDB_IMAGE_W500_URL = 'https://image.tmdb.org/t/p/w500%s'
TMDB_IMAGE_ORIGINAL_URL = 'https://image.tmdb.org/t/p/original%s'
TMDB_IMAGE_FACE_URL = 'https://image.tmdb.org/t/p/h632%s'
TMDB_PEOPLE_PROFILE_URL = 'https://www.themoviedb.org/person/%s'

# 添加下载时增加的标签，用于筛选和管理由 NAStool 创建的任务
PT_TAG = "NASTOOL"

# ===== 辅助识别参数 =====
# 给搜出来的结果打分用的权重。名字越匹配、年份越匹配，得分越高
KEYWORD_SEARCH_WEIGHT_1 = [10, 3, 2, 0.5, 0.5]
KEYWORD_SEARCH_WEIGHT_2 = [10, 2, 1]
KEYWORD_SEARCH_WEIGHT_3 = [10, 2]
KEYWORD_STR_SIMILARITY_THRESHOLD = 0.2
KEYWORD_DIFF_SCORE_THRESHOLD = 30

# 关键字黑名单：在提取电影真正名字时，把这些词过滤掉，防止把“中字”当成了电影名
KEYWORD_BLACKLIST = ['中字', '韩语', '双字', '中英', '日语', '双语', '国粤', 'HD', 'BD', '中日', '粤语', '完全版',
                     '法语', '西班牙语', 'HRHDTVAC3264', '未删减版', '未删减', '国语', '字幕组', '人人影视', 'www66ystv',
                     '人人影视制作', '英语', 'www6vhaotv', '无删减版', '完成版', '德意']

# WebDriver路径：爬虫无头浏览器的驱动路径
WEBDRIVER_PATH = {
    "Docker": "/usr/lib/chromium/chromedriver"
}

# Xvfb虚拟显示路径：Linux 下如果没有桌面环境，跑浏览器爬虫需要用到它
XVFB_PATH = [
    "/usr/bin/Xvfb",
    "/usr/local/bin/Xvfb"
]


# ===== 2. 单例模式配置类 =====

# 单例创建和配置文件读写使用不同的锁，避免构造 Config 时重入死锁。
_config_instance_lock = Lock()
_config_io_lock = RLock()

# 全局实例保存变量
_CONFIG = None


def singleconfig(cls):
    """
    这是一个装饰器（Decorator），用于实现“单例模式”。
    初学者可以这样理解：整个系统只需要一个“配置大管家”对象就够了，没必要每次读取配置都去 new 一个新管家。
    这个函数的作用是拦截对 Config 类的实例化操作，如果已经创建过，就直接返回之前的对象。
    """
    def _singleconfig(*args, **kwargs):
        global _CONFIG
        # 如果全局对象还没创建过
        if _CONFIG is None:
            with _config_instance_lock:
                if _CONFIG is None:
                    _CONFIG = cls(*args, **kwargs)
        return _CONFIG

    return _singleconfig


@singleconfig # 使用上面的装饰器，将 Config 变成单例类
class Config(object):
    """
    配置管理核心类。
    负责在程序启动时读取 yaml 配置文件，并提供给其他所有模块调用。
    """
    _config = {}         # 在内存里保存读取出来的所有配置数据 (字典格式)
    _config_path = None  # 配置文件在硬盘上的绝对路径

    def __init__(self):
        """
        初始化方法：在程序第一次调用 Config() 时执行。
        """
        # 从操作系统的环境变量 NASTOOL_CONFIG 获取配置文件的路径
        self._config_path = os.environ.get('NASTOOL_CONFIG')
        
        # 如果系统没设置时区，默认帮它设成中国时区
        if not os.environ.get('TZ'):
            os.environ['TZ'] = 'Asia/Shanghai'
            
        # 真正去硬盘上读取配置
        if not self.init_config():
            raise RuntimeError("config.yaml 加载失败，拒绝使用空配置继续启动")

    def init_config(self):
        """
        从硬盘读取 yaml 文件到内存的方法。
        """
        with _config_io_lock:
            try:
                if not self._config_path:
                    print("【Config】NASTOOL_CONFIG 环境变量未设置，程序无法工作，正在退出...")
                    quit()

                config_dir = self.get_config_path() or "."
                os.makedirs(config_dir, mode=0o700, exist_ok=True)
                os.chmod(config_dir, 0o700)
                if not os.path.exists(self._config_path):
                    template_path = os.path.join(self.get_inner_config_path(), "config.example.yaml")
                    with open(template_path, mode='r', encoding='utf-8') as template_file:
                        template_config = ruamel.yaml.YAML().load(template_file)
                    self._write_config_locked(template_config)
                    print("【Config】config.yaml 配置文件不存在，已将配置文件模板复制到配置目录...")

                os.chmod(self._config_path, 0o600)
                with open(self._config_path, mode='r', encoding='utf-8') as config_file:
                    print("正在加载配置：%s" % self._config_path)
                    loaded_config = ruamel.yaml.YAML().load(config_file)
                if not isinstance(loaded_config, dict):
                    raise ValueError("配置文件顶层必须是对象")
                self._config = loaded_config
                return True
            except Exception as error:
                print("【Config】加载 config.yaml 配置出错：%s" % str(error))
                return False

    @staticmethod
    def _fsync_directory(directory):
        """尽可能将原子替换结果同步到目录元数据。"""
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # 某些网络文件系统不支持对目录执行 fsync，文件本身仍已完成 fsync。
            pass

    def _write_config_locked(self, new_cfg):
        """将已持有写锁的配置以同目录原子替换方式落盘。"""
        config_snapshot = copy.deepcopy(new_cfg)
        config_dir = self.get_config_path() or "."
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
        os.chmod(config_dir, 0o700)
        file_descriptor, temp_path = tempfile.mkstemp(
            prefix=".config-",
            suffix=".tmp",
            dir=config_dir,
            text=True,
        )
        try:
            os.chmod(temp_path, 0o600)
            with os.fdopen(file_descriptor, mode='w', encoding='utf-8') as temp_file:
                yaml = ruamel.yaml.YAML()
                yaml.dump(config_snapshot, temp_file)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            with open(temp_path, mode='r', encoding='utf-8') as validation_file:
                validated_config = ruamel.yaml.YAML(typ="safe").load(validation_file)
            if not isinstance(validated_config, dict):
                raise ValueError("配置文件顶层必须是对象")

            os.replace(temp_path, self._config_path)
            temp_path = None
            os.chmod(self._config_path, 0o600)
            self._fsync_directory(config_dir)
            self._config = config_snapshot
            return True
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def get_proxies(self):
        """获取代理配置，方便其他模块（如搜刮TMDB时）调用"""
        return self.get_config('app').get("proxies")

    def get_ua(self):
        """获取配置文件里的 user_agent，没有就用默认的"""
        return self.get_config('app').get("user_agent") or DEFAULT_UA

    def get_config(self, node=None):
        """
        供其他所有模块使用的查询接口！非常常用。
        比如想获取日志配置，可以调用 Config().get_config('app')
        
        :param node: 要获取的顶层节点名，比如 'app', 'media'
        :return: 对应的字典配置，如果没传 node 则返回整个大字典
        """
        if not node:
            return self._config
        # get() 方法的好处是即使配里面没有这个节点，也会安全地返回空字典 {} 而不会报错
        return self._config.get(node, {})

    def save_config(self, new_cfg):
        """
        将用户在 Web 页面上修改的新配置，反写（保存）回硬盘的 yaml 文件里。
        """
        with _config_io_lock:
            return self._write_config_locked(new_cfg)

    def get_config_path(self):
        """返回配置文件所在的文件夹路径"""
        return os.path.dirname(self._config_path)

    def get_temp_path(self):
        """返回程序的临时文件夹存放路径"""
        return os.path.join(self.get_config_path(), "temp")

    @staticmethod
    def get_root_path():
        """
        获取当前项目的根目录路径。
        os.path.realpath(__file__) 会获取当前 config.py 的绝对路径，
        dirname 取它的上一级（即根目录）。
        """
        return os.path.dirname(os.path.realpath(__file__))

    def get_inner_config_path(self):
        """获取程序代码里自带的 config 文件夹路径"""
        return os.path.join(self.get_root_path(), "config")

    def get_domain(self):
        """
        获取用户配置的外网访问域名。
        用于给 Telegram 发消息时，里面包含的网页跳转链接。
        """
        domain = (self.get_config('app') or {}).get('domain')
        # 如果用户写了 test.com，这里自动帮他补齐成 http://test.com
        if domain and not domain.startswith('http'):
            domain = "http://" + domain
        return domain

    @staticmethod
    def get_timezone():
        """获取时区"""
        return os.environ.get('TZ')
