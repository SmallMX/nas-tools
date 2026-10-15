import copy
import datetime
import html as html_lib
import json
import os.path
import re
import signal
from threading import Timer
from flask import has_request_context, request
from flask_login import logout_user
from werkzeug.security import generate_password_hash
import log
from app.conf import SystemConfig, ModuleConf
from app.helper import ProgressHelper, DisplayHelper
from app.message import Message, MessageCenter
from app.retired_features import ACTIVE_USER_PERMISSIONS, sanitize_config_write
from app.scheduler import stop_scheduler
from app.utils import RequestUtils, ExceptionUtils
from config import Config
from web.security import request_has_system_settings, sanitize_message_client
from web.actions.validation import prepare_message_client_config, validate_site_config_url


def get_restart_target_pid(server_software=None):
    if server_software is None and has_request_context():
        server_software = request.environ.get("SERVER_SOFTWARE")
    server_software = str(server_software or os.environ.get("SERVER_SOFTWARE", "")).lower()
    if server_software.startswith("gunicorn"):
        parent_pid = os.getppid()
        if parent_pid > 1:
            return parent_pid
    return os.getpid()


def _message_client_config(data):
    """保存与连接测试复用相同的凭据保留和字段校验规则。"""
    cid = data.get("cid")
    existing = Message().get_message_client_info(cid=cid) if cid else None
    try:
        config = prepare_message_client_config(
            data.get("type"), data.get("config"), (existing or {}).get("config"))
    except ValueError as error:
        return None, {"code": 1, "msg": str(error)}
    return config, None


