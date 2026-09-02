import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_TEST_CONFIG_DIR = None

test_config_path = os.environ.get("NASTOOL_TEST_CONFIG")
if not test_config_path:
    _TEST_CONFIG_DIR = tempfile.TemporaryDirectory(prefix="nastool-tests-")
    test_config_path = os.path.join(_TEST_CONFIG_DIR.name, "config.yaml")

# 测试始终使用显式测试配置，避免误写开发者或宿主机的真实数据库。
os.environ["NASTOOL_CONFIG"] = test_config_path

from check_config import initialize_config
from app.db import init_db

initialize_config()
init_db()
