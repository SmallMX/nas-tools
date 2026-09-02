from enum import Enum


class MediaType(Enum):
    TV = '电视剧'
    MOVIE = '电影'
    ANIME = '动漫'
    UNKNOWN = '未知'


class DownloaderType(Enum):
    QB = 'Qbittorrent'
    TR = 'Transmission'


class SearchType(Enum):
    WEB = "WEB"
    DB = "豆瓣"
    OT = "手动下载"
    TG = "Telegram"
    API = "第三方API请求"


class MatchMode(Enum):
    NORMAL = "正常模式"
    STRICT = "严格模式"


class OsType(Enum):
    LINUX = "Linux"
    MACOS = "MacOS"
    DOCKER = "Docker"


class IndexerType(Enum):
    BUILTIN = "Indexer"




class BrushDeleteType(Enum):
    NOTDELETE = "不删除"
    SEEDTIME = "做种时间"
    RATIO = "分享率"
    UPLOADSIZE = "上传量"
    DLTIME = "下载耗时"
    AVGUPSPEED = "平均上传速度"
    IATIME = "未活动时间"


# 站点框架
class SiteSchema(Enum):
    DiscuzX = "Discuz!"
    Gazelle = "Gazelle"
    Ipt = "IPTorrents"
    NexusPhp = "NexusPhp"
    NexusProject = "NexusProject"
    NexusRabbit = "NexusRabbit"
    SmallHorse = "Small Horse"
    Unit3d = "Unit3d"
    TorrentLeech = "TorrentLeech"
    FileList = "FileList"
    TNode = "TNode"


MovieTypes = ['MOV', '电影']
TvTypes = ['TV', '电视剧']
