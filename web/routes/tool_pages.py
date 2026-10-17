from flask import Blueprint, render_template
from flask_login import login_required

from app.tools import get_tools
from app.tools.site_signin.config import get_site_signin_config


tool_pages_bp = Blueprint("tool_pages", __name__)


@tool_pages_bp.route("/tools", methods=["GET", "POST"])
@login_required
def tool_index():
    return render_template("tools/index.html", Tools=get_tools())


@tool_pages_bp.route("/tools/site-signin", methods=["GET", "POST"])
@login_required
def site_signin():
    return render_template(
        "tools/site_signin.html",
        ToolConfig=get_site_signin_config(),
    )
