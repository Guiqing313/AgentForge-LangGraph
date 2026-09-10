"""端到端真实运行脚本：用真实 LLM 与真实搜索跑一个研究主题并记录真实数据。

用法：
    python scripts/run_e2e.py "研究主题" [--out data/run.json]

运行前请在 .env 中配置 DEEPSEEK_API_KEY（以及可选的 TAVILY_API_KEY）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.graph.research_graph import ResearchGraph  # noqa: E402
from app.graph.state import initial_state  # noqa: E402


def needs_live_validation() -> bool:
    """mock 模式无需真实 key；仅真实 provider 校验配置。"""
    return settings.effective_provider != "mock"


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentForge 端到端运行")
    parser.add_argument("topic", type=str, help="研究主题")
    default_name = "run_result.mock.json" if settings.effective_provider == "mock" else "run_result.json"
    parser.add_argument("--out", type=str, default=str(ROOT / "data" / default_name))
    args = parser.parse_args()

    if needs_live_validation():
        settings.validate_for_live()

    graph = ResearchGraph().build()
    state = initial_state(args.topic)

    start = time.perf_counter()
    print(f"[1] 开始研究：{args.topic}")
    result = graph.invoke(state)
    elapsed = time.perf_counter() - start

    record = {
        "topic": args.topic,
        "status": result.get("status"),
        "elapsed_seconds": round(elapsed, 2),
        "sub_questions": result.get("sub_questions", []),
        "review_rounds": result.get("review_rounds", 0),
        "review_history": result.get("review_history", []),
        "search_log": result.get("log", []),
        "final_report": result.get("final_report", ""),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[2] 状态：{record['status']}")
    print(f"[3] 子问题数量：{len(record['sub_questions'])}")
    print(f"[4] 审核轮次：{record['review_rounds']}")
    print(f"[5] 耗时：{elapsed:.2f} 秒")
    print(f"[6] 结果已保存：{out_path}")
    print("\n===== 报告预览（前 800 字符）=====\n")
    print(record["final_report"][:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())