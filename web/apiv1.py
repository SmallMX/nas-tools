import json

from flask import Blueprint, g, request
from flask_restx import Api, inputs, reqparse, Resource

from app.brushtask import BrushTask
from app.sites import Sites
from app.utils import TokenCache
from config import Config
from web.action import WebAction
from web.backend.user import User
from web.security import (
    generate_access_token,
    extract_auth_token,
    login_required,
    require_auth,
    sanitize_brush_task,
    sanitize_downloader,
)


def parse_json_object(value):
    """将 JSON 对象或 JSON 字符串统一解析为 dict。"""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError("参数必须是有效的 JSON 对象") from error
    if not isinstance(parsed, dict):
        raise ValueError("参数必须是 JSON 对象")
    return parsed


def parse_json_list(value):
    """将 JSON 数组或 JSON 字符串统一解析为 list，避免字符串被拆成字符数组。"""
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ValueError("参数必须是有效的 JSON 数组") from error
    if not isinstance(parsed, list):
        raise ValueError("参数必须是 JSON 数组")
    return parsed

# ===== 2. Web API 接口定义中心 =====
# 初学者注意：这里是整个项目暴露给外部（如前端页面或你自己写的脚本）的接口。
# 前端通过发送 HTTP 的 GET 或 POST 请求到这些地址，后端就会执行相应的方法并返回 JSON 数据。

# 创建一个 Blueprint（蓝图），把所有的 API 路由打包在一起
apiv1_bp = Blueprint("apiv1", __name__)

# 使用 flask_restx 库来快速构建符合 RESTful 风格的 API，并能自动生成 Swagger 文档
Apiv1 = Api(apiv1_bp,
            version="1.0",
            title="NAStool Api",
            description="POST接口调用 /user/login 获取Token，GET接口使用 基础设置->安全->Api Key 调用",
            doc="/",  # 访问 /api/v1/ 就能看到所有接口的自动生成文档页面
            security='Bearer Auth',
            authorizations={"Bearer Auth": {"type": "apiKey", "name": "Authorization", "in": "header"}},
            )
# API分组
user = Apiv1.namespace('user', description='用户')
system = Apiv1.namespace('system', description='系统')
config = Apiv1.namespace('config', description='设置')
site = Apiv1.namespace('site', description='站点')
service = Apiv1.namespace('service', description='服务')
recommend = Apiv1.namespace('recommend', description='推荐')
search = Apiv1.namespace('search', description='搜索')
download = Apiv1.namespace('download', description='下载')
torrentremover = Apiv1.namespace('torrentremover', description='自动删种')
brushtask = Apiv1.namespace('brushtask', description='刷流')
media = Apiv1.namespace('media', description='媒体')
message = Apiv1.namespace('message', description='消息通知')


class ApiResource(Resource):
    """
    API 认证
    """
    method_decorators = [require_auth]


class ClientResource(Resource):
    """
    登录认证
    """
    method_decorators = [login_required]


def Failed():
    """
    返回失败报名
    """
    return {
        "code": -1,
        "success": False,
        "data": {}
    }


