"""成本模型与预算闸门（A5）。

口径：只统计外部 API 的现金支出；本地 Ollama 推理计 0。
安全策略（fail-closed）：
- 付费 provider（deepseek）必须显式 --allow-paid，且价格表 verified_at 非空；
- 付费调用若拿不到 usage（token），拒绝继续，不允许静默按 0 计；
- 任一上限（Tavily 调用数 / 成本）超限立即中止。
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PRICES_PATH = BASE_DIR / "config" / "prices.json"


class BudgetExceeded(RuntimeError):
    """预算或调用上限被突破。"""


class PaidProviderNotVerified(RuntimeError):
    """付费 provider 未获授权或价格表未验证。"""


def load_prices(path: str | Path | None = None) -> dict:
    price_path = Path(path) if path else DEFAULT_PRICES_PATH
    with open(price_path, encoding="utf-8") as handle:
        return json.load(handle)


def estimate_cost_cny(
    *,
    provider: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    tavily_calls: int = 0,
    prices: dict | None = None,
) -> float:
    """估算外部 API 成本（人民币）。本地 provider 只计 Tavily，不计本地推理。"""
    table = prices or load_prices()
    provider = (provider or "").lower()
    cost = 0.0
    if provider == "deepseek":
        cfg = table.get("deepseek", {})
        cost += (prompt_tokens or 0) / 1_000_000 * float(cfg.get("input_per_million_cny", 0))
        cost += (completion_tokens or 0) / 1_000_000 * float(cfg.get("output_per_million_cny", 0))
    tavily = table.get("tavily", {})
    cost += float(tavily_calls or 0) * float(tavily.get("per_credit_cny", 0))
    return round(cost, 4)


def ensure_paid_provider_allowed(provider: str, *, allow_paid: bool = False, prices: dict | None = None) -> None:
    """付费 provider 的准入门槛。"""
    provider = (provider or "").lower()
    if provider in ("", "ollama", "mock"):
        return
    if not allow_paid:
        raise PaidProviderNotVerified(f"provider={provider} 属付费调用，必须显式 --allow-paid 且先获用户确认")
    table = prices or load_prices()
    if not table.get("verified_at"):
        raise PaidProviderNotVerified("价格表 verified_at 为空：请先与用户核对官方价格并更新 config/prices.json")
    if not (table.get(provider, {}) or {}).get("verified_at"):
        raise PaidProviderNotVerified(f"价格表中 {provider} 的 verified_at 为空：拒绝付费调用")


def require_paid_usage(provider: str, prompt_tokens: int | None, completion_tokens: int | None) -> None:
    """付费 provider 拿不到 usage 时 fail-closed。"""
    if (provider or "").lower() in ("", "ollama", "mock"):
        return
    if prompt_tokens is None and completion_tokens is None:
        raise PaidProviderNotVerified(f"provider={provider} 未返回 usage，拒绝估算成本，调用中止")


def enforce_budget(
    *,
    spent_cny: float,
    max_cost_cny: float | None,
    tavily_calls: int,
    max_tavily_calls: int | None,
) -> None:
    if max_tavily_calls is not None and tavily_calls > max_tavily_calls:
        raise BudgetExceeded(f"Tavily 调用数 {tavily_calls} 超过上限 {max_tavily_calls}")
    if max_cost_cny is not None and spent_cny > max_cost_cny:
        raise BudgetExceeded(f"估算成本 ¥{spent_cny} 超过上限 ¥{max_cost_cny}")
