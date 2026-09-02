import json
import re

import log
from app.conf import ModuleConf
from app.helper import DbHelper
from app.message.client.telegram import Telegram
from app.message.message_center import MessageCenter
from app.utils import StringUtils, ExceptionUtils
from app.utils.commons import singleton
from app.utils.types import SearchType
from config import Config


@singleton
class Message(object):
    dbhelper = None
    messagecenter = None
    _message_schemas = (Telegram,)
    _active_clients = []
    _active_interactive_clients = {}
    _client_configs = {}
    _domain = None

    def __init__(self):
        log.debug(f"【Message】加载消息服务：{self._message_schemas}")
        self.init_config()

    def init_config(self):
        self.dbhelper = DbHelper()
        self.messagecenter = MessageCenter()
        self._domain = Config().get_domain()
        # 停止旧服务
        self.stop_service()
        # 活跃的客户端
        self._active_clients = []
        # 活跃的交互客户端
        self._active_interactive_clients = {}
        # 全量客户端配置
        self._client_configs = {}
        for client_config in self.dbhelper.get_message_client() or []:
            config = json.loads(client_config.config) if client_config.config else {}
            config.update({
                "interactive": client_config.interactive
            })
            client_conf = {
                "id": client_config.id,
                "name": client_config.name,
                "type": client_config.type,
                "config": config,
                "switchs": json.loads(client_config.switchs) if client_config.switchs else [],
                "interactive": client_config.interactive,
                "enabled": client_config.enabled
            }
            self._client_configs[str(client_config.id)] = client_conf
            if not client_config.enabled or not config:
                continue
            client = {
                "search_type": ModuleConf.MESSAGE_CONF.get('client').get(client_config.type, {}).get('search_type'),
                "client": self.__build_class(ctype=client_config.type, conf=config)
            }
            client.update(client_conf)
            self._active_clients.append(client)
            if client.get("interactive"):
                self._active_interactive_clients[client.get("search_type")] = client

    def stop_service(self):
        active_clients = list(self._active_clients or [])
        self._active_clients = []
        self._active_interactive_clients = {}
        for active_client in active_clients:
            client = active_client.get("client")
            if not client or not hasattr(client, "stop_service"):
                continue
            try:
                client.stop_service()
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Message】停止消息客户端 %s 失败：%s" % (active_client.get("name"), str(err)))

    def __build_class(self, ctype, conf):
        for message_schema in self._message_schemas:
            try:
                if message_schema.match(ctype):
                    return message_schema(conf)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
        return None

    def get_status(self, ctype=None, config=None):
        """
        测试消息设置状态
        """
        if not config or not ctype:
            return False
        # 测试状态不启动监听服务
        state, ret_msg = self.__build_class(ctype=ctype,
                                            conf=config).send_msg(title="测试",
                                                                  text="这是一条测试消息",
                                                                  url="https://github.com/SmallMX/nas-tools")
        if not state:
            log.error(f"【Message】{ctype} 发送测试消息失败：%s" % ret_msg)
        return state

    def __sendmsg(self, client, title, text="", image="", url="", user_id=""):
        """
        通用消息发送
        :param client: 消息端
        :param title: 消息标题
        :param text: 消息内容
        :param image: 图片URL
        :param url: 消息跳转地址
        :param user_id: 用户ID，如有则只发给这个用户
        :return: 发送状态、错误信息
        """
        if not client or not client.get('client'):
            return None
        cname = client.get('name')
        log.info(f"【Message】发送消息 {cname}：title={title}, text={text}")
        if self._domain:
            if url:
                if not url.startswith("http"):
                    url = "%s?next=%s" % (self._domain, url)
            else:
                url = self._domain
        else:
            url = ""
        state, ret_msg = client.get('client').send_msg(title=title,
                                                       text=text,
                                                       image=image,
                                                       url=url,
                                                       user_id=user_id)
        if not state:
            log.error(f"【Message】{cname} 消息发送失败：%s" % ret_msg)
        return state

    def send_channel_msg(self, channel, title, text="", image="", url="", user_id=""):
        """
        按渠道发送消息，用于消息交互
        :param channel: 消息渠道
        :param title: 消息标题
        :param text: 消息内容
        :param image: 图片URL
        :param url: 消息跳转地址
        :param user_id: 用户ID，如有则只发给这个用户
        :return: 发送状态、错误信息
        """
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        client = self._active_interactive_clients.get(channel)
        if client:
            state = self.__sendmsg(client=client,
                                   title=title,
                                   text=text,
                                   image=image,
                                   url=url,
                                   user_id=user_id)
            return state
        return False

    def __send_list_msg(self, client, medias, user_id, title):
        """
        发送选择类消息
        """
        if not client or not client.get('client'):
            return None
        cname = client.get('name')
        log.info(f"【Message】发送消息 {cname}：title={title}")
        state, ret_msg = client.get('client').send_list_msg(medias=medias,
                                                            user_id=user_id,
                                                            title=title,
                                                            url=self._domain)
        if not state:
            log.error(f"【Message】{cname} 发送消息失败：%s" % ret_msg)
        return state

    def send_channel_list_msg(self, channel, title, medias: list, user_id=""):
        """
        发送列表选择消息，用于消息交互
        :param channel: 消息渠道
        :param title: 消息标题
        :param medias: 媒体信息列表
        :param user_id: 用户ID，如有则只发给这个用户
        :return: 发送状态、错误信息
        """
        client = self._active_interactive_clients.get(channel)
        if client:
            state = self.__send_list_msg(client=client,
                                         title=title,
                                         medias=medias,
                                         user_id=user_id)
            return state
        return False

    def send_download_message(self, in_from: SearchType, can_item):
        """
        发送下载的消息
        :param in_from: 下载来源
        :param can_item: 下载的媒体信息
        :return: 发送状态、错误信息
        """
        msg_title = f"{can_item.get_title_ep_string()} 开始下载"
        msg_text = f"{can_item.get_star_string()}"
        msg_text = f"{msg_text}\n来自：{in_from.value}"
        if can_item.user_name:
            msg_text = f"{msg_text}\n用户：{can_item.user_name}"
        if can_item.site:
            msg_text = f"{msg_text}\n站点：{can_item.site}"
        if can_item.get_resource_type_string():
            msg_text = f"{msg_text}\n质量：{can_item.get_resource_type_string()}"
        if can_item.size:
            if str(can_item.size).isdigit():
                size = StringUtils.str_filesize(can_item.size)
            else:
                size = can_item.size
            msg_text = f"{msg_text}\n大小：{size}"
        if can_item.org_string:
            msg_text = f"{msg_text}\n种子：{can_item.org_string}"
        if can_item.seeders:
            msg_text = f"{msg_text}\n做种数：{can_item.seeders}"
        msg_text = f"{msg_text}\n促销：{can_item.get_volume_factor_string()}"
        if can_item.hit_and_run:
            msg_text = f"{msg_text}\nHit&Run：是"
        if can_item.description:
            html_re = re.compile(r'<[^>]+>', re.S)
            description = html_re.sub('', can_item.description)
            can_item.description = re.sub(r'<[^>]+>', '', description)
            msg_text = f"{msg_text}\n描述：{can_item.description}"
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=msg_title, content=msg_text)
        # 发送消息
        for client in self._active_clients:
            if "download_start" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_text,
                    image=can_item.get_message_image(),
                    url='downloading'
                )

    def send_download_fail_message(self, item, error_msg):
        """
        发送下载失败的消息
        """
        title = "添加下载任务失败：%s %s" % (item.get_title_string(), item.get_season_episode_string())
        text = f"站点：{item.site}\n种子名称：{item.org_string}\n错误信息：{error_msg}"
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        for client in self._active_clients:
            if "download_fail" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=item.get_message_image()
                )



    def send_site_signin_message(self, msgs: list):
        """
        发送站点签到消息
        """
        if not msgs:
            return
        title = "站点签到"
        text = "\n".join(msgs)
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        for client in self._active_clients:
            if "site_signin" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text
                )

    def send_site_message(self, title=None, text=None):
        """
        发送站点消息
        """
        if not title:
            return
        if not text:
            text = ""
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        for client in self._active_clients:
            if "site_message" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text
                )

    def send_brushtask_remove_message(self, title, text):
        """
        发送刷流删种的消息
        """
        if not title or not text:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        for client in self._active_clients:
            if "brushtask_remove" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask"
                )

    def send_brushtask_added_message(self, title, text):
        """
        发送刷流下种的消息
        """
        if not title or not text:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        for client in self._active_clients:
            if "brushtask_added" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask"
                )


    def send_custom_message(self, title, text="", image=""):
        """
        发送自定义消息
        """
        if not title:
            return
        # 插入消息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 发送消息
        for client in self._active_clients:
            if "custom_message" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=image
                )

    def get_message_client_info(self, cid=None):
        """
        获取消息端信息
        """
        if cid:
            return self._client_configs.get(str(cid))
        return self._client_configs

    def get_interactive_client(self, client_type=None):
        """
        查询当前可以交互的渠道
        """
        if client_type:
            return self._active_interactive_clients.get(client_type)
        else:
            return [client for client in self._active_interactive_clients.values()]

    @staticmethod
    def get_search_types():
        """
        查询可交互的渠道
        """
        return [info.get("search_type")
                for info in ModuleConf.MESSAGE_CONF.get('client').values()
                if info.get('search_type')]
