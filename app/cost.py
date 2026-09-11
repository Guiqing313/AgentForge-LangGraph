"""成本模型与预算闸门（A5；2026-09-11 按复测意见加固）。

口径：只统计外部 API 的现金支出；本地 Ollama 推理计 0。

安全策略（fail-closed）：
- 付费 provider 必须有用户授权（authorized_at）或官方价格核验（verified_at），且显式 --allow-paid；
- 付费调用若 usage 不完整（prompt 或 completion 任一缺失），拒绝估算并中止；
- 任务开始前用保守上界做预算预检，避免"先超支再中止"；
- 日期字段必须是合法 YYYY-MM-DD，不能靠"非空字符串"蒙混。
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PRICES_PATH = BASE_DIR / "config" / "prices.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BudgetExceeded(RuntimeError):
    """预算或调用上限被突破。"""


class PaidProviderNotVerified(RuntimeError):
    """付费 provider 未获授权/未核验价格/usage 不完整。"""


def load_prices(path: str | Path | None = None) -> dict:
    price_path = Path(path) if path else DEFAULT_PRICES_PATH
    with open(price_path, encoding="utf-8") as handle:
        return json.load(handle)


def _is_valid_date(value: object) -> bool:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _valid_rate(value: object) -> bool:
    """费率必须是非负有限数；缺失/负数/NaN 一律视为无效。"""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return number >= 0 and number == number and number != float("inf")


def _rates_valid(provider: str, table: dict) -> bool:
    entry = table.get(provider) or {}
    if provider == "deepseek":
        deepseek_ok = _valid_rate(entry.get("input_per_million_cny")) and _valid_rate(entry.get("output_per_million_cny"))
        tavily_ok = _valid_rate((table.get("tavily") or {}).get("per_credit_cny"))
        return deepseek_ok and tavily_ok
    if provider == "tavily":
        return _valid_rate(entry.get("per_credit_cny"))
    return False


def _provider_status(table: dict, provider: str) -> str:
    entry = table.get(provider) or {}
    if not _rates_valid(provider, table):
        return "unauthorized"
    if _is_valid_date(table.get("verified_at")) and _is_valid_date(entry.get("verified_at")):
        return "official"
    consumed = table.get("authorization_consumed_at")
    if _is_valid_date(table.get("authorized_at")) and _is_valid_date(entry.get("authorized_at")) and not consumed:
        return "placeholder-authorized"
    return "unauthorized"


def price_status(provider: str, prices: dict | None = None) -> str:
    """返回 official / placeholder-authorized / unauthorized。

    DeepSeek 的价格完整性包含其实际会调用的 Tavily：若 Tavily 费率或授权/核验缺失，
    DeepSeek 也判为 unauthorized（避免把 Tavily 成本按 0 漏算）。
    """
    table = prices if prices is not None else load_prices()
    provider = (provider or "").lower()
    if not _rates_valid(provider, table):
        return "unauthorized"
    if provider != "deepseek":
        return _provider_status(table, provider)
    deepseek_status = _provider_status(table, "deepseek")
    tavily_status = _provider_status(table, "tavily")
    if "unauthorized" in (deepseek_status, tavily_status):
        return "unauthorized"
    if deepseek_status == "official" and tavily_status == "official":
        return "official"
    return "placeholder-authorized"


def ensure_paid_provider_allowed(provider: str, *, allow_paid: bool = False, prices: dict | None = None) -> str:
    """付费 provider 准入门槛；返回价格状态。"""
    provider = (provider or "").lower()
    if provider in ("", "ollama", "mock"):
        return "local"
    if not allow_paid:
        raise PaidProviderNotVerified(f"provider={provider} 属付费调用，必须显式 --allow-paid 且先获用户确认")
    status = price_status(provider, prices)
    if status == "unauthorized":
        raise PaidProviderNotVerified(
            f"provider={provider} 既无合法 authorized_at（用户授权）也无合法 verified_at（官方核验），拒绝付费调用"
        )
    return status


def require_paid_usage(provider: str, prompt_tokens: int | None, completion_tokens: int | None) -> None:
    """付费 provider 的 usage 必须完整；任一缺失即 fail-closed。"""
    if (provider or "").lower() in ("", "ollama", "mock"):
        return
    if prompt_tokens is None or completion_tokens is None:
        raise PaidProviderNotVerified(
            f"provider={provider} 的 usage 不完整（prompt={prompt_tokens}, completion={completion_tokens}），拒绝估算成本"
        )


def estimate_cost_cny(
    *,
    provider: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    tavily_calls: int = 0,
    prices: dict | None = None,
) -> float:
    """估算外部 API 成本（人民币）。本地 provider 只计 Tavily，不计本地推理。"""
    table = prices if prices is not None else load_prices()
    provider = (provider or "").lower()
    cost = 0.0
    if provider == "deepseek":
        cfg = table.get("deepseek", {})
        cost += (prompt_tokens or 0) / 1_000_000 * float(cfg.get("input_per_million_cny", 0))
        cost += (completion_tokens or 0) / 1_000_000 * float(cfg.get("output_per_million_cny", 0))
    tavily = table.get("tavily", {})
    cost += float(tavily_calls or 0) * float(tavily.get("per_credit_cny", 0))
    return round(cost, 4)


def estimate_task_upper_bound_cny(
    *,
    provider: str,
    max_tavily_calls: int,
    max_llm_calls: int = 15,
    max_tokens_per_call: int = 4096,
    max_prompt_tokens_per_call: int | None = None,
    prices: dict | None = None,
) -> float:
    """任务开始前的保守上界（用于预检，宁可保守拒绝，也不先超支）。

    - Tavily：按剩余调用上限 × 单价；
    - 付费 provider：把每次调用的输入/输出都按 max_tokens_per_call 计的极端上界。
    """
    table = prices if prices is not None else load_prices()
    provider = (provider or "").lower()
    upper = float(max_tavily_calls or 0) * float((table.get("tavily") or {}).get("per_credit_cny", 0))
    if provider == "deepseek":
        cfg = table.get("deepseek") or {}
        prompt_bound = max_prompt_tokens_per_call if max_prompt_tokens_per_call is not None else max_tokens_per_call
        per_call = (
            float(cfg.get("input_per_million_cny", 0)) * (prompt_bound / 1_000_000)
            + float(cfg.get("output_per_million_cny", 0)) * (max_tokens_per_call / 1_000_000)
        )
        upper += max_llm_calls * per_call
    return round(upper, 4)


def enforce_pre_task_budget(*, spent_cny: float, upper_bound_cny: float, max_cost_cny: float | None) -> None:
    """任务开始前预检：已花 + 本任务保守上界不得超过总上限。"""
    if max_cost_cny is not None and spent_cny + upper_bound_cny > max_cost_cny:
        raise BudgetExceeded(
            f"预检拒绝：已花 ¥{spent_cny} + 本任务保守上界 ¥{upper_bound_cny} 超过上限 ¥{max_cost_cny}"
        )


def enforce_budget(
    *,
    spent_cny: float,
    max_cost_cny: float | None,
    tavily_calls: int,
    max_tavily_calls: int | None,
) -> None:
    """任务完成后的复核（与预检配套）。"""
    if max_tavily_calls is not None and tavily_calls > max_tavily_calls:
        raise BudgetExceeded(f"Tavily 调用数 {tavily_calls} 超过上限 {max_tavily_calls}")
    if max_cost_cny is not None and spent_cny > max_cost_cny:
        raise BudgetExceeded(f"估算成本 ¥{spent_cny} 超过上限 ¥{max_cost_cny}")
