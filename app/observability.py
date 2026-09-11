"""单任务预算与用量守卫（2026-09-11 全局收敛）。

设计原则（为什么这样改）：
- 之前"检查上限"和"记录调用"是两步，且分散在 BaseAgent / 搜索工具 / 脚本里，
  并发下会突破上限，且 TaskService 路径完全没接入；
- 现在收敛为唯一对象 UsageTracker：内部一把锁，调用前原子 reserve、调用后 record；
- 所有入口（TaskService 与 run_live_local）都通过 observability.track(...) 创建它；
- 价格表在使用前整体校验（见 app/cost.py），缺费率不会按 0 漏算。
"""

from __future__ import annotations

import contextvars
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from app.cost import (
    BudgetExceeded,
    ensure_paid_provider_allowed,
    estimate_cost_cny,
    load_prices,
    require_paid_usage,
)


@dataclass
class UsageTracker:
    """单任务用量 + 限额守卫（线程安全）。"""

    task_id: int | None = None
    provider: str = "mock"
    max_llm_calls: int | None = None
    max_tavily_calls: int | None = None
    max_cost_cny: float | None = None
    prices: dict | None = None
    started_at: float = field(default_factory=time.time)

    llm_calls: list[dict] = field(default_factory=list)
    search_calls: list[dict] = field(default_factory=list)
    node_latencies: list[dict] = field(default_factory=list)
    json_parse_failures: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _llm_reserved: int = 0
    _tavily_reserved: int = 0
    _llm_started: int = 0
    _tavily_started: int = 0

    # ---- 内部：仅在持锁时调用 ----
    def _price_table_locked(self) -> dict:
        return self.prices if self.prices is not None else load_prices()

    def _tavily_rate_locked(self) -> float:
        return float((self._price_table_locked().get("tavily") or {}).get("per_credit_cny", 0.0))

    def _worst_llm_cost_locked(self) -> float:
        if (self.provider or "").lower() != "deepseek":
            return 0.0
        from app.config import settings

        cfg = self._price_table_locked().get("deepseek") or {}
        prompt_bound = float(settings.max_prompt_chars_per_call)
        completion_bound = float(settings.llm_max_tokens)
        return (
            prompt_bound / 1_000_000 * float(cfg.get("input_per_million_cny", 0))
            + completion_bound / 1_000_000 * float(cfg.get("output_per_million_cny", 0))
        )

    def _estimated_cost_locked(self) -> float:
        prompt = sum(c["prompt_tokens"] or 0 for c in self.llm_calls)
        completion = sum(c["completion_tokens"] or 0 for c in self.llm_calls)
        tavily = sum(1 for c in self.search_calls if c.get("backend") == "tavily" and c.get("ok"))
        return estimate_cost_cny(
            provider=self.provider,
            prompt_tokens=prompt,
            completion_tokens=completion,
            tavily_calls=tavily,
            prices=self._price_table_locked(),
        )

    def _reserved_cost_locked(self) -> float:
        """在途预留的保守成本（并发下必须计入，否则多个线程可同时通过预算检查）。"""
        return self._llm_reserved * self._worst_llm_cost_locked() + self._tavily_reserved * self._tavily_rate_locked()

    # ---- LLM：原子预留 → 调用 → 记账/释放 ----
    def reserve_llm(self) -> None:
        with self._lock:
            if self.max_llm_calls is not None and self._llm_started >= self.max_llm_calls:
                raise BudgetExceeded(f"单任务 LLM 调用达到上限 {self.max_llm_calls}，中止以防超支")
            if self.max_cost_cny is not None:
                projected = self._estimated_cost_locked() + self._reserved_cost_locked() + self._worst_llm_cost_locked()
                if projected > self.max_cost_cny:
                    raise BudgetExceeded(
                        f"预算预检拒绝：已估算 ¥{self._estimated_cost_locked():.4f} + 在途预留 ¥{self._reserved_cost_locked():.4f} + 本次最坏 ¥{self._worst_llm_cost_locked():.4f} > 上限 ¥{self.max_cost_cny}"
                    )
            self._llm_reserved += 1
            self._llm_started += 1

    def record_llm(
        self,
        provider: str | None = None,
        latency_ms: float = 0.0,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        model: str | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> None:
        effective_provider = (provider or self.provider or "mock").lower()
        with self._lock:
            self._llm_reserved = max(0, self._llm_reserved - 1)
            if ok:
                require_paid_usage(effective_provider, prompt_tokens, completion_tokens)
            self.llm_calls.append(
                {
                    "provider": effective_provider,
                    "model": model,
                    "latency_ms": round(latency_ms, 1),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "ok": ok,
                    "error": error,
                }
            )

    def release_llm(self) -> None:
        with self._lock:
            self._llm_reserved = max(0, self._llm_reserved - 1)

    # ---- 外部搜索：只对 tavily（计费）预留 ----
    def reserve_search(self, backend: str) -> None:
        if (backend or "").lower() != "tavily":
            return
        with self._lock:
            if self.max_tavily_calls is not None and self._tavily_started >= self.max_tavily_calls:
                raise BudgetExceeded(f"单任务 Tavily 调用达到上限 {self.max_tavily_calls}，中止以防超支")
            if self.max_cost_cny is not None:
                projected = self._estimated_cost_locked() + self._reserved_cost_locked() + self._tavily_rate_locked()
                if projected > self.max_cost_cny:
                    raise BudgetExceeded(
                        f"预算预检拒绝：已估算 ¥{self._estimated_cost_locked():.4f} + 在途预留 ¥{self._reserved_cost_locked():.4f} + 本次 Tavily ¥{self._tavily_rate_locked():.4f} > 上限 ¥{self.max_cost_cny}"
                    )
            self._tavily_reserved += 1
            self._tavily_started += 1

    def record_search(self, backend: str, query: str, ok: bool, n_results: int = 0, error: str | None = None) -> None:
        with self._lock:
            if (backend or "").lower() == "tavily":
                self._tavily_reserved = max(0, self._tavily_reserved - 1)
            self.search_calls.append(
                {"backend": backend, "query": query[:200], "ok": ok, "n_results": n_results, "error": error}
            )

    def record_json_failure(self) -> None:
        with self._lock:
            self.json_parse_failures += 1

    def record_node(self, node: str, latency_ms: float) -> None:
        with self._lock:
            self.node_latencies.append({"node": node, "latency_ms": round(latency_ms, 1)})

    def snapshot(self) -> dict:
        with self._lock:
            prompt_tokens = [c["prompt_tokens"] for c in self.llm_calls if c["prompt_tokens"] is not None]
            completion_tokens = [c["completion_tokens"] for c in self.llm_calls if c["completion_tokens"] is not None]
            by_backend: dict[str, int] = {}
            for call in self.search_calls:
                by_backend[call["backend"]] = by_backend.get(call["backend"], 0) + 1
            return {
                "task_id": self.task_id,
                "provider": self.provider,
                "elapsed_seconds": round(time.time() - self.started_at, 2),
                "llm_calls": len(self.llm_calls),
                "llm_errors": sum(1 for c in self.llm_calls if not c["ok"]),
                "llm_reserved": self._llm_reserved,
                "llm_started": self._llm_started,
                "prompt_tokens": sum(prompt_tokens) if prompt_tokens else None,
                "completion_tokens": sum(completion_tokens) if completion_tokens else None,
                "search_calls": len(self.search_calls),
                "search_by_backend": by_backend,
                "tavily_reserved": self._tavily_reserved,
                "tavily_started": self._tavily_started,
                "estimated_cost_cny": self._estimated_cost_locked(),
                "json_parse_failures": self.json_parse_failures,
                "tavily_calls": by_backend.get("tavily", 0),
                "node_latencies": list(self.node_latencies),
                "details": {"llm": self.llm_calls, "search": self.search_calls},
            }


_current_tracker: contextvars.ContextVar[UsageTracker | None] = contextvars.ContextVar(
    "agentforge_usage_tracker", default=None
)


def current_tracker() -> UsageTracker | None:
    return _current_tracker.get()


@contextmanager
def track(
    task_id: int | None = None,
    *,
    provider: str = "mock",
    max_llm_calls: int | None = None,
    max_tavily_calls: int | None = None,
    max_cost_cny: float | None = None,
    prices: dict | None = None,
    allow_paid: bool = False,
) -> Iterator[UsageTracker]:
    """创建单任务守卫；付费 provider 若不允许会在进入时直接抛错。"""
    effective_provider = (provider or "mock").lower()
    if effective_provider not in ("mock", "ollama"):
        ensure_paid_provider_allowed(effective_provider, allow_paid=allow_paid, prices=prices)
    tracker = UsageTracker(
        task_id=task_id,
        provider=effective_provider,
        max_llm_calls=max_llm_calls,
        max_tavily_calls=max_tavily_calls,
        max_cost_cny=max_cost_cny,
        prices=prices,
    )
    token = _current_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _current_tracker.reset(token)
