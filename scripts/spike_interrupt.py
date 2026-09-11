r"""B1 spike：interrupt/resume + 进程重启恢复（纯图，mock 逻辑，不调用 LLM）。

验证点：
1) planner 后 interrupt，返回 __interrupt__；
2) 用 Command(resume=编辑后的子问题) 恢复，searcher 收到编辑后的列表；
3) 关闭并重新打开 SqliteSaver（模拟进程重启）后仍能恢复；
4) planner 只执行一次（恢复不重跑已完成的节点）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class SpikeState(TypedDict, total=False):
    topic: str
    sub_questions: list[str]
    received: list[str]
    planner_calls: int


def planner(state: SpikeState) -> dict:
    return {"sub_questions": ["原始A", "原始B"], "planner_calls": state.get("planner_calls", 0) + 1}


def human_review(state: SpikeState) -> dict:
    edited = interrupt({"proposed": state["sub_questions"], "message": "请编辑子问题后继续"})
    cleaned = [q for q in (edited or []) if isinstance(q, str) and q.strip()]
    return {"sub_questions": cleaned or state["sub_questions"]}


def searcher(state: SpikeState) -> dict:
    return {"received": list(state["sub_questions"])}


def build(saver):
    graph = StateGraph(SpikeState)
    graph.add_node("planner", planner)
    graph.add_node("human_review", human_review)
    graph.add_node("searcher", searcher)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "human_review")
    graph.add_edge("human_review", "searcher")
    graph.add_edge("searcher", END)
    return graph.compile(checkpointer=saver)


def main() -> int:
    db_path = ROOT / "data" / "spike_interrupt.sqlite"
    if db_path.exists():
        db_path.unlink()
    config = {"configurable": {"thread_id": "spike-thread-1"}}

    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = build(saver)
        first = graph.invoke({"topic": "spike"}, config)
        interrupted = "__interrupt__" in first
        planner_calls_1 = first.get("planner_calls")
        print(f"phase1_interrupted={interrupted} planner_calls={planner_calls_1} proposed={first.get('sub_questions')}")

    # 关闭连接后重新打开，模拟进程重启
    with SqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = build(saver)
        second = graph.invoke(Command(resume=["编辑后的A", "编辑后的B", "编辑后的C"]), config)
        received = second.get("received")
        planner_calls_2 = second.get("planner_calls")
        print(f"phase2_received={received} planner_calls={planner_calls_2}")

    ok = (
        interrupted
        and planner_calls_1 == 1
        and received == ["编辑后的A", "编辑后的B", "编辑后的C"]
        and planner_calls_2 == 1
    )
    print("SPIKE_OK" if ok else "SPIKE_FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
