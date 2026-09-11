r"""B1+B2 端到端验证（短轮询、增量输出）。

前置：
    1) 重置演示库：python scripts/reset_demo_db.py
    2) 启动后端（示例）：
       $env:DATABASE_URL="sqlite+aiosqlite:///D:/codex使用文件夹/AgentForge-v2/data/demo.db"
       $env:CHECKPOINT_DB="D:/codex使用文件夹/AgentForge-v2/data/demo_checkpoints.sqlite"
       $env:LLM_MODE="mock"; $env:HUMAN_REVIEW_ENABLED="true"; $env:WEB_SEARCH_ENABLED="false"
       uvicorn app.main:app --port 8001

运行：
    python scripts/e2e_review_flow.py --api-url http://127.0.0.1:8001 --max-wait 30
"""

from __future__ import annotations

import argparse
import time

import requests


def _wait_status(api_url: str, task_id: int, targets: set[str], max_wait: float, poll: float) -> dict:
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        response = requests.get(f"{api_url}/api/tasks/{task_id}", timeout=10)
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
    parser = argparse.ArgumentParser(description="B1+B2 端到端验证")
    parser.add_argument("--api-url", default="http://127.0.0.1:8001")
    parser.add_argument("--topic", default="E2E：RAG 与 Agent")
    parser.add_argument("--max-wait", type=float, default=30.0)
    parser.add_argument("--poll", type=float, default=0.4)
    args = parser.parse_args()

    created = requests.post(f"{args.api_url}/api/tasks", json={"topic": args.topic}, timeout=10)
    created.raise_for_status()
    task_id = created.json()["data"]["id"]
    print(f"[create] task_id={task_id} status={created.json()['data']['status']}", flush=True)

    paused = _wait_status(args.api_url, task_id, {"paused", "failed", "canceled"}, args.max_wait, args.poll)
    if paused["status"] != "paused":
        print(f"E2E_BAD：预期 paused，实际 {paused['status']}", flush=True)
        return 2
    print(f"[paused] proposed={paused.get('sub_questions')}", flush=True)

    edited = ["E2E 编辑问题一", "E2E 编辑问题二"]
    resumed = requests.post(
        f"{args.api_url}/api/tasks/{task_id}/resume", json={"sub_questions": edited}, timeout=10
    )
    resumed.raise_for_status()
    print(f"[resume] status={resumed.json()['data']['status']}", flush=True)

    final = _wait_status(args.api_url, task_id, {"completed", "failed", "canceled"}, args.max_wait, args.poll)
    ok = final["status"] == "completed" and final.get("sub_questions") == edited
    print(f"[final] status={final['status']} sub_questions={final.get('sub_questions')}", flush=True)
    print("E2E_OK" if ok else "E2E_BAD", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
