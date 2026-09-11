"""A5：成本模型与预算闸门测试（离线；2026-09-11 复测修复后）。"""

import pytest

from app.cost import (
    BudgetExceeded,
    PaidProviderNotVerified,
    enforce_budget,
    enforce_pre_task_budget,
    ensure_paid_provider_allowed,
    estimate_cost_cny,
    estimate_task_upper_bound_cny,
    load_prices,
    price_status,
    require_paid_usage,
)


def test_ollama_cost_is_zero():
    assert estimate_cost_cny(provider="ollama", prompt_tokens=10000, completion_tokens=2000) == 0.0


def test_deepseek_cost_uses_tokens_and_tavily():
    prices = {
        "deepseek": {"input_per_million_cny": 2.0, "output_per_million_cny": 8.0},
        "tavily": {"per_credit_cny": 0.058},
    }
    cost = estimate_cost_cny(
        provider="deepseek",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
        tavily_calls=10,
        prices=prices,
    )
    assert cost == pytest.approx(2.0 + 4.0 + 0.58, rel=1e-6)


def test_require_paid_usage_partial_fails_closed():
    """复测 P1-1：任一 usage 字段缺失都必须拒绝。"""
    require_paid_usage("ollama", None, None)
    require_paid_usage("deepseek", 100, 100)
    with pytest.raises(PaidProviderNotVerified):
        require_paid_usage("deepseek", 100, None)
    with pytest.raises(PaidProviderNotVerified):
        require_paid_usage("deepseek", None, 100)


def test_paid_provider_requires_allow_paid():
    with pytest.raises(PaidProviderNotVerified):
        ensure_paid_provider_allowed("deepseek", allow_paid=False)


def test_placeholder_authorization_allows_paid():
    prices = {
        "verified_at": None,
        "authorized_at": "2026-09-10",
        "deepseek": {
            "verified_at": None,
            "authorized_at": "2026-09-10",
            "input_per_million_cny": 2.0,
            "output_per_million_cny": 8.0,
        },
        "tavily": {"per_credit_cny": 0.058, "authorized_at": "2026-09-10"},
    }
    assert price_status("deepseek", prices) == "placeholder-authorized"
    assert ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=prices) == "placeholder-authorized"


def test_official_verification_status():
    prices = {
        "verified_at": "2026-09-10",
        "deepseek": {
            "verified_at": "2026-09-10",
            "input_per_million_cny": 2.0,
            "output_per_million_cny": 8.0,
        },
        "tavily": {"per_credit_cny": 0.058, "verified_at": "2026-09-10"},
    }
    assert price_status("deepseek", prices) == "official"
    assert ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=prices) == "official"


def test_invalid_date_is_unauthorized():
    """复测 P1-3：verified_at/authorized_at 必须是合法 YYYY-MM-DD。"""
    prices = {"verified_at": "not-a-date", "authorized_at": None, "deepseek": {"verified_at": "not-a-date", "authorized_at": None}}
    assert price_status("deepseek", prices) == "unauthorized"
    with pytest.raises(PaidProviderNotVerified):
        ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=prices)


def test_default_prices_authorization_consumed():
    """默认价格表的占位授权已在 2026-09-10 消费，再次付费需重新授权。"""
    table = load_prices()
    assert table["verified_at"] is None
    assert table["authorized_at"] == "2026-09-10"
    assert table["authorization_consumed_at"] == "2026-09-10"
    assert price_status("deepseek", table) == "unauthorized"


def test_empty_prices_dict_does_not_fall_back():
    """复测新 P1：显式传入空表不得回退到默认授权表。"""
    assert price_status("deepseek", {}) == "unauthorized"


def test_missing_rate_fields_are_unauthorized():
    """复测新 P1：费率字段缺失时不得按 0 放行。"""
    prices = {"verified_at": "2026-09-10", "deepseek": {"verified_at": "2026-09-10"}}
    assert price_status("deepseek", prices) == "unauthorized"


def test_upper_bound_covers_recorded_deepseek_task():
    """复测 P1-2c：预检上界必须覆盖实际记录的 15 Tavily / 13 LLM 任务。"""
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).resolve().parent.parent / "data" / "live_results.json").read_text(encoding="utf-8"))
    actual_max = max(record["estimated_cost_cny"] for record in data["deepseek"]["records"])
    upper = estimate_task_upper_bound_cny(
        provider="deepseek",
        max_tavily_calls=15,
        max_llm_calls=15,
        max_tokens_per_call=4096,
        max_prompt_tokens_per_call=8000,
        prices=load_prices(),
    )
    assert upper >= actual_max


def test_llm_call_cap_and_task_tavily_cap():
    """运行时硬上限必须真实生效（LLM 调用数与单任务 Tavily 数）。"""
    from app import observability

    with observability.track(task_id=1, provider="ollama", max_llm_calls=1) as tracker:
        tracker.reserve_llm()
        tracker.record_llm(provider="ollama", latency_ms=1.0)
        with pytest.raises(BudgetExceeded):
            tracker.reserve_llm()

    with observability.track(task_id=2, provider="ollama", max_tavily_calls=1) as tracker:
        tracker.reserve_search("tavily")
        tracker.record_search("tavily", "q1", True, 1)
        with pytest.raises(BudgetExceeded):
            tracker.reserve_search("tavily")


def test_concurrent_llm_reservation_is_atomic():
    """复测第三轮 P1-A：并发下也不得突破 LLM 上限。"""
    import threading

    from app import observability

    with observability.track(task_id=1, provider="ollama", max_llm_calls=1) as tracker:
        barrier = threading.Barrier(5)
        results: list[str] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            try:
                tracker.reserve_llm()
                with lock:
                    results.append("ok")
            except BudgetExceeded:
                with lock:
                    results.append("blocked")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert results.count("ok") == 1
    assert results.count("blocked") == 4