# 举例：这是一个具体的接口定义
# @user.route('/login') 意思是当访问 /api/v1/user/login 时，会交给下面这个 UserLogin 类来处理
@user.route('/login')
class UserLogin(Resource):
    # RequestParser 用来规定前端必须传哪些参数过来
    parser = reqparse.RequestParser()
    parser.add_argument('username', type=str, help='用户名', location='form', required=True)
    parser.add_argument('password', type=str, help='密码', location='form', required=True)

    @user.doc(parser=parser)
    def post(self):
        """
        用户登录接口的 POST 处理函数。
        初学者注意：通常前端点“登录”按钮，发的是 POST 请求，带上账密。
        """
        # 解析前端传过来的数据
        args = self.parser.parse_args()
        username = args.get('username')
        password = args.get('password')
        if not username or not password:
            # 如果没填，直接返回错误信息的 JSON
            return {"code": 401, "success": False, "message": "用户名或密码错误"}, 401
            
        # 去查数据库
        user_info = User().get_user(username)
        if not user_info:
            return {"code": 401, "success": False, "message": "用户名或密码错误"}, 401
            
        # 校验密码
        if not user_info.verify_password(password):
            return {"code": 401, "success": False, "message": "用户名或密码错误"}, 401
            
        # 密码正确！生成一串随机字符串（Token）作为门票发给前端
        # 以后前端每次请求其他需要登录的接口，都要在 Http Header 里带上这张门票
        token = generate_access_token(username)
        TokenCache.set(token, token) # 把门票存在服务器内存里记一下
        
        user_pris = str(user_info.pris).split(",")
        
        # 返回成功的数据包！
        return {
            "code": 0,
            "success": True,
            "data": {
                "token": token,
                "userinfo": {
                    "userid": user_info.id,
                    "username": user_info.username,
                    "userpris": user_pris
                }
            }
        }


@user.route('/info')
class UserInfo(ClientResource):
    def post(self):
        """
        获取当前令牌对应的用户信息
        """
        user_info = User().get_user(g.api_username)
        if not user_info:
            return {"code": 404, "success": False, "message": "用户不存在"}, 404
        return {
            "code": 0,
            "success": True,
            "data": {
                "userid": user_info.id,
                "username": user_info.username,
                "userpris": str(user_info.pris).split(",")
            }
        }


