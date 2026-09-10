"""按任务维度的用量与耗时追踪（A0 骨架，B3 扩展为 API/前端指标）。

通过 contextvars 让同一次任务内所有 Agent 调用都能写入同一个 tracker，
避免把 task_id / 用量逐层透传。未设置 tracker 时所有 record_* 都是 no-op，
因此对现有测试与调用方零影响。
"""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class UsageTracker:
    """一次研究任务的用量记录器。"""

    task_id: int | None = None
    started_at: float = field(default_factory=time.time)

    llm_calls: list[dict] = field(default_factory=list)
    search_calls: list[dict] = field(default_factory=list)
    json_parse_failures: int = 0

    def record_llm(
        self,
        provider: str,
        latency_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        model: str | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> None:
        self.llm_calls.append(
            {
                "provider": provider,
                "model": model,
                "latency_ms": round(latency_ms, 1),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "ok": ok,
                "error": error,
            }
        )

    def record_search(self, backend: str, query: str, ok: bool, n_results: int = 0, error: str | None = None) -> None:
        self.search_calls.append(
            {"backend": backend, "query": query[:200], "ok": ok, "n_results": n_results, "error": error}
        )

    def record_json_failure(self) -> None:
        self.json_parse_failures += 1

    def snapshot(self) -> dict:
        """汇总用量；token 缺失时保持 None（不得静默记 0）。"""
        prompt_tokens = [c["prompt_tokens"] for c in self.llm_calls if c["prompt_tokens"] is not None]
        completion_tokens = [c["completion_tokens"] for c in self.llm_calls if c["completion_tokens"] is not None]
        by_backend: dict[str, int] = {}
        for call in self.search_calls:
            by_backend[call["backend"]] = by_backend.get(call["backend"], 0) + 1
        return {
            "task_id": self.task_id,
            "elapsed_seconds": round(time.time() - self.started_at, 2),
            "llm_calls": len(self.llm_calls),
            "llm_errors": sum(1 for c in self.llm_calls if not c["ok"]),
            "prompt_tokens": sum(prompt_tokens) if prompt_tokens else None,
            "completion_tokens": sum(completion_tokens) if completion_tokens else None,
            "search_calls": len(self.search_calls),
            "search_by_backend": by_backend,
            "json_parse_failures": self.json_parse_failures,
            "details": {"llm": self.llm_calls, "search": self.search_calls},
        }


_current_tracker: contextvars.ContextVar[UsageTracker | None] = contextvars.ContextVar(
    "agentforge_usage_tracker", default=None
)


def current_tracker() -> UsageTracker | None:
    return _current_tracker.get()


@contextmanager
def track(task_id: int | None = None) -> Iterator[UsageTracker]:
    """在 with 块内启用 tracker，块结束后恢复之前的值。"""
    tracker = UsageTracker(task_id=task_id)
    token = _current_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _current_tracker.reset(token)