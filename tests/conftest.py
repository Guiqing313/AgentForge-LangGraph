"""pytest 公共配置：默认 mock LLM + 临时 SQLite，保证测试离线且不污染真实数据。"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

# 必须在 import app 之前设置
os.environ["LLM_MODE"] = "mock"  # 测试强制 mock，避免误用真实 provider
os.environ["WORKER_ENABLED"] = "false"  # 测试不启动后台 worker，保证确定性
_TMP_DB = Path(tempfile.gettempdir()) / f"agentforge_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"  # 强制隔离，避免污染真实数据库

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
