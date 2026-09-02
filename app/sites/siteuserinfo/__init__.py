from .discuz import DiscuzUserInfo
from .file_list import FileListSiteUserInfo
from .gazelle import GazelleSiteUserInfo
from .ipt_project import IptSiteUserInfo
from .nexus_php import NexusPhpSiteUserInfo
from .nexus_project import NexusProjectSiteUserInfo
from .nexus_rabbit import NexusRabbitSiteUserInfo
from .small_horse import SmallHorseSiteUserInfo
from .tnode import TNodeSiteUserInfo
from .torrent_leech import TorrentLeechSiteUserInfo
from .unit3d import Unit3dSiteUserInfo


SITE_USER_INFO_HANDLERS = (
    GazelleSiteUserInfo,
    NexusRabbitSiteUserInfo,
    DiscuzUserInfo,
    Unit3dSiteUserInfo,
    NexusProjectSiteUserInfo,
    SmallHorseSiteUserInfo,
    IptSiteUserInfo,
    TorrentLeechSiteUserInfo,
    FileListSiteUserInfo,
    TNodeSiteUserInfo,
    NexusPhpSiteUserInfo,
)
