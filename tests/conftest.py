"""pytest 公共配置：默认 mock LLM + 临时 SQLite，保证测试离线且不污染真实数据。"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

# 必须在 import app 之前设置
os.environ.setdefault("LLM_MODE", "mock")
_TMP_DB = Path(tempfile.gettempdir()) / f"agentforge_test_{uuid.uuid4().hex}.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DB}")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
