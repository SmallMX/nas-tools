from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.tools import get_tools
from app.tools.site_signin.config import get_site_signin_config
from web.backend.user import User


tool_pages_bp = Blueprint("tool_pages", __name__)


@tool_pages_bp.route("/tools", methods=["GET", "POST"])
@login_required
def tool_index():
    user = User().get_user(current_user.username)
    permissions = {
        item.strip() for item in str(user.pris).split(",") if item.strip()
    } if user and user.pris else set()
    tools = get_tools() if user and user.id == 0 else tuple(
        tool for tool in get_tools() if tool.permission in permissions
    )
    return render_template("tools/index.html", Tools=tools)


@tool_pages_bp.route("/tools/site-signin", methods=["GET", "POST"])
@login_required
def site_signin():
    return render_template(
        "tools/site_signin.html",
        ToolConfig=get_site_signin_config(),
    )
