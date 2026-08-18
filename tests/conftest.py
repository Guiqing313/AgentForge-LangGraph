"""pytest 公共配置：默认使用 mock LLM，保证测试离线可运行。"""

import os
import sys
from pathlib import Path

# 必须在 import app 之前设置
os.environ.setdefault("LLM_MODE", "mock")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))