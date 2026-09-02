# coding: utf-8
"""
数据库 ORM 模型定义 (app.db.models)
===================================

本模块定义了 NAS-Tools 所有数据库表的 SQLAlchemy ORM 模型。

`Base` 绑定到 user.db（主数据库），存储系统配置和业务数据。

命名约定：
    - 类名使用驼峰命名（CamelCase），如 DownloadHistory
    - Python ORM 属性名、实际数据库表名和列名统一使用小写，如 title
    - 每个模型对应一张数据库表，通过 __tablename__ 指定表名
"""
from sqlalchemy import Column, Float, Index, Integer, Text, text, Sequence
from sqlalchemy.orm import declarative_base

Base = declarative_base()       # user.db 的基类


class ConfigSite(Base):
    """站点配置 —— PT/BT 站点的 RSS 地址、签到地址、Cookie 等连接信息。"""
    __tablename__ = 'config_site'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text)
    pri = Column('pri', Text)
    rssurl = Column('rssurl', Text)
    signurl = Column('signurl', Text)
    cookie = Column('cookie', Text)
    include = Column('include', Text)
    note = Column('note', Text)


class ConfigUsers(Base):
    """用户管理 —— Web 管理后台的用户名、密码和权限配置。"""
    __tablename__ = 'config_users'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text, index=True, unique=True, nullable=False)
    password = Column('password', Text, nullable=False)
    pris = Column('pris', Text, nullable=False)


class DownloadHistory(Base):
    """下载历史 —— 记录每次成功添加到下载器的种子信息（标题、站点、日期等）。"""
    __tablename__ = 'download_history'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    title = Column('title', Text, index=True)
    year = Column('year', Text)
    type = Column('type', Text)
    tmdbid = Column('tmdbid', Text)
    vote = Column('vote', Text)
    poster = Column('poster', Text)
    overview = Column('overview', Text)
    torrent = Column('torrent', Text)
    enclosure = Column('enclosure', Text)
    site = Column('site', Text)
    desc = Column('desc', Text)
    date = Column('date', Text, index=True)

    def as_dict(self):
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}


class DownloadSetting(Base):
    """下载设置 —— 下载器的预设配置方案（分类、标签、限速、做种时间等）。"""
    __tablename__ = 'download_setting'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text)
    category = Column('category', Text)
    tags = Column('tags', Text)
    content_layout = Column('content_layout', Integer)
    is_paused = Column('is_paused', Integer)
    upload_limit = Column('upload_limit', Integer)
    download_limit = Column('download_limit', Integer)
    ratio_limit = Column('ratio_limit', Integer)
    seeding_time_limit = Column('seeding_time_limit', Integer)
    downloader = Column('downloader', Text)
    note = Column('note', Text)


class MessageClient(Base):
    """消息通知渠道 —— 配置 Telegram 消息推送客户端。"""
    __tablename__ = 'message_client'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text)
    type = Column('type', Text)
    config = Column('config', Text)
    switchs = Column('switchs', Text)
    interactive = Column('interactive', Integer)
    enabled = Column('enabled', Integer)
    note = Column('note', Text)












class TorrentRemoveTask(Base):
    """种子清理任务 —— 定时清理下载器中满足条件的种子（做种完成、超时等）。"""
    __tablename__ = 'torrent_remove_task'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text)
    action = Column('action', Integer)
    interval = Column('interval', Integer)
    enabled = Column('enabled', Integer)
    samedata = Column('samedata', Integer)
    onlynastool = Column('onlynastool', Integer)
    downloader = Column('downloader', Text)
    config = Column('config', Text)
    note = Column('note', Text)


class SearchResultInfo(Base):
    """搜索结果缓存 —— 暂存从各站点搜索到的种子信息，供前端展示和用户选择下载。"""
    __tablename__ = 'search_result_info'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    torrent_name = Column('torrent_name', Text)
    enclosure = Column('enclosure', Text)
    description = Column('description', Text)
    type = Column('type', Text)
    title = Column('title', Text)
    year = Column('year', Text)
    season = Column('season', Text)
    episode = Column('episode', Text)
    es_string = Column('es_string', Text)
    vote = Column('vote', Text)
    image = Column('image', Text)
    poster = Column('poster', Text)
    tmdbid = Column('tmdbid', Text)
    overview = Column('overview', Text)
    res_type = Column('res_type', Text)
    res_order = Column('res_order', Text)
    size = Column('size', Integer)
    seeders = Column('seeders', Integer)
    peers = Column('peers', Integer)
    site = Column('site', Text)
    site_order = Column('site_order', Text)
    pageurl = Column('pageurl', Text)
    otherinfo = Column('otherinfo', Text)
    upload_volume_factor = Column('upload_volume_factor', Float)
    download_volume_factor = Column('download_volume_factor', Float)
    note = Column('note', Text)


class SiteBrushDownloaders(Base):
    """刷流专用下载器 —— 站点刷流任务使用的独立下载器配置（与主下载器分离）。"""
    __tablename__ = 'site_brush_downloaders'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text)
    type = Column('type', Text)
    host = Column('host', Text)
    port = Column('port', Text)
    username = Column('username', Text)
    password = Column('password', Text)
    save_dir = Column('save_dir', Text)
    note = Column('note', Text)

    def as_dict(self):
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}


