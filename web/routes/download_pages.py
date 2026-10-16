"""下载任务、历史与自动删种页面。"""

from flask import Blueprint, request, render_template
from flask_login import login_required
from app.conf import ModuleConf
from app.torrentremover import TorrentRemover
from config import Config
from web.action import WebAction


download_pages_bp = Blueprint("download_pages", __name__)


@download_pages_bp.route('/downloading', methods=['POST', 'GET'])
@login_required
def downloading():
    DispTorrents = WebAction().get_downloading().get("result")
    return render_template("download/downloading.html",
                           DownloadCount=len(DispTorrents),
                           Torrents=DispTorrents,
                           Client=Config().get_config("pt").get("pt_client"))


@download_pages_bp.route('/downloaded', methods=['POST', 'GET'])
@login_required
def downloaded():
    CurrentPage = request.args.get("page") or 1
    return render_template("discovery/recommend.html",
                           Type='DOWNLOADED',
                           Title='近期下载',
                           CurrentPage=CurrentPage)


@download_pages_bp.route('/torrent_remove', methods=['POST', 'GET'])
@login_required
def torrent_remove():
    TorrentRemoveTasks = TorrentRemover().get_torrent_remove_tasks()
    return render_template("download/torrent_remove.html",
                           DownloaderConfig=ModuleConf.TORRENTREMOVER_DICT,
                           Count=len(TorrentRemoveTasks),
                           TorrentRemoveTasks=TorrentRemoveTasks)
