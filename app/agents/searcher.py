"""搜索 Agent：受控 ReAct 循环（规划检索策略 -> 执行检索 -> 评估 -> 必要时重写查询）。

相比完全自由的 function-calling，这里采用「显式状态机」控制 ReAct 循环：
- Reasoning：LLM 规划查询词与检索偏好；
- Acting：执行本地知识库 / 网络搜索；
- Observation：统计结果数量与内容；
- 循环：结果不足时由 LLM 重写查询词，再搜一轮（上限 2 轮）。

真实性与可观测性要求：检索失败时必须如实记录，且不把错误信息当作
有效资料传给下游，避免分析/撰写 Agent 基于空结果产生幻觉。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.config import settings
from app.cost import BudgetExceeded, PaidProviderNotVerified
from app.observability import current_tracker
from app.tools.rag import LocalSearchTool
from app.tools.search import WebSearchTool

PLAN_PROMPT = """你是一名信息检索策略专家。给定一个子问题，请规划检索策略。

要求：
1. 给出 1-3 个高质量的检索关键词（search_queries），关键词应具体、有利于搜索引擎返回相关信息；
2. prefer_local：若该问题更适合先在本地知识库检索（如内部文档类问题）则为 true，否则 false。

只输出 JSON，不要输出解释文字。

输出格式：
{"search_queries": ["关键词1", "关键词2"], "prefer_local": false}
"""

REFORMULATE_PROMPT = """你是一名信息检索策略专家。首轮检索没有获得有效结果，请为下面的子问题重新设计 1-3 个不同的检索关键词。

只输出 JSON，不要输出解释文字。

输出格式：
{"search_queries": ["新关键词1", "新关键词2"]}
"""


@dataclass
class SearchOutcome:
    """一次搜索的结果与过程记录。"""

    question: str
    documents: list[dict] = field(default_factory=list)
    rounds: int = 0
    log: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        if not self.documents:
            return "（未检索到有效结果）"
        parts = []
        for i, doc in enumerate(self.documents, 1):
            parts.append(
                f"[资料{i}] 标题：{doc.get('title', '')}\n"
                f"来源：{doc.get('url', '')}\n"
                f"内容：{doc.get('content', '')}"
            )
        return "\n\n".join(parts)

    def sources(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for doc in self.documents:
            url = doc.get("url", "").strip()
            title = doc.get("title", "").strip()
            label = f"{title} ({url})" if url else title
            if label and label not in seen:
                seen.add(label)
                result.append(label)
        return result


class SearcherAgent(BaseAgent):
    """针对子问题执行受控 ReAct 检索。"""

    def __init__(self, web_search: WebSearchTool | None = None, local_search: LocalSearchTool | None = None) -> None:
        super().__init__()
        self.web_search = web_search or WebSearchTool()
        self.local_search = local_search or LocalSearchTool()

    def plan_queries(self, question: str) -> dict:
        result = self._chat_json(PLAN_PROMPT, f"子问题：{question}")
        queries = result.get("search_queries", []) if isinstance(result, dict) else []
        if not isinstance(queries, list) or not queries:
            queries = [question]
        return {
            "search_queries": [q for q in queries if isinstance(q, str)][:3],
            "prefer_local": bool(result.get("prefer_local", False)),
        }

    def search(self, question: str, max_rounds: int = 2) -> SearchOutcome:
        if settings.llm_mode == "mock":
            return SearchOutcome(
                question=question,
                documents=[
                    {
                        "title": "模拟资料（mock 模式）",
                        "content": "离线验证模式下的模拟检索结果，用于验证编排逻辑。",
                        "url": "mock://example",
                    }
                ],
                rounds=1,
                log=["mock 模式：跳过真实网络检索"],
            )

        outcome = SearchOutcome(question=question)
        plan = self.plan_queries(question)
        queries = plan["search_queries"]
        prefer_local = plan["prefer_local"]

        for round_idx in range(1, max_rounds + 1):
            round_docs: list[dict] = []
            for query in queries:
                if prefer_local:
                    docs, err = self._try_local(query)
                    round_docs.extend(docs)
                    note = f"（失败：{err}）" if err else ""
                    outcome.log.append(f"第{round_idx}轮 本地检索「{query}」→ {len(docs)} 条{note}")

                if settings.web_search_enabled:
                    docs, err = self._try_web(query)
                    round_docs.extend(docs)
                    note = f"（失败：{err}）" if err else ""
                    outcome.log.append(f"第{round_idx}轮 网络检索「{query}」→ {len(docs)} 条{note}")
                else:
                    outcome.log.append(f"第{round_idx}轮 网络检索已禁用（WEB_SEARCH_ENABLED=false）")

            outcome.documents = self._dedupe(outcome.documents + round_docs)
            outcome.rounds = round_idx

            if self._is_sufficient(outcome.documents):
                break

            if round_idx < max_rounds:
                queries = self._reformulate(question)
                if not queries:
                    break

        return outcome

    def _try_web(self, query: str) -> tuple[list[dict], str | None]:
        try:
            # 记录由 WebSearchTool 统一负责（含 cache/tavily/duckduckgo）
            return self.web_search.search(query), None
        except BudgetExceeded:
            raise  # 预算/上限属于硬停止，不得被降级吞掉
        except Exception as exc:  # noqa: BLE001
            return [], str(exc)

    def _try_local(self, query: str) -> tuple[list[dict], str | None]:
        try:
            docs = self.local_search.search(query)
            tracker = current_tracker()
            if tracker is not None:
                tracker.record_search(backend="local", query=query, ok=True, n_results=len(docs))
            return docs, None
        except Exception as exc:  # noqa: BLE001
            tracker = current_tracker()
            if tracker is not None:
                tracker.record_search(backend="local", query=query, ok=False, error=str(exc))
            return [], str(exc)

    @staticmethod
    def _is_sufficient(documents: list[dict]) -> bool:
        """轻量充分性规则：至少两条非空内容才视为充分，避免单条弱结果过早结束检索。"""
        valid = sum(1 for d in documents if str(d.get("content", "")).strip())
        return valid >= 2

    def _reformulate(self, question: str) -> list[str]:
        try:
            result = self._chat_json(REFORMULATE_PROMPT, f"子问题：{question}")
            queries = result.get("search_queries", []) if isinstance(result, dict) else []
            cleaned = [q for q in queries if isinstance(q, str) and q.strip()]
            return cleaned[:3]
        except (BudgetExceeded, PaidProviderNotVerified):
            raise  # 预算/付费校验属于硬停止，不得被降级为"无新查询"
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _dedupe(documents: list[dict]) -> list[dict]:
        seen: set[str] = set()
        result: list[dict] = []
        for doc in documents:
            key = (doc.get("url", "") or doc.get("title", "") or doc.get("content", ""))[:200]
            if key not in seen:
                seen.add(key)
                result.append(doc)
        return result
