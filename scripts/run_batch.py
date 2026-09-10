"""批量真实端到端测试：多个主题依次运行，汇总真实数据到 data/batch_results.json。"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, ".")

from app.graph.research_graph import ResearchGraph
from app.graph.state import initial_state

TOPICS = [
    "2025年大语言模型发展趋势",
    "向量数据库技术选型对比",
    "Python异步编程最佳实践",
    "多智能体系统架构设计",
    "检索增强生成RAG技术现状",
]


def run_one(topic: str) -> dict:
    start = time.perf_counter()
    try:
        graph = ResearchGraph().build()
        result = graph.invoke(initial_state(topic))
        elapsed = time.perf_counter() - start
        total_docs = sum(len(o.documents) for o in result.get("search_outcomes", {}).values())
        return {
            "topic": topic,
            "status": result.get("status"),
            "elapsed_seconds": round(elapsed, 2),
            "sub_questions": len(result.get("sub_questions", [])),
            "total_documents": total_docs,
            "review_rounds": result.get("review_rounds", 0),
            "review_scores": [h["score"] for h in result.get("review_history", [])],
            "report_length": len(result.get("final_report", "")),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "topic": topic,
            "status": "failed",
            "error": str(exc),
            "elapsed_seconds": round(time.perf_counter() - start, 2),
        }


def main() -> int:
    results = []
    for topic in TOPICS:
        print(f"\n===== 测试主题：{topic} =====", flush=True)
        record = run_one(topic)
        results.append(record)
        print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)

    out = pathlib.Path("data/batch_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n===== 汇总已保存：{out} =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
