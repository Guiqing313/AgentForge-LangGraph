"""A5：成本模型与预算闸门测试（离线）。"""

import pytest

from app.cost import (
    BudgetExceeded,
    PaidProviderNotVerified,
    enforce_budget,
    ensure_paid_provider_allowed,
    estimate_cost_cny,
    load_prices,
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


def test_paid_provider_requires_allow_paid():
    with pytest.raises(PaidProviderNotVerified):
        ensure_paid_provider_allowed("deepseek", allow_paid=False)


def test_paid_provider_requires_verified_prices():
    with pytest.raises(PaidProviderNotVerified):
        ensure_paid_provider_allowed("deepseek", allow_paid=True, prices={"verified_at": None})


def test_default_prices_verified_after_user_authorization():
    """用户 2026-09-10 授权按占位价执行 DeepSeek 对比后，默认价格表应已确认。"""
    table = load_prices()
    assert table["verified_at"] == "2026-09-10"
    ensure_paid_provider_allowed("deepseek", allow_paid=True, prices=table)


def test_unverified_prices_block_paid():
    with pytest.raises(PaidProviderNotVerified):
        ensure_paid_provider_allowed("deepseek", allow_paid=True, prices={"verified_at": None})


def test_require_paid_usage_fail_closed():
    require_paid_usage("ollama", None, None)
    with pytest.raises(PaidProviderNotVerified):
        require_paid_usage("deepseek", None, None)


def test_enforce_budget_limits():
    enforce_budget(spent_cny=1.0, max_cost_cny=2.0, tavily_calls=5, max_tavily_calls=10)
    with pytest.raises(BudgetExceeded):
        enforce_budget(spent_cny=2.5, max_cost_cny=2.0, tavily_calls=5, max_tavily_calls=10)
    with pytest.raises(BudgetExceeded):
        enforce_budget(spent_cny=0.1, max_cost_cny=2.0, tavily_calls=11, max_tavily_calls=10)
