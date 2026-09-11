r"""本地 live 运行 + 成本闸门（A5）。

用法（AgentForge venv；需 Ollama 与 embedding 服务运行）：
    python scripts/run_live_local.py --topics "RAG 与 Agent 的区别" "大模型应用工程师需要哪些能力" \
        --max-tavily-calls 30 --max-cost-cny 2

DeepSeek 对比（需用户确认价格、更新 config/prices.json 的 verified_at 后）：
    python scripts/run_live_local.py --topics ... --compare-deepseek --allow-paid

说明：
- 默认 provider = ollama（本地，无 API 成本）；Tavily 调用有上限；
- 付费 provider 在 --allow-paid 且 prices.json verified_at 非空时才允许启动（fail-closed）；
- DeepSeek 对比与 Ollama 使用同一进程内搜索缓存，复用同一批搜索结果，避免不公平对比与重复计费。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import observability  # noqa: E402
from app.config import settings  # noqa: E402
from app.cost import (  # noqa: E402
    enforce_budget,
    enforce_pre_task_budget,
    ensure_paid_provider_allowed,
    estimate_cost_cny,
    estimate_task_upper_bound_cny,
    load_prices,
    require_paid_usage,
)
from app.graph.research_graph import ResearchGraph  # noqa: E402
from app.graph.state import initial_state  # noqa: E402
from app.tools.search import cache_size, clear_cache, configure_limits, tavily_calls_used  # noqa: E402

DEFAULT_TOPICS = ["RAG 与 Agent 的区别", "大模型应用工程师需要哪些能力"]


def _apply_provider(provider: str) -> None:
    """在同一进程内切换 LLM provider（只影响 factory 与 BaseAgent 的 settings 引用）。"""
    import app.agents.base as base_module
    import app.llm.factory as factory_module

    new_settings = replace(settings, llm_provider=provider, llm_mode="live")
    factory_module.settings = new_settings
    base_module.settings = new_settings


def _run_topics(provider: str, topics: list[str], max_tavily_calls: int, max_cost_cny: float, max_tavily_per_task: int = 6) -> dict:
    _apply_provider(provider)
    configure_limits(max_tavily_calls)
    graph = ResearchGraph().build()

    records: list[dict] = []
    total_cost = 0.0
    total_tavily = 0
    total_prompt_tokens: int | None = 0
    total_completion_tokens: int | None = 0

    for index, topic in enumerate(topics, start=1):
        # 任务开始前的保守预检：宁可拒绝，也不先超支
        remaining_tavily = max(max_tavily_calls - total_tavily, 0)
        upper_bound = estimate_task_upper_bound_cny(
            provider=provider,
            max_tavily_calls=min(remaining_tavily, max_tavily_per_task),
            max_llm_calls=12,
            max_tokens_per_call=settings.llm_max_tokens,
        )
        enforce_pre_task_budget(spent_cny=total_cost, upper_bound_cny=upper_bound, max_cost_cny=max_cost_cny)

        with observability.track(task_id=index) as tracker:
            start = time.perf_counter()
            result = graph.invoke(initial_state(topic))
            elapsed = round(time.perf_counter() - start, 2)
            snapshot = tracker.snapshot()

        tavily_calls = snapshot["search_by_backend"].get("tavily", 0)
        total_tavily += tavily_calls
        prompt_tokens = snapshot["prompt_tokens"]
        completion_tokens = snapshot["completion_tokens"]
        require_paid_usage(provider, prompt_tokens, completion_tokens)
        cost = estimate_cost_cny(
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tavily_calls=tavily_calls,
        )
        total_cost = round(total_cost + cost, 4)
        if prompt_tokens is not None:
            total_prompt_tokens = (total_prompt_tokens or 0) + prompt_tokens
        if completion_tokens is not None:
            total_completion_tokens = (total_completion_tokens or 0) + completion_tokens

        record = {
            "topic": topic,
            "provider": provider,
            "status": result.get("status"),
            "elapsed_seconds": elapsed,
            "review_rounds": result.get("review_rounds", 0),
            "sub_questions": len(result.get("sub_questions", [])),
            "search_calls": snapshot["search_calls"],
            "search_by_backend": snapshot["search_by_backend"],
            "tavily_calls": tavily_calls,
            "tavily_calls_total_tool": tavily_calls_used(),
            "llm_calls": snapshot["llm_calls"],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_cny": cost,
        }
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
        enforce_budget(
            spent_cny=total_cost,
            max_cost_cny=max_cost_cny,
            tavily_calls=total_tavily,
            max_tavily_calls=max_tavily_calls,
        )

    return {
        "provider": provider,
        "records": records,
        "totals": {
            "tasks": len(records),
            "tavily_calls": total_tavily,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "estimated_cost_cny": total_cost,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentForge 本地 live 运行 + 成本闸门")
    parser.add_argument("--topics", nargs="+", default=DEFAULT_TOPICS)
    parser.add_argument("--max-tavily-calls", type=int, default=30)
    parser.add_argument("--max-tavily-per-task", type=int, default=6, help="单任务预检使用的 Tavily 上界")
    parser.add_argument("--max-cost-cny", type=float, default=10.0, help="外部 API 总成本上限（默认 10 元）")
    parser.add_argument("--max-paid-cost-cny", type=float, default=2.0, help="付费 provider 阶段成本上限（默认 2 元）")
    parser.add_argument("--out", default=str(ROOT / "data" / "live_results.json"))
    parser.add_argument("--compare-deepseek", action="store_true", help="在 Ollama 之后用同一批搜索结果跑 1 次 DeepSeek 对比")
    parser.add_argument("--allow-paid", action="store_true", help="允许付费 provider（需价格表已由用户验证）")
    args = parser.parse_args()

    if settings.llm_mode == "mock":
        print("LLM_MODE=mock：live 运行需要 LLM_MODE=live")
        return 2

    prices = load_prices()
    results: dict = {
        "checked_at": "2026-09-10",
        "prices": prices,
        "mode": "local-ollama",
    }

    primary = "ollama"
    ensure_paid_provider_allowed(primary, allow_paid=True, prices=prices)
    clear_cache()
    def _save(payload: dict) -> Path:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    ollama_result = _run_topics(primary, args.topics, args.max_tavily_calls, args.max_cost_cny, args.max_tavily_per_task)
    results["ollama"] = ollama_result
    results["search_cache_size"] = cache_size()
    _save(results)  # 增量落盘：即使下一阶段中止也不丢已有记录

    if args.compare_deepseek:
        ensure_paid_provider_allowed("deepseek", allow_paid=args.allow_paid, prices=prices)
        remaining_total = max(args.max_cost_cny - ollama_result["totals"]["estimated_cost_cny"], 0.0)
        paid_limit = min(args.max_paid_cost_cny, remaining_total)
        if paid_limit <= 0:
            print("预算已用尽，跳过 DeepSeek 对比")
            return 3
        deepseek_result = _run_topics(
            "deepseek", args.topics, args.max_tavily_calls, paid_limit, args.max_tavily_per_task
        )
        results["deepseek"] = deepseek_result
        results["mode"] = "ollama+deepseek"
        results["comparison_note"] = (
            "planner 子问题数可能因 provider 不同而变化，本对比为探索性，不作控制变量结论。"
        )

    results["search_cache_size"] = cache_size()
    out_path = _save(results)
    print(f"saved={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
