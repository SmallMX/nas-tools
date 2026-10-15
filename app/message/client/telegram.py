import re
from html import escape
from threading import Event, Lock
from urllib.parse import quote, urlencode

import requests

import log
from app.helper import ThreadHelper
from app.message.client._base import _IMessageClient
from app.utils import RequestUtils, ExceptionUtils
from config import Config

_webhook_registration_lock = Lock()
TELEGRAM_LOCAL_CALLBACK_URL = "http://127.0.0.1:3000/telegram"


class Telegram(_IMessageClient):
    schema = "telegram"

    _telegram_token = None
    _telegram_chat_id = None
    _webhook = None
    _webhook_url = None
    _webhook_secret = None
    _webhook_dirty = False
    _telegram_user_ids = []
    _telegram_admin_ids = []
    _domain = None
    _message_proxy_event = None
    _client_config = {}
    _interactive = False
    _enabled = True

    def __init__(self, config):
        self._client_config = config
        self._interactive = config.get("interactive")
        self.init_config()

    def init_config(self):
        if self._client_config:
            self._enabled = True
            self._telegram_token = self._client_config.get('token')
            self._telegram_chat_id = self._client_config.get('chat_id')
            self._webhook = self._client_config.get('webhook')
            self._load_runtime_config()
            self._telegram_admin_ids = []
            telegram_admin_ids = self._client_config.get('admin_ids')
            if telegram_admin_ids:
                self._telegram_admin_ids = [
                    item.strip() for item in telegram_admin_ids.split(",") if item.strip()
                ]
            self._telegram_user_ids = list(self._telegram_admin_ids)
            telegram_user_ids = self._client_config.get('user_ids')
            if telegram_user_ids:
                self._telegram_user_ids.extend(
                    item.strip() for item in telegram_user_ids.split(",") if item.strip()
                )
            if self._telegram_token and self._telegram_chat_id:
                if self._webhook:
                    if self._webhook_url:
                        self.__set_bot_webhook()
                    if self._message_proxy_event:
                        self._message_proxy_event.set()
                        self._message_proxy_event = None
                elif self._interactive:
                    self.__del_bot_webhook()
                    if not self._message_proxy_event:
                        event = Event()
                        self._message_proxy_event = event
                        ThreadHelper().start_thread(self.__start_telegram_message_proxy, [event])

    def _load_runtime_config(self):
        config = Config()
        self._domain = (config.get_domain() or '').rstrip('/')
        self._webhook_secret = config.get_config('security').get('telegram_webhook_secret')
        self._webhook_url = "%s/telegram" % self._domain if self._webhook and self._domain else None

    def reload_runtime_config(self):
        """刷新回调地址和密钥，不重启轮询或重置已消费消息的位置。"""
        previous = (self._domain, self._webhook_url, self._webhook_secret)
        succeeded = False
        try:
            self._load_runtime_config()
            if not (self._enabled and self._telegram_token and self._telegram_chat_id and self._webhook):
                succeeded = True
            elif self._webhook_url and self._webhook_secret:
                _, previous_url, previous_secret = previous
                if previous_url == self._webhook_url and previous_secret == self._webhook_secret \
                        and not self._webhook_dirty:
                    succeeded = True
                else:
                    force = self._webhook_dirty or previous_secret != self._webhook_secret
                    # 删除旧回调或响应丢失后，远端状态不能再由本地配置相等推断。
                    self._webhook_dirty = True
                    succeeded = self.__set_bot_webhook(force=force)
                    if succeeded:
                        self._webhook_dirty = False
            return succeeded
        except Exception as error:
            log.error("【Telegram】刷新 Webhook 配置失败：%s" % type(error).__name__)
            return False
        finally:
            if not succeeded:
                # 注册失败仍保留上次状态，重复保存相同配置时可以继续重试。
                self._domain, self._webhook_url, self._webhook_secret = previous

    @classmethod
    def match(cls, ctype):
        return True if ctype == cls.schema else False

    def get_admin(self):
        """
        获取允许使用远程命令的user_id列表
        """
        return self._telegram_admin_ids

    def get_users(self):
        """
        获取允许使用telegram机器人的user_id列表
        """
        return self._telegram_user_ids

    def send_msg(self, title, text="", image="", url="", user_id=""):
        """
        发送Telegram消息
        :param title: 消息标题
        :param text: 消息内容
        :param image: 消息图片地址
        :param url: 点击消息转转的URL
        :param user_id: 用户ID，如有则只发消息给该用户
        :user_id: 发送消息的目标用户ID，为空则发给管理员
        """
        if not title and not text:
            return False, "标题和内容不能同时为空"
        try:
            if not self._telegram_token or not self._telegram_chat_id:
                return False, "参数未配置"

            # 先保留原文，再转义展示内容，避免纯文本降级时带上格式标记。
            text = str(text or "")
            titles = str(title or "").split('\n')
            title = titles[0]
            if len(titles) > 1:
                if not text:
                    text = "\n".join(titles[1:])
                else:
                    text = "%s\n%s" % ("\n".join(titles[1:]), text)
            text = text.replace("\n\n", "\n")
            if title and text:
                plain_caption = "%s\n%s" % (title, text)
                caption = "<b>%s</b>\n%s" % (escape(title), escape(text))
            elif text:
                plain_caption = text
                caption = escape(text)
            else:
                plain_caption = title
                caption = escape(title)
            if image and url:
                caption = '%s\n\n<a href="%s">查看详情</a>' % (caption, escape(str(url)))
                plain_caption = "%s\n\n查看详情：%s" % (plain_caption, url)
            if user_id:
                chat_id = user_id
            else:
                chat_id = self._telegram_chat_id

            return self.__send_request(chat_id=chat_id, image=image, caption=caption,
                                       plain_caption=plain_caption)

        except Exception as msg_e:
            message = self._redact_delivery_error(msg_e)
            log.error("【Telegram】发送消息失败：%s" % message)
            return False, message

    def send_list_msg(self, medias: list, user_id="", title="", **kwargs):
        """
        发送列表类消息
        """
        try:
            if not self._telegram_token or not self._telegram_chat_id:
                return False, "参数未配置"
            if not title or not isinstance(medias, list):
                return False, "数据错误"
            image, caption = "", "<b>%s</b>" % escape(str(title))
            plain_caption = str(title)
            for index, media in enumerate(medias, start=1):
                if not image:
                    image = media.get_message_image()
                media_title = str(media.get_title_string() or "")
                detail_url = str(media.get_detail_url() or "")
                description = str(media.get_type_string() or "")
                vote = media.get_vote_string()
                if vote:
                    description = "%s，%s" % (description, vote)
                caption = '%s\n%s. <a href="%s">%s</a>\n%s' % (
                    caption, index, escape(detail_url), escape(media_title), escape(description))
                plain_caption = "%s\n%s. %s\n%s\n%s" % (
                    plain_caption, index, media_title, detail_url, description)

            if user_id:
                chat_id = user_id
            else:
                chat_id = self._telegram_chat_id

            return self.__send_request(chat_id=chat_id, image=image, caption=caption,
                                       plain_caption=plain_caption)

        except Exception as msg_e:
            message = self._redact_delivery_error(msg_e)
            log.error("【Telegram】发送列表消息失败：%s" % message)
            return False, message

    def _redact_delivery_error(self, error):
        # 请求异常可能带有完整 URL，其中包括令牌、图片签名或消息内容。
        message = re.sub(r'https?://[^\s<>"\']+', '<redacted-url>', str(error))
        for secret in (self._telegram_token, self._webhook_secret):
            if secret:
                message = message.replace(str(secret), "<redacted>")
                message = message.replace(quote(str(secret), safe=""), "<redacted>")
        return message

    @staticmethod
    def _can_fallback_to_plain(error_code, description, image):
        if error_code != 400:
            return False
        description = description.lower()
        if "can't parse entities" in description or "can't parse message text" in description:
            return True
        return bool(image) and any(reason in description for reason in (
            "failed to get http url content",
            "wrong type of the web page content",
            "wrong file identifier/http url specified",
            "wrong remote file identifier specified",
            "photo_invalid",
            "photo_content_type_invalid",
            "photo_ext_invalid",
            "image_process_failed",
            "photo must be non-empty",
            "file is too big",
            "message caption is too long",
            "media_caption_too_long",
        ))

    def __send_request(self, chat_id="", image="", caption="", plain_caption=None):
        """
        向Telegram发送报文
        """
        def _res_parse(result):
            if result is None:
                return False, "未获取到返回信息", False
            status_code = result.status_code
            try:
                ret_json = result.json()
            except ValueError:
                return False, "Telegram 返回非 JSON 响应（HTTP %s）" % status_code, False
            if not isinstance(ret_json, dict):
                return False, "Telegram 返回信息格式错误", False
            if ret_json.get("ok") is True:
                return True, "", False
            error_code = ret_json.get("error_code") or status_code
            description = str(ret_json.get("description") or "未获取到错误描述")
            if isinstance(error_code, int):
                message = "Telegram %s: %s" % (error_code, description)
            else:
                message = description
            can_fallback = (status_code == 400
                            and self._can_fallback_to_plain(error_code, description, image))
            return False, self._redact_delivery_error(message), can_fallback

        proxies = Config().get_proxies()
        if image:
            # 发送图文消息
            values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "HTML"}
            sc_url = "https://api.telegram.org/bot%s/sendPhoto?" % self._telegram_token
        else:
            # 发送文本消息
            values = {"chat_id": chat_id, "text": caption, "parse_mode": "HTML"}
            sc_url = "https://api.telegram.org/bot%s/sendMessage?" % self._telegram_token
        res = RequestUtils(proxies=proxies).get_res(sc_url + urlencode(values))
        flag, msg, can_fallback = _res_parse(res)
        if not flag and can_fallback and plain_caption is not None:
            log.warn("【Telegram】消息被拒绝，降级为纯文本发送：%s" % msg)
            # 只对明确未送达的内容错误降级一次；网络超时、认证和限流错误不重发。
            values = {"chat_id": chat_id, "text": plain_caption}
            sc_url = "https://api.telegram.org/bot%s/sendMessage?" % self._telegram_token
            res = RequestUtils(proxies=proxies).get_res(sc_url + urlencode(values))
            flag, fallback_msg, _ = _res_parse(res)
            if not flag:
                return False, "%s；纯文本发送失败：%s" % (msg, fallback_msg)
            return True, ""
        return flag, msg

    def __set_bot_webhook(self, force=False):
        """
        设置Telegram Webhook
        """
        if not self._webhook_url or not self._telegram_token:
            return False

        with _webhook_registration_lock:
            if not self._webhook_secret:
                log.error("【Telegram】Webhook 密钥未初始化，拒绝注册不安全的 Webhook")
                return False
            status = self.__get_bot_webhook()
            if not status:
                return False
            if status == 1 and not force:
                return True
            if status == 2:
                self.__del_bot_webhook()
            values = {
                "url": self._webhook_url,
                "allowed_updates": ["message"],
                "secret_token": self._webhook_secret,
            }
            sc_url = "https://api.telegram.org/bot%s/setWebhook?" % self._telegram_token
            res = RequestUtils(proxies=Config().get_proxies()).get_res(sc_url + urlencode(values))
            if res is not None:
                response_data = res.json()
                if response_data.get("ok"):
                    log.info("【Telegram】Webhook 设置成功，地址为：%s" % self._webhook_url)
                    return True
                else:
                    log.error("【Telegram】Webhook 设置失败：%s" % response_data.get("description"))
            else:
                log.error("【Telegram】Webhook 设置失败：网络连接故障！")
            return False

    def __get_bot_webhook(self):
        """
        获取Telegram已设置的Webhook
        :return: 状态：1-存在且相等，2-存在不相等，3-不存在，0-网络出错
        """
        sc_url = "https://api.telegram.org/bot%s/getWebhookInfo" % self._telegram_token
        res = RequestUtils(proxies=Config().get_proxies()).get_res(sc_url)
        if res is not None and res.json():
            if res.json().get("ok"):
                result = res.json().get("result") or {}
                webhook_url = result.get("url") or ""
                if webhook_url:
                    log.info("【Telegram】Webhook 地址为：%s" % webhook_url)
                pending_update_count = result.get("pending_update_count")
                last_error_message = result.get("last_error_message")
                if pending_update_count and last_error_message:
                    log.warn("【Telegram】Webhook 有 %s 条消息挂起，最后一次失败原因为：%s" % (
                        pending_update_count, last_error_message))
                if webhook_url == self._webhook_url:
                    return 1
                else:
                    return 2
            else:
                return 3
        else:
            return 0

    def __del_bot_webhook(self):
        """
        删除Telegram Webhook
        :return: 是否成功
        """
        sc_url = "https://api.telegram.org/bot%s/deleteWebhook" % self._telegram_token
        res = RequestUtils(proxies=Config().get_proxies()).get_res(sc_url)
        if res and res.json() and res.json().get("ok"):
            return True
        else:
            return False

    def __start_telegram_message_proxy(self, event: Event):
        log.info("Telegram消息接收服务启动")

        long_poll_timeout = 5

        def consume_messages(_config, _offset, _sc_url, _ds_url):
            try:
                values = {"timeout": long_poll_timeout, "offset": _offset}
                res = RequestUtils(proxies=_config.get_proxies()).get_res(_sc_url + urlencode(values))
                if res and res.json():
                    for msg in res.json().get("result", []):
                        # 无论本地是否成功，先更新offset，即消息最多成功消费一次
                        _offset = msg["update_id"] + 1
                        log.debug("【Telegram】接收到消息: %s" % msg)
                        local_res = requests.post(
                            _ds_url,
                            json=msg,
                            timeout=10,
                            headers={
                                "X-Telegram-Bot-Api-Secret-Token":
                                    _config.get_config('security').get('telegram_webhook_secret') or ""
                            },
                        )
                        log.debug("【Telegram】message: %s processed, response is: %s" % (msg, local_res.text))
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【Telegram】消息接收出现错误: %s" % e)
            return _offset

        offset = 0
        while True:
            _config = Config()
            sc_url = "https://api.telegram.org/bot%s/getUpdates?" % self._telegram_token
            ds_url = TELEGRAM_LOCAL_CALLBACK_URL
            if not self._enabled:
                log.info("Telegram消息接收服务已停止")
                break

            i = 0
            while i < 20 and not event.is_set():
                offset = consume_messages(_config, offset, sc_url, ds_url)
                i = i + 1

    def stop_service(self):
        """
        停止服务
        """
        self._enabled = False
        if self._message_proxy_event:
            self._message_proxy_event.set()
            self._message_proxy_event = None
