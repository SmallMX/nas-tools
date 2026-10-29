"""搜索与媒体探索页面。"""

from flask import Blueprint, request, json, render_template
from flask_login import login_required
from app.conf import ModuleConf
from app.indexer import Indexer
from web.action import WebAction


search_pages_bp = Blueprint("search_pages", __name__)


@search_pages_bp.route('/search', methods=['POST', 'GET'])
@login_required
def search():
    # 结果
    res = WebAction().get_search_result()
    SearchResults = res.get("result")
    Count = res.get("total")
    return render_template("search.html",
                           Count=Count,
                           Results=SearchResults,
                           SiteDict=Indexer().get_indexer_hash_dict(),
                           UPCHAR=chr(8593))


@search_pages_bp.route('/recommend', methods=['POST', 'GET'])
@login_required
def recommend():
    Type = request.args.get("type") or ""
    SubType = request.args.get("subtype") or ""
    Title = request.args.get("title") or ""
    SubTitle = request.args.get("subtitle") or ""
    try:
        CurrentPage = int(request.args.get("page") or 1)
    except (TypeError, ValueError):
        return "页码必须是整数", 400
    if CurrentPage < 1 or CurrentPage > 10000:
        return "页码超出允许范围", 400
    Week = request.args.get("week") or ""
    TmdbId = request.args.get("tmdbid") or ""
    PersonId = request.args.get("personid") or ""
    Keyword = request.args.get("keyword") or ""
    Source = request.args.get("source") or ""
    FilterKey = request.args.get("filter") or ""
    raw_params = request.args.get("params")
    try:
        Params = json.loads(raw_params) if raw_params else {}
    except (TypeError, ValueError):
        return "推荐过滤参数不是有效的 JSON", 400
    if not isinstance(Params, dict):
        return "推荐过滤参数必须是 JSON 对象", 400
    return render_template("discovery/recommend.html",
                           Type=Type,
                           SubType=SubType,
                           Title=Title,
                           CurrentPage=CurrentPage,
                           Week=Week,
                           TmdbId=TmdbId,
                           PersonId=PersonId,
                           SubTitle=SubTitle,
                           Keyword=Keyword,
                           Source=Source,
                           Filter=FilterKey,
                           FilterConf=ModuleConf.DISCOVER_FILTER_CONF.get(FilterKey) if FilterKey else {},
                           Params=Params)


@search_pages_bp.route('/ranking', methods=['POST', 'GET'])
@login_required
def ranking():
    return render_template("discovery/ranking.html",
                           DiscoveryType="RANKING")


@search_pages_bp.route('/tmdb_movie', methods=['POST', 'GET'])
@login_required
def tmdb_movie():
    return render_template("discovery/recommend.html",
                           Type="DISCOVER",
                           SubType="MOV",
                           Title="TMDB电影",
                           Filter="tmdb_movie",
                           FilterConf=ModuleConf.DISCOVER_FILTER_CONF.get('tmdb_movie'))


@search_pages_bp.route('/tmdb_tv', methods=['POST', 'GET'])
@login_required
def tmdb_tv():
    return render_template("discovery/recommend.html",
                           Type="DISCOVER",
                           SubType="TV",
                           Title="TMDB电视剧",
                           Filter="tmdb_tv",
                           FilterConf=ModuleConf.DISCOVER_FILTER_CONF.get('tmdb_tv'))


def _streaming_discovery(provider, title):
    """渲染视频平台的探索列表，并保留筛选条件。"""
    raw_params = request.args.get("params")
    try:
        params = json.loads(raw_params) if raw_params else {}
    except (TypeError, ValueError):
        return "推荐过滤参数不是有效的 JSON", 400
    if not isinstance(params, dict):
        return "推荐过滤参数必须是 JSON 对象", 400
    params = {"category": "tv", "sort": "hot", **params}
    filters = ModuleConf.DISCOVER_FILTER_CONF.get(provider)
    if provider == "tencent" and params.get("category") == "children" and filters and "sort" in filters:
        filters = {**filters, "sort": {**filters["sort"], "options": [
            option for option in filters["sort"]["options"] if option["value"] != "score"
        ]}}
    return render_template("discovery/recommend.html",
                           Type="STREAMING",
                           SubType=provider,
                           Title=title,
                           SubTitle="按分类与排序浏览作品，点击海报前往平台详情，或搜索资源。",
                           Filter=provider,
                           FilterConf=filters,
                           Params=params)


@search_pages_bp.route('/tencent', methods=['POST', 'GET'])
@login_required
def tencent():
    return _streaming_discovery("tencent", "腾讯视频")


@search_pages_bp.route('/iqiyi', methods=['POST', 'GET'])
@login_required
def iqiyi():
    return _streaming_discovery("iqiyi", "爱奇艺")


@search_pages_bp.route('/mgtv', methods=['POST', 'GET'])
@login_required
def mgtv():
    return _streaming_discovery("mgtv", "芒果视频")


@search_pages_bp.route('/bangumi', methods=['POST', 'GET'])
@login_required
def discovery_bangumi():
    return render_template("discovery/ranking.html",
                           DiscoveryType="BANGUMI")


@search_pages_bp.route('/media_detail', methods=['POST', 'GET'])
@login_required
def media_detail():
    TmdbId = request.args.get("id")
    Type = request.args.get("type")
    return render_template("discovery/mediainfo.html",
                           TmdbId=TmdbId,
                           Type=Type)


@search_pages_bp.route('/discovery_person', methods=['POST', 'GET'])
@login_required
def discovery_person():
    TmdbId = request.args.get("tmdbid")
    Title = request.args.get("title")
    SubTitle = request.args.get("subtitle")
    Type = request.args.get("type")
    return render_template("discovery/person.html",
                           TmdbId=TmdbId,
                           Title=Title,
                           SubTitle=SubTitle,
                           Type=Type)