class SiteBrushTask(Base):
    """刷流任务 —— 定义站点刷流的 RSS 规则、删种规则、做种体积、执行间隔等。"""
    __tablename__ = 'site_brush_task'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    name = Column('name', Text, index=True)
    site = Column('site', Text)
    freeleech = Column('freeleech', Text)
    rss_rule = Column('rss_rule', Text)
    remove_rule = Column('remove_rule', Text)
    seed_size = Column('seed_size', Text)
    inteval = Column('inteval', Text)
    downloader = Column('downloader', Text)
    download_count = Column('download_count', Text)
    remove_count = Column('remove_count', Text)
    download_size = Column('download_size', Text)
    upload_size = Column('upload_size', Text)
    sendmessage = Column('sendmessage', Text)
    forceupload = Column('forceupload', Text)
    state = Column('state', Text)
    lst_mod_date = Column('lst_mod_date', Text)


class SiteBrushTorrents(Base):
    """刷流种子记录 —— 记录刷流任务下载的种子信息，用于后续的删种和统计。"""
    __tablename__ = 'site_brush_torrents'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    task_id = Column('task_id', Text, index=True)
    torrent_name = Column('torrent_name', Text)
    torrent_size = Column('torrent_size', Text)
    enclosure = Column('enclosure', Text)
    downloader = Column('downloader', Text)
    download_id = Column('download_id', Text)
    lst_mod_date = Column('lst_mod_date', Text)

    def as_dict(self):
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}


class SiteStatisticsHistory(Base):
    """站点数据历史 —— 按日期记录各站点的上传量/下载量/分享率等数据，用于趋势图。"""
    __tablename__ = 'site_statistics_history'
    __table_args__ = (
        Index('indx_site_statistics_history_ds', 'date', 'url'),
        Index('un_indx_site_statistics_history_ds', 'date', 'url', unique=True)
    )

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    site = Column('site', Text)
    date = Column('date', Text)
    user_level = Column('user_level', Text)
    upload = Column('upload', Text)
    download = Column('download', Text)
    ratio = Column('ratio', Text)
    seeding = Column('seeding', Integer, server_default=text("0"))
    leeching = Column('leeching', Integer, server_default=text("0"))
    seeding_size = Column('seeding_size', Integer, server_default=text("0"))
    bonus = Column('bonus', Float, server_default=text("0.0"))
    url = Column('url', Text)


class SiteSigninHistory(Base):
    """站点签到历史 —— 记录签到或保号登录的执行结果，用于按日重试和状态展示。"""
    __tablename__ = 'site_signin_history'
    __table_args__ = (
        Index('indx_site_signin_history_date_site', 'date', 'site_id', 'action'),
    )

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    site_id = Column('site_id', Integer, index=True)
    site = Column('site', Text)
    action = Column('action', Text)
    success = Column('success', Integer, server_default=text("0"))
    message = Column('message', Text)
    duration = Column('duration', Integer, server_default=text("0"))
    date = Column('date', Text, index=True)
    created_at = Column('created_at', Text)


class SiteUserInfoStats(Base):
    """站点用户信息 —— 当前最新的站点用户数据快照（等级、积分、上传下载量等）。"""
    __tablename__ = 'site_user_info_stats'
    __table_args__ = (
        Index('indx_site_user_info_stats_url', 'url'),
    )

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    site = Column('site', Text, index=True)
    username = Column('username', Text)
    user_level = Column('user_level', Text)
    join_at = Column('join_at', Text)
    update_at = Column('update_at', Text)
    upload = Column('upload', Integer)
    download = Column('download', Integer)
    ratio = Column('ratio', Float)
    seeding = Column('seeding', Integer)
    leeching = Column('leeching', Integer)
    seeding_size = Column('seeding_size', Integer)
    bonus = Column('bonus', Float)
    url = Column('url', Text, unique=True)
    msg_unread = Column('msg_unread', Integer)
    ext_info = Column('ext_info', Text)


class SiteFavicon(Base):
    """站点图标缓存 —— 缓存各站点的 favicon 图标数据，避免重复请求。"""
    __tablename__ = 'site_favicon'

    site = Column('site', Text, primary_key=True)
    url = Column('url', Text)
    favicon = Column('favicon', Text)


class SiteUserSeedingInfo(Base):
    """站点做种信息 —— 记录用户在各站点的做种详情（JSON 格式存储）。"""
    __tablename__ = 'site_user_seeding_info'

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    site = Column('site', Text, index=True)
    seeding_info = Column('seeding_info', Text, server_default=text("'[]'"))
    update_at = Column('update_at', Text)
    url = Column('url', Text, unique=True)


class SystemDict(Base):
    """系统字典 —— 通用的键值对存储表，用于保存各类系统级配置和状态数据。"""
    __tablename__ = 'system_dict'
    __table_args__ = (
        Index('indx_system_dict', 'type', 'key'),
    )

    id = Column('id', Integer, Sequence('id'), primary_key=True)
    type = Column('type', Text)
    key = Column('key', Text)
    value = Column('value', Text)
    note = Column('note', Text)
