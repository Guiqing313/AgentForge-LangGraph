r"""测量 SSE 首事件延迟（进程内 ASGI，无端口）。

用法：D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe scripts\measure_sse_latency.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
for name in ("sse_latency.db", "sse_latency_checkpoints.sqlite"):
    target = DATA / name
    if target.exists():
        target.unlink()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DATA / 'sse_latency.db'}"
os.environ["CHECKPOINT_DB"] = str(DATA / "sse_latency_checkpoints.sqlite")
os.environ["LLM_MODE"] = "mock"
os.environ["WORKER_ENABLED"] = "false"
os.environ["HUMAN_REVIEW_ENABLED"] = "false"
os.environ["WEB_SEARCH_ENABLED"] = "false"
os.environ["MEMORY_ENABLED"] = "false"
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.db.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.task_service import TaskService  # noqa: E402


async def _create_completed_task() -> int:
    await init_db()
    task = await TaskService.create_task("SSE 延迟测量")
    await TaskService.run_task(task.id)
    return task.id


def main() -> int:
    task_id = asyncio.run(_create_completed_task())
    samples: list[float] = []
    with TestClient(app) as client:
        for _ in range(5):
            start = time.perf_counter()
            with client.stream("GET", f"/api/tasks/{task_id}/stream") as response:
                for chunk in response.iter_text():
                    if chunk.strip():
                        samples.append((time.perf_counter() - start) * 1000)
                        break
    median = statistics.median(samples)
    print(f"samples_ms={[round(s, 1) for s in samples]}")
    print(f"p50_ms={round(median, 1)}")
    print("SSE_LATENCY_OK" if median <= 2000 else "SSE_LATENCY_BAD")
    return 0 if median <= 2000 else 2


if __name__ == "__main__":
    raise SystemExit(main())
