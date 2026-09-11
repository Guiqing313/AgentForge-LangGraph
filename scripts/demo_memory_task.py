r"""A2 端到端记忆演示：两个真实任务（mock LLM）经 task_service 跑通记忆生命周期。

任务1「RAG 检索增强生成」完成 → 写入 agent_memory；
任务2「RAG 检索增强」执行前检索到记忆 → planner 日志出现「注入 N 条历史记忆」。

用法（AgentForge venv，需 embedding 服务运行，外部 API 成本 0）：
    <repo>\venv\Scripts\python.exe scripts\demo_memory_task.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
(ROOT / "data").mkdir(exist_ok=True)

# 必须在 import app 之前设置：独立演示数据库 + mock LLM + 记忆开启
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{ROOT / 'data' / 'demo_memory_task.db'}"
os.environ["LLM_MODE"] = "mock"
os.environ["MEMORY_ENABLED"] = "true"
sys.path.insert(0, str(ROOT))

from app.db.database import init_db  # noqa: E402
from app.services.memory_service import MemoryService  # noqa: E402
from app.services.task_service import TaskService  # noqa: E402


async def main() -> int:
    await init_db()
    service = MemoryService()
    before = service.count()

    first = await TaskService.create_task("RAG 检索增强生成")
    await TaskService.run_task(first.id)
    after_first = service.count()

    second = await TaskService.create_task("RAG 检索增强")
    result = await TaskService.run_task(second.id)
    logs = result.logs or []
    injected_lines = [line for line in logs if "历史记忆" in line]

    print(f"task1_id={first.id} memory_count_before={before} after_first={after_first}")
    print(f"task2_id={second.id} status={result.status} review_rounds={result.review_rounds}")
    print(f"task2_logs={logs}")
    print(f"memory_injection_log={injected_lines}")
    ok = after_first > before and bool(injected_lines) and result.status == "completed"
    print("DEMO_OK" if ok else "DEMO_BAD")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