@user.route('/manage')
class UserManage(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('oper', type=str, help='操作类型（add 新增/del删除）', location='form', required=True)
    parser.add_argument('name', type=str, help='用户名', location='form', required=True)
    parser.add_argument('password', type=str, help='新增用户密码（至少 8 位）', location='form')
    parser.add_argument('pris', type=str, help='权限', location='form')

    @user.doc(parser=parser)
    def post(self):
        """
        用户管理
        """
        return WebAction().api_action(cmd='user_manager', data=self.parser.parse_args())


@user.route('/list')
class UserList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有用户
        """
        return WebAction().api_action(cmd='get_users')


@service.route('/mediainfo')
class ServiceMediaInfo(ApiResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='args', required=True)

    @service.doc(parser=parser)
    def get(self):
        """
        识别媒体信息（密钥认证）
        """
        return WebAction().api_action(cmd='name_test', data=self.parser.parse_args())


@service.route('/name/test')
class ServiceNameTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名称', location='form', required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        名称识别测试
        """
        return WebAction().api_action(cmd='name_test', data=self.parser.parse_args())


@service.route('/network/test')
class ServiceNetworkTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('url', type=str, help='URL地址', location='form', required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        网络连接性测试
        """
        return WebAction().api_action(cmd='net_test', data=self.parser.parse_args().get("url"))


@service.route('/run')
class ServiceRun(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('item', type=str,
                        help='服务名称（autoremovetorrents）',
                        location='form',
                        required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        运行服务
        """
        return WebAction().api_action(cmd='sch', data=self.parser.parse_args())


@site.route('/statistics')
class SiteStatistic(ApiResource):
    @staticmethod
    def get():
        """
        获取站点数据明细（密钥认证）
        """
        # 返回站点信息
        return {
            "code": 0,
            "success": True,
            "data": {
                "user_statistics": WebAction().get_site_user_statistics({"encoding": "DICT"}).get("data")
            }
        }


@site.route('/sites')
class SiteSites(ApiResource):
    @staticmethod
    def get():
        """
        获取所有站点配置（密钥认证）
        """
        sites = Sites().get_sites()
        desensitized_sites = []
        for site in sites:
            site_copy = dict(site)
            if site_copy.get("cookie"):
                site_copy["cookie"] = "******"
            if site_copy.get("apikey"):
                site_copy["apikey"] = "******"
            desensitized_sites.append(site_copy)
        return {
            "code": 0,
            "success": True,
            "data": {
                "user_sites": desensitized_sites
            }
        }


@site.route('/update')
class SiteUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('site_name', type=str, help='站点名称', location='form', required=True)
    parser.add_argument('site_id', type=int, help='更新站点ID', location='form')
    parser.add_argument('site_pri', type=str, help='优先级', location='form')
    parser.add_argument('site_rssurl', type=str, help='RSS地址', location='form')
    parser.add_argument('site_signurl', type=str, help='站点地址', location='form')
    parser.add_argument('site_cookie', type=str, help='Cookie', location='form')
    parser.add_argument('site_note', type=str, help='站点属性', location='form')
    parser.add_argument('site_include', type=str, help='站点用途', location='form')

    @site.doc(parser=parser)
    def post(self):
        """
        新增/删除站点
        """
        return WebAction().api_action(cmd='update_site', data=self.parser.parse_args())


@site.route('/info')
class SiteInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站点ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询单个站点详情
        """
        return WebAction().api_action(cmd='get_site', data=self.parser.parse_args())


@site.route('/favicon')
class SiteFavicon(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站点名称', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        获取站点图标(Base64)
        """
        return WebAction().api_action(cmd='get_site_favicon', data=self.parser.parse_args())


@site.route('/test')
class SiteTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站点ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        测试站点连通性
        """
        return WebAction().api_action(cmd='test_site', data=self.parser.parse_args())


@site.route('/delete')
class SiteDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站点ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        删除站点
        """
        return WebAction().api_action(cmd='del_site', data=self.parser.parse_args())


@site.route('/statistics/activity')
class SiteStatisticsActivity(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站点名称', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询站点 上传/下载/做种数据
        """
        return WebAction().api_action(cmd='get_site_activity', data=self.parser.parse_args())


@site.route('/check')
class SiteCheck(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('url', type=str, help='站点地址', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        检查站点是否支持FREE/HR检测
        """
        return WebAction().api_action(cmd='check_site_attr', data=self.parser.parse_args())


@site.route('/statistics/history')
class SiteStatisticsHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('days', type=int, help='时间范围（天）', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询所有站点历史数据
        """
        return WebAction().api_action(cmd='get_site_history', data=self.parser.parse_args())


@site.route('/statistics/seedinfo')
class SiteStatisticsSeedinfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站点名称', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查询站点做种分布
        """
        return WebAction().api_action(cmd='get_site_seeding_info', data=self.parser.parse_args())


@site.route('/resources')
class SiteResources(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='站点索引ID', location='form', required=True)
    parser.add_argument('page', type=int, help='页码', location='form')
    parser.add_argument('keyword', type=str, help='站点名称', location='form')

    @site.doc(parser=parser)
    def post(self):
        """
        查询站点资源列表
        """
        return WebAction().api_action(cmd='list_site_resources', data=self.parser.parse_args())


@site.route('/list')
class SiteList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('basic', type=int, help='只查询基本信息（0-否/1-是）', location='form')
    parser.add_argument('rss', type=int, help='资源浏览（0-否/1-是）', location='form')
    parser.add_argument('brush', type=int, help='刷流（0-否/1-是）', location='form')
    parser.add_argument('signin', type=int, help='签到（0-否/1-是）', location='form')
    parser.add_argument('statistic', type=int, help='数据统计（0-否/1-是）', location='form')

    def post(self):
        """
        查询站点列表
        """
        return WebAction().api_action(cmd='get_sites', data=self.parser.parse_args())


@site.route('/indexers')
class SiteIndexers(ClientResource):

    @staticmethod
    def post():
        """
        查询站点索引列表
        """
        return WebAction().api_action(cmd='get_indexers')


@search.route('/keyword')
class SearchKeyword(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('search_word', type=str, help='搜索关键字', location='form', required=True)
    parser.add_argument('unident', type=int, help='快速模式（0-否/1-是）', location='form')
    parser.add_argument('filters', type=str, help='过滤条件', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('media_type', type=str, help='类型（电影/电视剧）', location='form')

    @search.doc(parser=parser)
    def post(self):
        """
        根据关键字/TMDBID搜索
        """
        return WebAction().api_action(cmd='search', data=self.parser.parse_args())


@search.route('/result')
class SearchResult(ClientResource):
    @staticmethod
    def post():
        """
        查询搜索结果
        """
        return WebAction().api_action(cmd='get_search_result')


@download.route('/search')
class DownloadSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='搜索结果ID', location='form', required=True)
    parser.add_argument('dir', type=str, help='保存目录', location='form')
    parser.add_argument('setting', type=str, help='下载设置', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        下载搜索结果
        """
        return WebAction().api_action(cmd='download', data=self.parser.parse_args())


@download.route('/item')
class DownloadItem(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('enclosure', type=str, help='链接URL', location='form', required=True)
    parser.add_argument('title', type=str, help='标题', location='form', required=True)
    parser.add_argument('site', type=str, help='站点名称', location='form')
    parser.add_argument('description', type=str, help='描述', location='form')
    parser.add_argument('page_url', type=str, help='详情页面URL', location='form')
    parser.add_argument('size', type=str, help='大小', location='form')
    parser.add_argument('seeders', type=str, help='做种数', location='form')
    parser.add_argument('uploadvolumefactor', type=float, help='上传因子', location='form')
    parser.add_argument('downloadvolumefactor', type=float, help='下载因子', location='form')
    parser.add_argument('dl_dir', type=str, help='保存目录', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        下载链接
        """
        return WebAction().api_action(cmd='download_link', data=self.parser.parse_args())


@download.route('/start')
class DownloadStart(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任务ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        开始下载任务
        """
        return WebAction().api_action(cmd='pt_start', data=self.parser.parse_args())


@download.route('/stop')
class DownloadStop(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任务ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        暂停下载任务
        """
        return WebAction().api_action(cmd='pt_stop', data=self.parser.parse_args())


@download.route('/info')
class DownloadInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ids', type=str, help='任务IDS', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载进度
        """
        return WebAction().api_action(cmd='pt_info', data=self.parser.parse_args())


@download.route('/remove')
class DownloadRemove(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任务ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        删除下载任务
        """
        return WebAction().api_action(cmd='pt_remove', data=self.parser.parse_args())


@download.route('/history')
class DownloadHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=str, help='第几页', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载历史
        """
        return WebAction().api_action(cmd='get_downloaded', data=self.parser.parse_args())


@download.route('/now')
class DownloadNow(ClientResource):
    @staticmethod
    def post():
        """
        查询正在下载的任务
        """
        return WebAction().api_action(cmd='get_downloading')


@download.route('/config/info')
class DownloadConfigInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查询下载设置
        """
        return WebAction().api_action(cmd='get_download_setting', data=self.parser.parse_args())


@download.route('/config/update')
class DownloadConfigUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form', required=True)
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('category', type=str, help='分类', location='form')
    parser.add_argument('tags', type=str, help='标签', location='form')
    parser.add_argument('content_layout', type=int, help='布局（0-全局/1-原始/2-创建子文件夹/3-不建子文件夹）',
                        location='form')
    parser.add_argument('is_paused', type=int, help='动作（0-添加后开始/1-添加后暂停）', location='form')
    parser.add_argument('upload_limit', type=int, help='上传速度限制', location='form')
    parser.add_argument('download_limit', type=int, help='下载速度限制', location='form')
    parser.add_argument('ratio_limit', type=int, help='分享率限制', location='form')
    parser.add_argument('seeding_time_limit', type=int, help='做种时间限制', location='form')
    parser.add_argument('downloader', type=str, help='下载器（Qbittorrent/Transmission）', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        新增/修改下载设置
        """
        return WebAction().api_action(cmd='update_download_setting', data=self.parser.parse_args())


@download.route('/config/delete')
class DownloadConfigDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        删除下载设置
        """
        return WebAction().api_action(cmd='delete_download_setting', data=self.parser.parse_args())


@download.route('/config/list')
class DownloadConfigList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='ID', location='form')

    def post(self):
        """
        查询下载设置
        """
        return WebAction().api_action(cmd="get_download_setting", data=self.parser.parse_args())


@download.route('/config/directory')
class DownloadConfigDirectory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下载设置ID', location='form')

    def post(self):
        """
        查询下载保存目录
        """
        return WebAction().api_action(cmd="get_download_dirs", data=self.parser.parse_args())



@system.route('/logging')
class SystemLogging(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('refresh_new', type=int, help='是否刷新增量日志（0-否/1-是）', location='form', required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        获取实时日志
        """
        return WebAction().api_action(cmd='logging', data=self.parser.parse_args())



@system.route('/restart')
class SystemRestart(ClientResource):

    @staticmethod
    def post():
        """
        重启
        """
        return WebAction().api_action(cmd='restart')


@system.route('/logout')
class SystemLogout(ClientResource):

    @staticmethod
    def post():
        """
        注销
        """
        token = extract_auth_token(request.headers.get("Authorization", default=None))
        if token:
            TokenCache.delete(token)
        return {
            "code": 0,
            "success": True
        }


@system.route('/message')
class SystemMessage(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('lst_time', type=str, help='时间（YYYY-MM-DD HH24:MI:SS）', location='form')

    @system.doc(parser=parser)
    def post(self):
        """
        查询消息中心消息
        """
        return WebAction().get_system_message(lst_time=self.parser.parse_args().get("lst_time"))


@system.route('/progress')
class SystemProgress(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='进度类型', location='form', required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        查询任务进度
        """
        return WebAction().api_action(cmd='refresh_process', data=self.parser.parse_args())


@config.route('/update')
class ConfigUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('items', type=parse_json_object, help='配置项（JSON 对象）',
                        location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        新增/修改配置
        """
        return WebAction().api_action(cmd='update_config', data=self.parser.parse_args().get("items"))


@config.route('/test')
class ConfigTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('command', type=str, help='测试命令', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        测试配置连通性
        """
        return WebAction().api_action(cmd='test_connection', data=self.parser.parse_args())


@config.route('/info')
class ConfigInfo(ClientResource):
    @staticmethod
    def post():
        """
        获取所有配置信息
        """
        from web.security import desensitize_config_dict
        return {
            "code": 0,
            "success": True,
            "data": desensitize_config_dict(Config().get_config())
        }



@recommend.route('/list')
class RecommendList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str,
                        help='内容类型（MOV/TV/SEARCH/DOWNLOADED/TRENDING/DISCOVER/DOUBANTAG）',
                        location='form', required=True)
    parser.add_argument('subtype', type=str,
                        help='子类型（hm/ht/nm/nt/dbom/dbhm/dbht/dbdh/dbnm/dbtop/dbzy/bangumi 等）',
                        location='form')
    parser.add_argument('page', type=int, help='页码', location='form', default=1)
    parser.add_argument('week', type=str, help='星期', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDB ID', location='form')
    parser.add_argument('personid', type=str, help='人物 ID', location='form')
    parser.add_argument('keyword', type=str, help='搜索关键字', location='form')
    parser.add_argument('source', type=str, help='搜索来源', location='form')
    parser.add_argument('params', type=parse_json_object, help='筛选参数（JSON 对象）', location='form')

    @recommend.doc(parser=parser)
    def post(self):
        """
        推荐列表
        """
        return WebAction().api_action(cmd='get_recommend', data=self.parser.parse_args())













@media.route('/search')
class MediaSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('keyword', type=str, help='关键字', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        搜索TMDB/豆瓣词条
        """
        return WebAction().api_action(cmd='search_media_infos', data=self.parser.parse_args())


@media.route('/cache/update')
class MediaCacheUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('key', type=str, help='缓存Key值', location='form', required=True)
    parser.add_argument('title', type=str, help='标题', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        修改TMDB缓存标题
        """
        return WebAction().api_action(cmd='modify_tmdb_cache', data=self.parser.parse_args())


@media.route('/cache/delete')
class MediaCacheDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cache_key', type=str, help='缓存Key值', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        删除TMDB缓存
        """
        return WebAction().api_action(cmd='delete_tmdb_cache', data=self.parser.parse_args())


@media.route('/cache/clear')
class MediaCacheClear(ClientResource):

    @staticmethod
    def post():
        """
        清空TMDB缓存
        """
        return WebAction().api_action(cmd='clear_tmdb_cache')


@media.route('/tv/seasons')
class MediaTvSeasons(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        查询电视剧季列表
        """
        return WebAction().api_action(cmd='get_tvseason_list', data=self.parser.parse_args())


@media.route('/category/list')
class MediaCategoryList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（电影/电视剧/动漫）', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        查询二级分类配置
        """
        return WebAction().api_action(cmd='get_categories', data=self.parser.parse_args())


@media.route('/info')
class MediaInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('id', type=str, help='TMDBID', location='form')
    parser.add_argument('title', type=str, help='标题', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        识别媒体信息
        """
        return WebAction().api_action(cmd='media_info', data=self.parser.parse_args())


@media.route('/detail')
class MediaDetail(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('tmdbid', type=str, help='TMDBID/DB:豆瓣ID', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        查询TMDB媒体详情
        """
        return WebAction().api_action(cmd='media_detail', data=self.parser.parse_args())


@media.route('/similar')
class MediaSimilar(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('page', type=int, help='页码', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        根据TMDBID查询类似媒体
        """
        return WebAction().api_action(cmd='media_similar', data=self.parser.parse_args())


@media.route('/recommendations')
class MediaRecommendations(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('page', type=int, help='页码', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        根据TMDBID查询推荐媒体
        """
        return WebAction().api_action(cmd='media_recommendations', data=self.parser.parse_args())


@media.route('/person')
class MediaPersonList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='类型（MOV/TV）', location='form', required=True)
    parser.add_argument('personid', type=str, help='演员ID', location='form')
    parser.add_argument('page', type=int, help='页码', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        查询TMDB演员参演作品
        """
        return WebAction().api_action(cmd='person_medias', data=self.parser.parse_args())


@brushtask.route('/update')
class BrushTaskUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('brushtask_id', type=str, help='刷流任务ID', location='form')
    parser.add_argument('brushtask_name', type=str, help='任务名称', location='form', required=True)
    parser.add_argument('brushtask_site', type=int, help='站点', location='form', required=True)
    parser.add_argument('brushtask_interval', type=int, help='刷新间隔(分钟)', location='form', required=True)
    parser.add_argument('brushtask_downloader', type=int, help='下载器', location='form', required=True)
    parser.add_argument('brushtask_totalsize', type=int, help='保种体积(GB)', location='form', required=True)
    parser.add_argument('brushtask_state', type=str, help='状态（Y/N）', location='form', required=True)
    parser.add_argument('brushtask_sendmessage', type=str, help='消息推送（Y/N）', location='form')
    parser.add_argument('brushtask_forceupload', type=str, help='强制做种（Y/N）', location='form')
    parser.add_argument('brushtask_free', type=str, help='促销（FREE/2XFREE）', location='form')
    parser.add_argument('brushtask_hr', type=str, help='Hit&Run（HR）', location='form')
    parser.add_argument('brushtask_torrent_size', type=int, help='种子大小(GB)', location='form')
    parser.add_argument('brushtask_include', type=str, help='包含', location='form')
    parser.add_argument('brushtask_exclude', type=str, help='排除', location='form')
    parser.add_argument('brushtask_dlcount', type=int, help='同时下载任务数', location='form')
    parser.add_argument('brushtask_peercount', type=str,
                        help='做种人数限制（格式：gt#10、lt#10 或 bw#10,20）', location='form')
    parser.add_argument('brushtask_seedtime', type=float, help='做种时间(小时)', location='form')
    parser.add_argument('brushtask_seedratio', type=float, help='分享率', location='form')
    parser.add_argument('brushtask_seedsize', type=int, help='上传量(GB)', location='form')
    parser.add_argument('brushtask_dltime', type=float, help='下载耗时(小时)', location='form')
    parser.add_argument('brushtask_avg_upspeed', type=int, help='平均上传速度(KB/S)', location='form')
    parser.add_argument('brushtask_iatime', type=float, help='未活动时间(小时)', location='form')
    parser.add_argument('brushtask_pubdate', type=int, help='发布时间（小时）', location='form')
    parser.add_argument('brushtask_upspeed', type=int, help='上传限速（KB/S）', location='form')
    parser.add_argument('brushtask_downspeed', type=int, help='下载限速（KB/S）', location='form')

    @brushtask.doc(parser=parser)
    def post(self):
        """
        新增/修改刷流任务
        """
        return WebAction().api_action(cmd='add_brushtask', data=self.parser.parse_args())


@brushtask.route('/delete')
class BrushTaskDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        删除刷流任务
        """
        return WebAction().api_action(cmd='del_brushtask', data=self.parser.parse_args())


@brushtask.route('/info')
class BrushTaskInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流任务详情
        """
        return WebAction().api_action(cmd='brushtask_detail', data=self.parser.parse_args())


@brushtask.route('/list')
class BrushTaskList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有刷流任务
        """
        return {
            "code": 0,
            "success": True,
            "data": {
                "tasks": [
                    sanitize_brush_task(task)
                    for task in BrushTask().get_brushtask_info()
                ]
            }
        }


@brushtask.route('/torrents')
class BrushTaskTorrents(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        查询刷流任务种子明细
        """
        return WebAction().api_action(cmd='list_brushtask_torrents', data=self.parser.parse_args())


@brushtask.route('/downloader/update')
class BrushTaskDownloaderUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('test', type=int, help='测试（0-否/1-是）', location='form', required=True)
    parser.add_argument('id', type=int, help='下载器ID', location='form')
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('type', type=str, help='类型（qbittorrent/transmission）', location='form', required=True)
    parser.add_argument('host', type=str, help='地址', location='form', required=True)
    parser.add_argument('port', type=int, help='端口', location='form', required=True)
    parser.add_argument('username', type=str, help='用户名', location='form')
    parser.add_argument('password', type=str, help='密码', location='form')
    parser.add_argument('save_dir', type=str, help='保存目录', location='form')

    @brushtask.doc(parser=parser)
    def post(self):
        """
        新增/修改刷流下载器
        """
        return WebAction().api_action(cmd='add_downloader', data=self.parser.parse_args())


@brushtask.route('/downloader/delete')
class BrushTaskDownloaderDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='下载器ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        删除刷流下载器
        """
        return WebAction().api_action(cmd='delete_downloader', data=self.parser.parse_args())


@brushtask.route('/downloader/info')
class BrushTaskDownloaderInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='下载器ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流下载器详情
        """
        return WebAction().api_action(cmd='get_downloader', data=self.parser.parse_args())


@brushtask.route('/downloader/list')
class BrushTaskDownloaderList(ClientResource):
    @staticmethod
    def post():
        """
        查询所有刷流下载器
        """
        return {
            "code": 0,
            "success": True,
            "data": {
                "downloaders": [
                    sanitize_downloader(downloader)
                    for downloader in BrushTask().get_downloader_info()
                ]
            }
        }


@brushtask.route('/run')
class BrushTaskRun(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='刷流任务ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流下载器详情
        """
        return WebAction().api_action(cmd='run_brushtask', data=self.parser.parse_args())



@message.route('/client/update')
class MessageClientUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form')
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('type', type=str, help='类型（telegram）',
                        location='form', required=True)
    parser.add_argument('config', type=str, help='配置项（JSON）', location='form', required=True)
    parser.add_argument('switchs', type=parse_json_list, help='开关（JSON 数组）',
                        location='form', required=True)
    parser.add_argument('interactive', type=int, help='是否开启交互（0/1）', location='form', required=True)
    parser.add_argument('enabled', type=int, help='是否启用（0/1）', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        新增/修改通知消息服务渠道
        """
        return WebAction().api_action(cmd='update_message_client', data=self.parser.parse_args())


@message.route('/client/delete')
class MessageClientDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        删除通知消息服务渠道
        """
        return WebAction().api_action(cmd='delete_message_client', data=self.parser.parse_args())


@message.route('/client/status')
class MessageClientStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='操作类型（interactive/enable）', location='form', required=True)
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)
    parser.add_argument('type', type=str, help='消息渠道类型（telegram）', location='form', required=True)
    parser.add_argument('checked', type=inputs.boolean, help='是否开启', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        设置通知消息服务渠道状态
        """
        return WebAction().api_action(cmd='check_message_client', data=self.parser.parse_args())


@message.route('/client/info')
class MessageClientInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        查询通知消息服务渠道设置
        """
        return WebAction().api_action(cmd='get_message_client', data=self.parser.parse_args())


@message.route('/client/test')
class MessageClientTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form')
    parser.add_argument('type', type=str, help='类型（telegram）',
                        location='form', required=True)
    parser.add_argument('config', type=str, help='配置（JSON）', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        测试通知消息服务配置正确性
        """
        return WebAction().api_action(cmd='test_message_client', data=self.parser.parse_args())


@torrentremover.route('/task/info')
class TorrentRemoverTaskInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任务ID', location='form', required=True)

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        查询自动删种任务详情
        """
        return WebAction().api_action(cmd='get_torrent_remove_task', data=self.parser.parse_args())


@torrentremover.route('/task/list')
class TorrentRemoverTaskList(ClientResource):
    @staticmethod
    @torrentremover.doc()
    def post():
        """
        查询所有自动删种任务
        """
        return WebAction().api_action(cmd='get_torrent_remove_task')


@torrentremover.route('/task/delete')
class TorrentRemoverTaskDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任务ID', location='form', required=True)

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        删除自动删种任务
        """
        return WebAction().api_action(cmd='delete_torrent_remove_task', data=self.parser.parse_args())


@torrentremover.route('/task/update')
class TorrentRemoverTaskUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任务ID', location='form')
    parser.add_argument('name', type=str, help='名称', location='form', required=True)
    parser.add_argument('action', type=int, help='动作(1-暂停/2-删除种子/3-删除种子及文件)', location='form',
                        required=True)
    parser.add_argument('interval', type=int, help='运行间隔（分钟）', location='form', required=True)
    parser.add_argument('enabled', type=int, help='状态（0-停用/1-启用）', location='form', required=True)
    parser.add_argument('samedata', type=int, help='处理辅种（0-否/1-是）', location='form', required=True)
    parser.add_argument('onlynastool', type=int, help='只管理NASTool添加的下载（0-否/1-是）', location='form',
                        required=True)
    parser.add_argument('ratio', type=float, help='分享率', location='form')
    parser.add_argument('seeding_time', type=int, help='做种时间（小时）', location='form')
    parser.add_argument('upload_avs', type=int, help='平均上传速度（KB/S）', location='form')
    parser.add_argument('size', type=str, help='种子大小（GB）', location='form')
    parser.add_argument('savepath_key', type=str, help='保存路径关键词', location='form')
    parser.add_argument('tracker_key', type=str, help='tracker关键词', location='form')
    parser.add_argument('downloader', type=str, help='下载器（Qb/Tr）', location='form')
    parser.add_argument('qb_state', type=str, help='Qb种子状态（多个用;分隔）', location='form')
    parser.add_argument('qb_category', type=str, help='Qb分类（多个用;分隔）', location='form')
    parser.add_argument('tr_state', type=str, help='Tr种子状态（多个用;分隔）', location='form')
    parser.add_argument('tr_error_key', type=str, help='Tr错误信息关键词', location='form')

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        新增/修改自动删种任务
        """
        return WebAction().api_action(cmd='update_torrent_remove_task', data=self.parser.parse_args())
