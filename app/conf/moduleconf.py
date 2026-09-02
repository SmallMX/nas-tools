# coding: utf-8
from app.utils.types import *


class ModuleConf(object):
    # 下载器
    DOWNLOADER_DICT = {
        "qbittorrent": DownloaderType.QB,
        "transmission": DownloaderType.TR,
    }

    # 消息通知类型
    MESSAGE_CONF = {
        "client": {
            "telegram": {
                "name": "Telegram",
                "img_url": "../static/img/telegram.png",
                "search_type": SearchType.TG,
                "config": {
                    "token": {
                        "id": "telegram_token",
                        "required": True,
                        "title": "Bot Token",
                        "tooltip": "telegram机器人的Token，关注BotFather创建机器人",
                        "type": "password"
                    },
                    "chat_id": {
                        "id": "telegram_chat_id",
                        "required": True,
                        "title": "Chat ID",
                        "tooltip": "接受消息通知的用户、群组或频道Chat ID，关注@getidsbot获取",
                        "type": "text"
                    },
                    "user_ids": {
                        "id": "telegram_user_ids",
                        "required": False,
                        "title": "User IDs",
                        "tooltip": "允许使用交互的用户Chat ID，留空则只允许管理用户使用，关注@getidsbot获取",
                        "type": "text",
                        "placeholder": "使用,分隔多个Id"
                    },
                    "admin_ids": {
                        "id": "telegram_admin_ids",
                        "required": False,
                        "title": "Admin IDs",
                        "tooltip": "允许使用管理命令的用户Chat ID，关注@getidsbot获取",
                        "type": "text",
                        "placeholder": "使用,分隔多个Id"
                    },
                    "webhook": {
                        "id": "telegram_webhook",
                        "required": False,
                        "title": "Webhook",
                        "tooltip": "Telegram机器人消息有两种模式：Webhook或消息轮循；开启后将使用Webhook方式，需要在基础设置中正确配置好由反向代理提供HTTPS的外网访问地址，同时受Telegram官方限制，端口需为443、80、88、8443之一；关闭后将使用消息轮循方式，此时需要在基础设置->安全处将Telegram IPv4源地址设置为127.0.0.1",
                        "type": "switch"
                    }
                }
            },
        },
        "switch": {
            "download_start": {
                "name": "新增下载",
                "fuc_name": "download_start"
            },
            "download_fail": {
                "name": "下载失败",
                "fuc_name": "download_fail"
            },
            "site_signin": {
                "name": "站点签到",
                "fuc_name": "site_signin"
            },
            "site_message": {
                "name": "站点消息",
                "fuc_name": "site_message"
            },
            "brushtask_added": {
                "name": "刷流下种",
                "fuc_name": "brushtask_added"
            },
            "brushtask_remove": {
                "name": "刷流删种",
                "fuc_name": "brushtask_remove"
            },

            "custom_message": {
                "name": "自定义消息",
                "fuc_name": "custom_message"
            }
        }
    }

    # 自动删种配置
    TORRENTREMOVER_DICT = {
        "Qb": {
            "name": "Qbittorrent",
            "img_url": "../static/img/qbittorrent.png",
            "downloader_type": DownloaderType.QB,
            "torrent_state": {
                "downloading": "正在下载_传输数据",
                "stalledDL": "正在下载_未建立连接",
                "uploading": "正在上传_传输数据",
                "stalledUP": "正在上传_未建立连接",
                "error": "暂停_发生错误",
                "pausedDL": "暂停_下载未完成",
                "pausedUP": "暂停_下载完成",
                "missingFiles": "暂停_文件丢失",
                "checkingDL": "检查中_下载未完成",
                "checkingUP": "检查中_下载完成",
                "checkingResumeData": "检查中_启动时恢复数据",
                "forcedDL": "强制下载_忽略队列",
                "queuedDL": "等待下载_排队",
                "forcedUP": "强制上传_忽略队列",
                "queuedUP": "等待上传_排队",
                "allocating": "分配磁盘空间",
                "metaDL": "获取元数据",
                "moving": "移动文件",
                "unknown": "未知状态",
            }
        },
        "Tr": {
            "name": "Transmission",
            "img_url": "../static/img/transmission.png",
            "downloader_type": DownloaderType.TR,
            "torrent_state": {
                "downloading": "正在下载",
                "seeding": "正在上传",
                "download_pending": "等待下载_排队",
                "seed_pending": "等待上传_排队",
                "checking": "正在检查",
                "check_pending": "等待检查_排队",
                "stopped": "暂停",
            }
        }
    }

    # 搜索种子过滤属性
    TORRENT_SEARCH_PARAMS = {
        "restype": {
            "BLURAY": r"Blu-?Ray|BD|BDRIP",
            "REMUX": r"REMUX",
            "DOLBY": r"DOLBY|DOVI|\s+DV$|\s+DV\s+",
            "WEB": r"WEB-?DL|WEBRIP",
            "HDTV": r"U?HDTV",
            "UHD": r"UHD",
            "HDR": r"HDR",
            "3D": r"3D"
        },
        "pix": {
            "8k": r"8K",
            "4k": r"4K|2160P|X2160",
            "1080p": r"1080[PIX]|X1080",
            "720p": r"720P"
        }
    }

    # 网络测试对象
    NETTEST_TARGETS = [
        "www.themoviedb.org",
        "api.themoviedb.org",
        "api.tmdb.org",
        "image.tmdb.org",
        "webservice.fanart.tv",
        "api.telegram.org"
    ]

    # 下载器
    DOWNLOADER_CONF = {
        "qbittorrent": {
            "name": "Qbittorrent",
            "img_url": "../static/img/qbittorrent.png",
            "background": "bg-blue",
            "test_command": "qbittorrent",
            "config": {
                "qbhost": {
                    "id": "qbittorrent.qbhost",
                    "required": True,
                    "title": "IP地址",
                    "tooltip": "配置IP地址，如为https则需要增加https://前缀",
                    "type": "text",
                    "placeholder": "127.0.0.1"
                },
                "qbport": {
                    "id": "qbittorrent.qbport",
                    "required": True,
                    "title": "端口",
                    "type": "text",
                    "placeholder": "8080"
                },
                "qbusername": {
                    "id": "qbittorrent.qbusername",
                    "required": True,
                    "title": "用户名",
                    "type": "text",
                    "placeholder": "admin"
                },
                "qbpassword": {
                    "id": "qbittorrent.qbpassword",
                    "required": False,
                    "title": "密码",
                    "type": "password",
                    "placeholder": "adminadmin"
                },
                "verify_cert": {
                    "id": "qbittorrent.verify_cert",
                    "required": False,
                    "title": "验证 HTTPS 证书",
                    "tooltip": "默认开启；使用自签名证书时可显式关闭",
                    "type": "switch"
                },
                "auto_management": {
                    "id": "qbittorrent.auto_management",
                    "required": False,
                    "title": "自动管理模式",
                    "tooltip": "开启后下载目录将由Qbittorrent自动管理，不再使用NASTool传递的下载目录，需要同时在下载目录设置中配置好分类标签",
                    "type": "switch"
                }
            }
        },
        "transmission": {
            "name": "Transmission",
            "img_url": "../static/img/transmission.png",
            "background": "bg-danger",
            "test_command": "transmission",
            "config": {
                "trhost": {
                    "id": "transmission.trhost",
                    "required": True,
                    "title": "IP地址",
                    "tooltip": "配置IP地址，如为https则需要增加https://前缀",
                    "type": "text",
                    "placeholder": "127.0.0.1"
                },
                "trport": {
                    "id": "transmission.trport",
                    "required": True,
                    "title": "端口",
                    "type": "text",
                    "placeholder": "9091"
                },
                "trusername": {
                    "id": "transmission.trusername",
                    "required": True,
                    "title": "用户名",
                    "type": "text",
                    "placeholder": "admin"
                },
                "trpassword": {
                    "id": "transmission.trpassword",
                    "required": False,
                    "title": "密码",
                    "type": "password",
                    "placeholder": ""
                }
            }
        }


    }

    # 发现过滤器
    DISCOVER_FILTER_CONF = {
        "tmdb_movie": {
            "with_genres": {
                "name": "类型",
                "type": "dropdown",
                "options": [{'value': '', 'name': '全部'},
                            {'value': '12', 'name': '冒险'},
                            {'value': '16', 'name': '动画'},
                            {'value': '35', 'name': '喜剧'},
                            {'value': '80', 'name': '犯罪'},
                            {'value': '18', 'name': '剧情'},
                            {'value': '14', 'name': '奇幻'},
                            {'value': '27', 'name': '恐怖'},
                            {'value': '9648', 'name': '悬疑'},
                            {'value': '10749', 'name': '爱情'},
                            {'value': '878', 'name': '科幻'},
                            {'value': '53', 'name': '惊悚'},
                            {'value': '10752', 'name': '战争'}]
            },
            "with_original_language": {
                "name": "语言",
                "type": "dropdown",
                "options": [{'value': '', 'name': '全部'},
                            {'value': 'zh', 'name': '中文'},
                            {'value': 'en', 'name': '英语'},
                            {'value': 'ja', 'name': '日语'},
                            {'value': 'ko', 'name': '韩语'},
                            {'value': 'fr', 'name': '法语'},
                            {'value': 'de', 'name': '德语'},
                            {'value': 'ru', 'name': '俄语'},
                            {'value': 'hi', 'name': '印地语'}]
            }
        },
        "tmdb_tv": {
            "with_genres": {
                "name": "类型",
                "type": "dropdown",
                "options": [{'value': '', 'name': '全部'},
                            {'value': '10759', 'name': '动作冒险'},
                            {'value': '16', 'name': '动画'},
                            {'value': '35', 'name': '喜剧'},
                            {'value': '80', 'name': '犯罪'},
                            {'value': '99', 'name': '纪录'},
                            {'value': '18', 'name': '剧情'},
                            {'value': '10762', 'name': '儿童'},
                            {'value': '9648', 'name': '悬疑'},
                            {'value': '10764', 'name': '真人秀'},
                            {'value': '10765', 'name': '科幻'}]
            },
            "with_original_language": {
                "name": "语言",
                "type": "dropdown",
                "options": [{'value': '', 'name': '全部'},
                            {'value': 'zh', 'name': '中文'},
                            {'value': 'en', 'name': '英语'},
                            {'value': 'ja', 'name': '日语'},
                            {'value': 'ko', 'name': '韩语'},
                            {'value': 'fr', 'name': '法语'},
                            {'value': 'de', 'name': '德语'},
                            {'value': 'ru', 'name': '俄语'},
                            {'value': 'hi', 'name': '印地语'}]
            }
        }
    }

    @staticmethod
    def get_enum_name(enum, value):
        """
        根据Enum的value查询name
        :param enum: 枚举
        :param value: 枚举值
        :return: 枚举名或None
        """
        for e in enum:
            if e.value == value:
                return e.name
        return None

    @staticmethod
    def get_enum_item(enum, value):
        """
        根据Enum的value查询name
        :param enum: 枚举
        :param value: 枚举值
        :return: 枚举项
        """
        for e in enum:
            if e.value == value:
                return e
        return None

    @staticmethod
    def get_dictenum_key(dictenum, value):
        """
        根据Enum dict的value查询key
        :param dictenum: 枚举字典
        :param value: 枚举类（字典值）的值
        :return: 字典键或None
        """
        for k, v in dictenum.items():
            if v.value == value:
                return k
        return None
