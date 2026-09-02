import html
import os
import shutil
import sqlite3
import tempfile
import urllib.parse
from pathlib import Path

from flask import Blueprint, make_response, request, send_file
from flask_login import current_user, login_required
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from app.db.main_db import RETIRED_DATABASE_TABLES, RETIRED_SYSTEM_CONFIG_KEYS
from app.utils import ExceptionUtils
from config import Config
from web.backend.user import User


system_files_bp = Blueprint("system_files", __name__)


def create_sqlite_backup(source_path: Path, destination_path: Path):
    if not source_path.is_file():
        raise FileNotFoundError(f"数据库文件不存在: {source_path}")

    source_connection = sqlite3.connect(str(source_path))
    destination_connection = sqlite3.connect(str(destination_path))
    try:
        source_connection.backup(destination_connection)
        tables_to_clear = {
            "search_result_info",
            "download_history",
            "site_signin_history",
        }
        existing_tables = {
            str(row[0]).lower(): str(row[0])
            for row in destination_connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for table in sorted(RETIRED_DATABASE_TABLES.intersection(existing_tables)):
            destination_connection.execute(f'DROP TABLE "{existing_tables[table]}"')
        for table in sorted(tables_to_clear.intersection(existing_tables)):
            destination_connection.execute(f'DELETE FROM "{existing_tables[table]}"')
        if "system_dict" in existing_tables:
            destination_connection.executemany(
                f'DELETE FROM "{existing_tables["system_dict"]}" '
                'WHERE type = ? AND "key" = ?',
                [("SystemConfig", key) for key in sorted(RETIRED_SYSTEM_CONFIG_KEYS)],
            )
        destination_connection.commit()
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError("备份数据库完整性校验失败")
    finally:
        destination_connection.close()
        source_connection.close()


@system_files_bp.route("/dirlist", methods=["POST"])
@login_required
def dirlist():
    items = ['<ul class="jqueryFileTree" style="display: none;">']
    try:
        from web.action import get_allowed_file_roots, resolve_allowed_file_path
        from web.security import request_has_system_settings

        input_dir = request.form.get("dir")
        file_filter = request.form.get("filter")
        unrestricted = request_has_system_settings()
        roots = get_allowed_file_roots()
        if not input_dir or input_dir == "/":
            if unrestricted:
                paths = [Path("/") / name for name in os.listdir("/")]
            else:
                paths = list(roots)
        else:
            current_dir = os.path.normpath(urllib.parse.unquote(input_dir))
            if unrestricted:
                current_dir = Path(current_dir)
                if not current_dir.is_dir():
                    current_dir = current_dir.parent
            else:
                current_dir = resolve_allowed_file_path(
                    current_dir, roots=roots, must_exist=True)
                if not current_dir.is_dir():
                    current_dir = current_dir.parent
            paths = [current_dir / name for name in os.listdir(current_dir)]

        for item_path in sorted(paths, key=lambda path: (not os.path.isdir(path), str(path).lower())):
            if not unrestricted:
                try:
                    item_path = resolve_allowed_file_path(
                        str(item_path), roots=roots, must_exist=True)
                except ValueError:
                    continue
            item_name = os.path.basename(item_path) or item_path
            safe_path = html.escape(str(item_path).replace("\\", "/"), quote=True)
            safe_name = html.escape(str(item_name).replace("\\", "/"))
            if os.path.isdir(item_path):
                items.append(
                    f'<li class="directory collapsed"><a rel="{safe_path}/">{safe_name}</a></li>'
                )
            elif file_filter != "HIDE_FILES_FILTER":
                extension = html.escape(os.path.splitext(item_name)[1][1:], quote=True)
                items.append(
                    f'<li class="file ext_{extension}"><a rel="{safe_path}">{safe_name}</a></li>'
                )
    except RequestEntityTooLarge:
        raise
    except Exception as error:
        ExceptionUtils.exception_traceback(error)
        items.append(f"加载路径失败: {html.escape(str(error))}")
    items.append("</ul>")
    return make_response("".join(items), 200)


@system_files_bp.route("/backup", methods=["POST"])
@login_required
def backup():
    backup_dir = None
    zip_file = None
    try:
        config_path = Path(Config().get_config_path())
        backup_root = config_path / "backup"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_dir = Path(tempfile.mkdtemp(prefix="bk_", dir=backup_root))

        shutil.copy2(config_path / "config.yaml", backup_dir)
        category = (Config().get_config("media") or {}).get("category")
        if category:
            category_name = str(category).strip()
            if Path(category_name).name != category_name \
                    or "/" in category_name \
                    or "\\" in category_name:
                raise ValueError("媒体分类配置名不合法")
            category_file = config_path / f"{category_name}.yaml"
            if category_file.is_file() and not category_file.is_symlink():
                shutil.copy2(category_file, backup_dir / category_file.name)

        sites_source = config_path / "sites"
        if sites_source.is_dir() and not sites_source.is_symlink():
            sites_backup = backup_dir / "sites"
            sites_backup.mkdir()
            for site_file in sites_source.iterdir():
                if site_file.suffix.lower() in {".yml", ".yaml"} \
                        and site_file.is_file() \
                        and not site_file.is_symlink():
                    shutil.copy2(site_file, sites_backup / site_file.name)
        create_sqlite_backup(config_path / "user.db", backup_dir / "user.db")

        zip_file = Path(shutil.make_archive(str(backup_dir), "zip", str(backup_dir)))
        shutil.rmtree(backup_dir)
        backup_dir = None

        response = send_file(
            zip_file,
            as_attachment=True,
            download_name=f"nastool-backup-{zip_file.stem.removeprefix('bk_')}.zip",
        )
        def cleanup_backup_artifacts():
            zip_file.unlink(missing_ok=True)
            try:
                backup_root.rmdir()
            except OSError:
                pass

        response.call_on_close(cleanup_backup_artifacts)
        return response
    except Exception as error:
        ExceptionUtils.exception_traceback(error)
        if backup_dir:
            shutil.rmtree(backup_dir, ignore_errors=True)
        if zip_file:
            zip_file.unlink(missing_ok=True)
        if 'backup_root' in locals():
            try:
                backup_root.rmdir()
            except OSError:
                pass
        return make_response("创建备份失败", 400)


@system_files_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    try:
        uploaded_file = request.files["file"]
        filename = secure_filename(uploaded_file.filename)
        if not filename:
            return {"code": 1, "msg": "文件名为空或不合法", "filepath": ""}

        extension = Path(filename).suffix.lower()
        allowed_extensions = {".torrent"}
        if extension not in allowed_extensions:
            return {"code": 1, "msg": f"不支持的文件类型: {extension}", "filepath": ""}

        user_info = User().get_user(current_user.username)
        user_permissions = set(str(user_info.pris).split(",")) if user_info and user_info.pris else set()
        is_admin = bool(user_info and user_info.id == 0)
        can_upload = is_admin or bool(
            user_permissions.intersection({"系统设置", "资源搜索", "下载管理"})
        )
        if not can_upload:
            return {"code": 1, "msg": "权限不足，拒绝上传该类型文件", "filepath": ""}, 403

        temp_path = Path(Config().get_temp_path()).resolve()
        temp_path.mkdir(parents=True, exist_ok=True)
        file_path = (temp_path / filename).resolve()
        if temp_path not in file_path.parents:
            return {"code": 1, "msg": "非法的文件路径", "filepath": ""}

        uploaded_file.seek(0, os.SEEK_END)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)
        if file_size > 20 * 1024 * 1024:
            return {"code": 1, "msg": "文件大小超过限制 (最大 20MB)", "filepath": ""}

        uploaded_file.save(str(file_path))
        return {"code": 0, "filename": filename, "filepath": str(file_path)}
    except RequestEntityTooLarge:
        raise
    except Exception as error:
        ExceptionUtils.exception_traceback(error)
        return {"code": 1, "msg": "上传文件失败", "filepath": ""}
