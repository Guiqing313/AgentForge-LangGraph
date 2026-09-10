"""Agent 基类：封装 LLM 调用与稳健的 JSON 解析。

所有 Agent 共享两个能力：
1. ``_chat``     —— 纯文本对话（同时向 UsageTracker 记录耗时/用量）；
2. ``_chat_json``—— 要求模型返回 JSON 并从输出中稳健提取。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.config import settings
from app.llm.factory import get_llm
from app.observability import current_tracker


class SimpleMessage:
    """未安装 langchain 时的最小消息对象（鸭子类型兼容）。"""

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def _make_message(role: str, content: str) -> Any:
    """优先使用 langchain 消息；不可用时退回 SimpleMessage。"""
    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        cls = {"system": SystemMessage, "human": HumanMessage, "ai": AIMessage}.get(
            role, HumanMessage
        )
        return cls(content=content)
    except ImportError:
        return SimpleMessage(role, content)


def extract_json(text: str) -> Any:
    """从模型输出中稳健地提取 JSON。

    模型常常把 JSON 包在 ```json ... ``` 代码块里，或在前后附加解释文字。
    这里依次尝试：整体解析 -> 代码块提取 -> 首个平衡花括号块提取。
    """
    if not isinstance(text, str):
        raise ValueError(f"模型输出不是字符串：{type(text)!r}")

    text = text.strip()

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])

    raise ValueError(f"无法从模型输出中解析 JSON，前 200 字符：{text[:200]!r}")


class BaseAgent:
    """所有 Agent 的基类。"""

    def __init__(self) -> None:
        self.llm = get_llm()

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        tracker = current_tracker()
        start = time.perf_counter()
        try:
            response = self.llm.invoke(
                [
                    _make_message("system", system_prompt),
                    _make_message("human", user_prompt),
                ]
            )
        except Exception as exc:  # noqa: BLE001 —— 记录失败后向上抛出，保持原语义
            if tracker is not None:
                tracker.record_llm(
                    provider=settings.effective_provider,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    model=self._model_name(),
                    ok=False,
                    error=str(exc),
                )
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        if tracker is not None:
            usage = getattr(response, "usage_metadata", None) or {}
            tracker.record_llm(
                provider=settings.effective_provider,
                latency_ms=latency_ms,
                prompt_tokens=usage.get("input_tokens"),
                completion_tokens=usage.get("output_tokens"),
                model=self._model_name(),
            )
        return response.content

    def _chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        raw = self._chat(system_prompt, user_prompt)
        try:
            return extract_json(raw)
        except Exception:
            tracker = current_tracker()
            if tracker is not None:
                tracker.record_json_failure()
            raise

    def _model_name(self) -> str:
        if settings.effective_provider == "ollama":
            return settings.ollama_model
        if settings.effective_provider == "deepseek":
            return settings.deepseek_model
        return "mock"