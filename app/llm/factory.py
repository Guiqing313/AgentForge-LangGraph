"""LLM 工厂：统一创建 ollama / deepseek / mock 三种模式的模型实例。

- ollama（默认）：调用本地 Ollama 的 OpenAI 兼容接口，无 API 成本；
- deepseek：调用 DeepSeek 的 OpenAI 兼容接口（付费，仅用于 1 次对比实验）；
- mock：确定性输出，用于单元测试与无外部依赖时的离线流程验证。

三种模式暴露相同的 ``invoke(messages)`` 接口，上层 Agent 代码无需感知差异。
"""

from __future__ import annotations

from typing import Any, Iterable

from app.config import settings


class _FakeMessage:
    """模仿 LangChain AIMessage 的最小对象。"""

    def __init__(self, content: str) -> None:
        self.content = content


def _messages_to_text(messages: Iterable[Any]) -> str:
    """把消息列表拼成纯文本，供 mock 规则匹配使用。"""
    parts: list[str] = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):  # 多模态/分段内容，提取文本段
            for seg in content:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    parts.append(seg.get("text", ""))
                elif isinstance(seg, str):
                    parts.append(seg)
    return "\n".join(parts)


class MockLLM:
    """确定性 mock 模型。

    根据 prompt 中的关键字返回对应结构的 JSON 字符串，
    使集成测试能够验证「编排逻辑」本身，而非模型输出质量。

    可通过 ``responses`` 注入自定义关键字 -> 响应映射，便于测试特定分支。
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}

    def invoke(self, messages: Iterable[Any], **kwargs: Any) -> _FakeMessage:
        text = _messages_to_text(messages)
        for keyword, response in self.responses.items():
            if keyword in text:
                return _FakeMessage(response)
        return _FakeMessage(self._default_response(text))

    @staticmethod
    def _default_response(text: str) -> str:
        if "sub_questions" in text:
            return '{"sub_questions": ["背景与现状", "核心技术", "应用与落地", "挑战与趋势"]}'
        if "search_queries" in text:
            return '{"search_queries": ["相关关键词一", "相关关键词二"], "prefer_local": true}'
        if "key_findings" in text:
            return '{"key_findings": ["关键发现A", "关键发现B"], "credibility": "中", "contradictions": [], "summary": "离线模式下的模拟分析结果"}'
        if "score" in text and "suggestions" in text:
            return '{"score": 7, "suggestions": ["整体结构完整，可进一步补充数据支撑"], "issues": []}'
        if "报告" in text or "report" in text.lower():
            return "## 研究摘要\n\n离线模式生成的模拟研究报告。\n\n## 正文\n\n（mock 内容）\n\n## 结论\n\n（mock 结论）"
        return "{}"


def get_provider_name() -> str:
    """返回真实生效的 provider 名称（ollama / deepseek / mock）。"""
    return settings.effective_provider


def get_llm() -> Any:
    """根据配置返回 ollama / deepseek / mock 模型实例。"""
    provider = settings.effective_provider
    if provider == "mock":
        return MockLLM()

    from langchain_openai import ChatOpenAI

    if provider == "ollama":
        return ChatOpenAI(
            api_key="ollama",  # Ollama 不校验 key，但 OpenAI 客户端要求非空
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=60,
            max_retries=2,
        )

    # deepseek
    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=60,
        max_retries=2,
    )
