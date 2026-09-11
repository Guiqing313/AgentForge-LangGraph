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
        "deepseek": {"verified_at": None, "authorized_at": "2026-09-10"},
    }
    assert price_status("deepseek", prices) == "placeholder-authorized"
    assert ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=prices) == "placeholder-authorized"


def test_official_verification_status():
    prices = {"verified_at": "2026-09-10", "deepseek": {"verified_at": "2026-09-10"}}
    assert price_status("deepseek", prices) == "official"
    assert ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=prices) == "official"


def test_invalid_date_is_unauthorized():
    """复测 P1-3：verified_at/authorized_at 必须是合法 YYYY-MM-DD。"""
    prices = {"verified_at": "not-a-date", "authorized_at": None, "deepseek": {"verified_at": "not-a-date", "authorized_at": None}}
    assert price_status("deepseek", prices) == "unauthorized"
    with pytest.raises(PaidProviderNotVerified):
        ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=prices)


def test_default_prices_are_authorized_but_not_officially_verified():
    table = load_prices()
    assert table["verified_at"] is None
    assert table["authorized_at"] == "2026-09-10"
    assert price_status("deepseek", table) == "placeholder-authorized"


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