class SystemActions:
    """系统配置、用户、通知与运行状态动作。"""

    def __init__(self, dbhelper):
        self.dbhelper = dbhelper

    @staticmethod
    def restart_server():
        """
        返回响应后发送 SIGTERM，由外部进程管理器按部署策略拉起服务。
        """
        logout_user()

        target_pid = get_restart_target_pid()

        def shutdown():
            stop_scheduler()
            DisplayHelper().quit()
            os.kill(target_pid, signal.SIGTERM)

        timer = Timer(0.75, shutdown)
        timer.daemon = True
        timer.start()

    @staticmethod
    def set_config_value(cfg, cfg_key, cfg_value):
        """
        根据Key设置配置值
        """
        if cfg_value == "******":
            return cfg
        cfg_value = sanitize_config_write(cfg_key, cfg_value)
        optional_service_labels = {
            "app.ocr_server": "OCR服务地址",
            "laboratory.tmdb_proxy": "TMDB代理服务地址",
        }
        if cfg_key in optional_service_labels:
            cfg_value = validate_site_config_url(
                cfg_value, optional_service_labels[cfg_key]
            ).rstrip('/')
        # 密码
        if cfg_key == "app.login_password":
            if not cfg_value:
                return cfg
            if not cfg_value.startswith("[hash]"):
                cfg['app']['login_password'] = "[hash]%s" % generate_password_hash(
                    cfg_value)
            else:
                cfg['app']['login_password'] = cfg_value
            return cfg
        # 代理
        if cfg_key == "app.proxies":
            if cfg_value:
                if not cfg_value.startswith("http") and not cfg_value.startswith("sock"):
                    cfg['app']['proxies'] = {
                        "https": "http://%s" % cfg_value, "http": "http://%s" % cfg_value}
                else:
                    cfg['app']['proxies'] = {"https": "%s" %
                                             cfg_value, "http": "%s" % cfg_value}
            else:
                cfg['app']['proxies'] = {"https": None, "http": None}
            return cfg
        # 最大支持三层赋值
        keys = cfg_key.split(".")
        if keys:
            if len(keys) == 1:
                cfg[keys[0]] = cfg_value
            elif len(keys) == 2:
                if not cfg.get(keys[0]):
                    cfg[keys[0]] = {}
                cfg[keys[0]][keys[1]] = cfg_value
            elif len(keys) == 3:
                if cfg.get(keys[0]):
                    if not cfg[keys[0]].get(keys[1]) or isinstance(cfg[keys[0]][keys[1]], str):
                        cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value
                else:
                    cfg[keys[0]] = {}
                    cfg[keys[0]][keys[1]] = {}
                    cfg[keys[0]][keys[1]][keys[2]] = cfg_value

        return cfg

    @staticmethod
    def logging(data):
        """
        查询实时日志
        """
        log_list = []
        refresh_new = data.get('refresh_new')
        source = data.get('source')

        if not source:
            if not refresh_new:
                log_list = list(log.LOG_QUEUE)
            elif log.LOG_INDEX:
                if log.LOG_INDEX > len(list(log.LOG_QUEUE)):
                    log_list = list(log.LOG_QUEUE)
                else:
                    log_list = list(log.LOG_QUEUE)[-log.LOG_INDEX:]
            log.LOG_INDEX = 0
        else:
            queue_logs = list(log.LOG_QUEUE)
            for message in queue_logs:
                if str(message.get("source")) == source:
                    log_list.append(message)
                else:
                    continue

            if refresh_new:
                if int(refresh_new) < len(log_list):
                    log_list = log_list[int(refresh_new):]
                elif int(refresh_new) >= len(log_list):
                    log_list = []
        return {"loglist": log_list}

    def restart(self, data):
        """
        重启
        """
        # 退出主进程
        self.restart_server()
        return {"code": 0}

    @staticmethod
    def logout(data):
        """
        注销
        """
        logout_user()
        return {"code": 0}

    def update_config(self, data):
        """
        更新配置信息
        """
        cfg = copy.deepcopy(Config().get_config())
        cfgs = dict(data).items()
        # 仅测试不保存
        config_test = False
        # 修改配置
        try:
            for key, value in cfgs:
                if key == "test" and value:
                    config_test = True
                    continue
                # 生效配置
                cfg = self.set_config_value(cfg, key, value)
        except ValueError as error:
            return {"code": 1, "msg": str(error)}

        # 保存配置
        if not config_test:
            from app.config_reload import save_config_and_apply
            if not save_config_and_apply(cfg):
                return {"code": 1, "msg": "配置保存或应用失败，请检查系统日志"}

        return {"code": 0}

    def user_manager(self, data):
        """
        用户管理
        """
        if not isinstance(data, dict):
            return {"code": 1, "success": False, "message": "请求参数错误"}
        oper = str(data.get("oper") or "").strip().lower()
        name = str(data.get("name") or "").strip()
        if oper not in {"add", "del"}:
            return {"code": 1, "success": False, "message": "不支持的用户操作"}
        if not name or len(name) > 64:
            return {"code": 1, "success": False, "message": "用户名不能为空且不能超过 64 个字符"}

        if oper == "add":
            raw_password = data.get("password")
            if not isinstance(raw_password, str) or not 8 <= len(raw_password) <= 128:
                return {"code": 1, "success": False, "message": "密码长度必须为 8 至 128 个字符"}
            if name == (Config().get_config("app") or {}).get("login_user") \
                    or self.dbhelper.is_user_exists(name):
                return {"code": 1, "success": False, "message": "用户已存在"}
            pris = data.get("pris")
            if isinstance(pris, str):
                pris = [permission.strip() for permission in pris.split(",")]
            if not isinstance(pris, list) or not pris \
                    or any(permission not in ACTIVE_USER_PERMISSIONS for permission in pris):
                return {"code": 1, "success": False, "message": "包含已下线或未知权限"}
            normalized_permissions = list(dict.fromkeys(pris))
            password_hash = generate_password_hash(raw_password)
            ret = self.dbhelper.insert_user(name, password_hash, ",".join(normalized_permissions))
        else:
            if name == (Config().get_config("app") or {}).get("login_user"):
                return {"code": 1, "success": False, "message": "不能删除管理员用户"}
            ret = self.dbhelper.delete_user(name)

        if ret:
            return {"code": 0, "success": True}
        return {"code": 1, "success": False, "message": "用户不存在或操作失败"}

    @staticmethod
    def get_system_message(lst_time):
        messages = MessageCenter().get_system_messages(lst_time=lst_time)
        if messages:
            lst_time = messages[0].get("time")
        return {
            "code": 0,
            "message": messages,
            "lst_time": lst_time
        }

    def refresh_message(self, data):
        """
        刷新首页消息中心
        """
        lst_time = data.get("lst_time")
        system_msg = self.get_system_message(lst_time=lst_time)
        messages = system_msg.get("message")
        lst_time = system_msg.get("lst_time")
        message_items = []
        for message in list(reversed(messages)):
            def plain_text(value):
                text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.IGNORECASE)
                return html_lib.unescape(re.sub(r"<[^>]+>", "", text))

            message_items.append({
                "level": str(message.get("level") or "INFO"),
                "title": plain_text(message.get("title")),
                "content": plain_text(message.get("content")),
                "time": str(message.get("time") or ""),
            })
        return {"code": 0, "message": message_items, "lst_time": lst_time}

    @staticmethod
    def net_test(data):
        target = str(data or "").strip().lower().rstrip(".")
        if target not in {item.lower().rstrip(".") for item in ModuleConf.NETTEST_TARGETS}:
            return {"res": False, "time": "0 毫秒", "msg": "不支持的网络测试目标"}
        if target == "image.tmdb.org":
            target = target + "/t/p/w500/wwemzKWzjKYJFfCeiB57q3r4Bcm.png"
        target = "https://" + target
        start_time = datetime.datetime.now()
        if target.find("themoviedb") != -1 \
                or target.find("telegram") != -1 \
                or target.find("fanart") != -1 \
                or target.find("tmdb") != -1:
            res = RequestUtils(proxies=Config().get_proxies(),
                               timeout=5).get_res(target, allow_redirects=False)
        else:
            res = RequestUtils(timeout=5).get_res(target, allow_redirects=False)
        elapsed_ms = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
        if not res:
            return {"res": False, "time": "%s 毫秒" % elapsed_ms}
        elif res.ok:
            return {"res": True, "time": "%s 毫秒" % elapsed_ms}
        else:
            return {"res": False, "time": "%s 毫秒" % elapsed_ms}

    @staticmethod
    def refresh_process(data):
        """
        刷新进度条
        """
        process_type = data.get("type")
        if process_type == "sitecookie" and has_request_context() \
                and not request_has_system_settings():
            return {"code": 403, "value": 0, "text": "权限不足"}
        detail = ProgressHelper().get_process(process_type)
        if detail:
            return {"code": 0, "value": detail.get("value"), "text": detail.get("text")}
        else:
            return {"code": 1, "value": 0, "text": "正在处理..."}

    def get_users(self, data=None):
        """
        查询所有用户
        """
        user_list = self.dbhelper.get_users()
        Users = []
        for user in user_list:
            pris = str(user.pris).split(",")
            Users.append({"id": user.id, "name": user.name, "pris": pris})
        return {"code": 0, "result": Users}

    def update_message_client(self, data):
        """
        更新消息设置
        """
        name = data.get("name")
        cid = data.get("cid")
        ctype = data.get("type")
        switchs = data.get("switchs")
        switchs = switchs if isinstance(switchs, list) else []
        supported_switches = set(ModuleConf.MESSAGE_CONF.get("switch", {}))
        if any(
            not isinstance(switch, str) or switch not in supported_switches
            for switch in switchs
        ):
            return {"code": 1, "msg": "消息渠道包含已下线或未知的通知类型"}
        interactive = data.get("interactive")
        enabled = data.get("enabled")
        config_dict, error = _message_client_config(data)
        if error:
            return error
        saved = self.dbhelper.insert_message_client(
            name=name,
            ctype=ctype,
            config=json.dumps(config_dict, ensure_ascii=False),
            switchs=switchs,
            interactive=interactive,
            enabled=enabled,
            cid=cid,
        )
        if not saved:
            return {"code": 1, "msg": "消息渠道保存失败"}
        Message().init_config()
        return {"code": 0}

    def delete_message_client(self, data):
        """
        删除消息设置
        """
        if self.dbhelper.delete_message_client(cid=data.get("cid")):
            Message().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    def check_message_client(self, data):
        """
        维护消息设置
        """
        flag = data.get("flag")
        cid = data.get("cid")
        ctype = data.get("type")
        checked = data.get("checked")
        if flag == "interactive":
            # TG/WX只能开启一个交互
            if checked:
                self.dbhelper.check_message_client(interactive=0, ctype=ctype)
            self.dbhelper.check_message_client(cid=cid,
                                               interactive=1 if checked else 0)
            Message().init_config()
            return {"code": 0}
        elif flag == "enable":
            self.dbhelper.check_message_client(cid=cid,
                                               enabled=1 if checked else 0)
            Message().init_config()
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def get_message_client(data):
        """
        获取消息设置
        """
        cid = data.get("cid")
        detail = Message().get_message_client_info(cid=cid)
        if not detail:
            return {"code": 1, "msg": "消息渠道不存在", "detail": {}}
        return {"code": 0, "detail": sanitize_message_client(detail)}

    @staticmethod
    def test_message_client(data):
        """
        测试消息设置
        """
        ctype = data.get("type")
        config, error = _message_client_config(data)
        if error:
            return error
        res = Message().get_status(ctype=ctype, config=config)
        if res:
            return {"code": 0}
        else:
            return {"code": 1}

    @staticmethod
    def set_system_config(data):
        """
        设置系统设置（数据库）
        """
        key = data.get("key")
        value = data.get("value")
        if not key or not value:
            return {"code": 1}
        try:
            if SystemConfig().set_system_config(key=key, value=value):
                return {"code": 0}
            return {"code": 1}
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {"code": 1}

    @staticmethod
    def send_custom_message(data):
        """
        发送自定义消息
        """
        title = data.get("title")
        text = data.get("text") or ""
        image = data.get("image") or ""
        Message().send_custom_message(title=title, text=text, image=image)
        return {"code": 0}

    @staticmethod
    def save_user_script(data):
        """
        保存用户自定义脚本
        """
        script = data.get("javascript") or ""
        css = data.get("css") or ""
        SystemConfig().set_system_config(key="CustomScript",
                                         value={
                                             "css": css,
                                             "javascript": script
                                         })
        return {"code": 0, "msg": "保存成功"}
