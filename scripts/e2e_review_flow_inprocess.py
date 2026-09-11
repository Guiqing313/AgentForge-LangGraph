r"""B1+B2 端到端（进程内 ASGI TestClient；不启动真实端口、无残留进程）。

用法：
    <repo>\venv\Scripts\python.exe scripts\e2e_review_flow_inprocess.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
for name in ("demo.db", "demo_checkpoints.sqlite"):
    target = DATA / name
    if target.exists():
        target.unlink()

# 必须在 import app 之前设置
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DATA / 'demo.db'}"
os.environ["CHECKPOINT_DB"] = str(DATA / "demo_checkpoints.sqlite")
os.environ["LLM_MODE"] = "mock"
os.environ["HUMAN_REVIEW_ENABLED"] = "true"
os.environ["WORKER_ENABLED"] = "true"
os.environ["WEB_SEARCH_ENABLED"] = "false"
os.environ["MEMORY_ENABLED"] = "false"
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def wait_for(client: TestClient, task_id: int, targets: set[str], max_wait: float = 30.0, poll: float = 0.4) -> dict:
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        response.raise_for_status()
        task = response.json()["data"]
        if task["status"] != last:
            print(f"[poll] status={task['status']}", flush=True)
            last = task["status"]
        if task["status"] in targets:
            return task
        time.sleep(poll)
    raise TimeoutError(f"等待 {targets} 超时（{max_wait}s），最后状态={last}")


def main() -> int:
    with TestClient(app) as client:
        created = client.post("/api/tasks", json={"topic": "进程内 E2E：RAG 与 Agent"})
        created.raise_for_status()
        task_id = created.json()["data"]["id"]
        print(f"[create] task_id={task_id} status={created.json()['data']['status']}", flush=True)

        paused = wait_for(client, task_id, {"paused", "failed", "canceled"})
        if paused["status"] != "paused":
            print(f"E2E_BAD：预期 paused，实际 {paused['status']}", flush=True)
            return 2
        print(f"[paused] proposed={paused.get('sub_questions')}", flush=True)

        edited = ["E2E 编辑问题一", "E2E 编辑问题二"]
        resumed = client.post(f"/api/tasks/{task_id}/resume", json={"sub_questions": edited})
        resumed.raise_for_status()
        print(f"[resume] status={resumed.json()['data']['status']}", flush=True)

        final = wait_for(client, task_id, {"completed", "failed", "canceled"})
        ok = final["status"] == "completed" and final.get("sub_questions") == edited
        print(f"[final] status={final['status']} sub_questions={final.get('sub_questions')}", flush=True)
        print("E2E_OK" if ok else "E2E_BAD", flush=True)
        return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