def test_missing_tavily_rate_blocks_deepseek():
    """复测第三轮 P1-B：DeepSeek 价格完整性必须包含 Tavily 费率。"""
    prices = {
        "verified_at": "2026-09-10",
        "deepseek": {
            "verified_at": "2026-09-10",
            "input_per_million_cny": 2.0,
            "output_per_million_cny": 8.0,
        },
    }
    assert price_status("deepseek", prices) == "unauthorized"


def test_pre_task_budget_rejects_before_running():
    """复测 P1-2：任务开始前用保守上界预检，不允许先超支。"""
    enforce_pre_task_budget(spent_cny=1.0, upper_bound_cny=0.1, max_cost_cny=1.2)
    with pytest.raises(BudgetExceeded):
        enforce_pre_task_budget(spent_cny=1.0, upper_bound_cny=0.5, max_cost_cny=1.2)


def test_task_upper_bound_is_positive_for_paid():
    prices = {
        "deepseek": {"input_per_million_cny": 2.0, "output_per_million_cny": 8.0},
        "tavily": {"per_credit_cny": 0.058},
    }
    upper = estimate_task_upper_bound_cny(
        provider="deepseek", max_tavily_calls=6, max_llm_calls=12, max_tokens_per_call=4096, prices=prices
    )
    assert upper > 0
    assert estimate_task_upper_bound_cny(provider="ollama", max_tavily_calls=6, prices=prices) == pytest.approx(0.348)


def test_enforce_budget_limits():
    enforce_budget(spent_cny=1.0, max_cost_cny=2.0, tavily_calls=5, max_tavily_calls=10)
    with pytest.raises(BudgetExceeded):
        enforce_budget(spent_cny=2.5, max_cost_cny=2.0, tavily_calls=5, max_tavily_calls=10)
    with pytest.raises(BudgetExceeded):
        enforce_budget(spent_cny=0.1, max_cost_cny=2.0, tavily_calls=11, max_tavily_calls=10)


def test_search_call_limit_blocks_further_tavily(monkeypatch):
    """复测 P1-2：Tavily 达到硬上限后不再发起外部调用。"""
    from app.tools import search as search_mod

    search_mod.clear_cache()
    search_mod.configure_limits(1)
    try:
        tool = search_mod.WebSearchTool(tavily_api_key="fake", use_cache=False)
        calls = {"n": 0}

        def fake_tavily(query):
            calls["n"] += 1
            return [{"title": "t", "content": "c", "url": "u"}]

        monkeypatch.setattr(tool, "_search_tavily", fake_tavily)
        tool.search("q1")
        with pytest.raises(RuntimeError):
            tool.search("q2")
        assert calls["n"] == 1
    finally:
        search_mod.configure_limits(None)
        search_mod.clear_cache()


def test_tavily_missing_authorization_blocks_deepseek():
    """复测第四轮 P2：DeepSeek 状态必须同时要求 Tavily 的授权/核验字段。"""
    prices = {
        "verified_at": "2026-09-10",
        "authorized_at": None,
        "deepseek": {
            "verified_at": "2026-09-10",
            "input_per_million_cny": 2.0,
            "output_per_million_cny": 8.0,
        },
        "tavily": {"per_credit_cny": 0.058},
    }
    assert price_status("deepseek", prices) == "unauthorized"


def test_concurrent_cost_reservation_counts_inflight():
    """复测第四轮 P1：并发下成本上限也不能被在途预留绕过。"""
    import threading

    from app import observability

    prices = {
        "verified_at": "2026-09-10",
        "authorized_at": "2026-09-10",
        "deepseek": {
            "verified_at": "2026-09-10",
            "authorized_at": "2026-09-10",
            "input_per_million_cny": 2.0,
            "output_per_million_cny": 8.0,
        },
        "tavily": {"per_credit_cny": 0.058, "verified_at": "2026-09-10", "authorized_at": "2026-09-10"},
    }
    # 单次最坏 LLM 成本 ≈ 8000/1M*2 + 4096/1M*8 = 0.0488；上限 0.06 只允许 1 个在途预留
    with observability.track(task_id=1, provider="deepseek", allow_paid=True, prices=prices, max_cost_cny=0.06) as tracker:
        barrier = threading.Barrier(5)
        results: list[str] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            try:
                tracker.reserve_llm()
                with lock:
                    results.append("ok")
            except BudgetExceeded:
                with lock:
                    results.append("blocked")

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert results.count("ok") == 1
    assert results.count("blocked") == 4


def test_cache_hit_is_recorded_once():
    """复测第四轮 P2：cache 命中也要记账，且每次 search 只记一条。"""
    from app import observability
    from app.tools import search as search_mod

    search_mod.clear_cache()
    search_mod.configure_limits(None)
    tool = search_mod.WebSearchTool(tavily_api_key="fake", use_cache=True)
    tool._search_tavily = lambda query: [{"title": "t", "content": "c", "url": "u"}]
    try:
        with observability.track(task_id=1, provider="ollama") as tracker:
            tool.search("q1")
            tool.search("q1")
            snapshot = tracker.snapshot()
        assert snapshot["search_by_backend"].get("tavily") == 1
        assert snapshot["search_by_backend"].get("cache") == 1
        assert snapshot["search_calls"] == 2
    finally:
        search_mod.clear_cache()
