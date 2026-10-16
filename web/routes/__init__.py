from web.routes.download_pages import download_pages_bp
from web.routes.search_pages import search_pages_bp
from web.routes.settings_pages import settings_pages_bp
from web.routes.site_pages import site_pages_bp
from web.routes.system_files import system_files_bp
from web.routes.tool_pages import tool_pages_bp

__all__ = [
    "system_files_bp", "tool_pages_bp",
    "search_pages_bp", "download_pages_bp", "site_pages_bp", "settings_pages_bp",
]
