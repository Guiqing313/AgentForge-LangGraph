r"""B1 演示：真实 ResearchGraph + AsyncSqliteSaver 的 interrupt → 编辑子问题 → resume。

用法（AgentForge venv，mock LLM，不需要 Ollama）：
    <repo>\venv\Scripts\python.exe scripts\demo_interrupt.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("LLM_MODE", "mock")
sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from app.graph.research_graph import ResearchGraph  # noqa: E402
from app.graph.state import initial_state  # noqa: E402


async def main() -> int:
    db_path = ROOT / "data" / "demo_interrupt.sqlite"
    if db_path.exists():
        db_path.unlink()
    config = {"configurable": {"thread_id": "demo-task-1"}}

    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = ResearchGraph().build(checkpointer=saver, enable_human_review=True)
        first = await graph.ainvoke(initial_state("RAG 与 Agent 的区别"), config)
        paused = "__interrupt__" in first
        print(f"paused={paused} proposed={first.get('sub_questions')}")

        edited = ["编辑：RAG 的核心流程", "编辑：Agent 的工具调用"]
        final = await graph.ainvoke(Command(resume=edited), config)
        print(f"status={final.get('status')} sub_questions={final.get('sub_questions')}")
        print(f"report_chars={len(final.get('final_report') or '')}")

    ok = paused and final.get("status") == "completed" and final.get("sub_questions") == edited
    print("DEMO_OK" if ok else "DEMO_BAD")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
