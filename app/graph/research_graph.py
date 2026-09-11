"""AgentForge 研究协作工作流图。

工作流（以实现为准）：
  START -> planner -> searcher -> analyzer -> writer -> reviewer
  - searcher 是单个节点：对全部子问题并行执行；每个子问题内部最多 2 轮（不足则改写查询词）。
    （没有"搜索节点回到自身"的图级条件边——该循环在 SearcherAgent.search 内部。）
  - reviewer 后条件边：合格或超过 max_review_rounds -> finalize；否则回 writer 修订。
"""

from __future__ import annotations

import contextvars
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.analyzer import AnalyzerAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.searcher import SearcherAgent, SearchOutcome
from app.agents.writer import WriterAgent
from app.config import settings
from app.cost import BudgetExceeded
from app.graph.state import ResearchState


class ResearchGraph:
    """封装工作流图的构建，支持注入 Agent 以便测试。"""

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        searcher: SearcherAgent | None = None,
        analyzer: AnalyzerAgent | None = None,
        writer: WriterAgent | None = None,
        reviewer: ReviewerAgent | None = None,
    ) -> None:
        self.planner = planner or PlannerAgent()
        self.searcher = searcher or SearcherAgent()
        self.analyzer = analyzer or AnalyzerAgent()
        self.writer = writer or WriterAgent()
        self.reviewer = reviewer or ReviewerAgent()

    # ---- 节点函数 ----

    def _plan_node(self, state: ResearchState) -> dict:
        topic = state["topic"]
        memories = state.get("relevant_memories") or []
        # 仅在确有记忆时传第二参数，保持与只接受 topic 的 FakePlanner 兼容
        sub_questions = self.planner.plan(topic, memories) if memories else self.planner.plan(topic)
        return {
            "sub_questions": sub_questions,
            "current_question_index": 0,
            "status": "searching",
            "log": [
                f"规划完成：分解为 {len(sub_questions)} 个子问题"
                + (f"（注入 {len(memories)} 条历史记忆）" if memories else "")
            ],
        }

    def _search_node(self, state: ResearchState) -> dict:
        """并行搜索所有子问题（受控线程池），显著缩短搜索阶段耗时。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        questions = state["sub_questions"]
        outcomes: dict[str, SearchOutcome] = {}
        logs: list[str] = []

        max_workers = min(len(questions) or 1, 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 复制当前 context（含 UsageTracker），否则子线程里 current_tracker() 为 None
            future_map = {}
            for question in questions:
                ctx = contextvars.copy_context()
                future_map[executor.submit(ctx.run, self.searcher.search, question)] = question
            for future in as_completed(future_map):
                question = future_map[future]
                try:
                    outcome = future.result()
                except BudgetExceeded:
                    raise  # 硬停止：预算/调用上限不得被降级为"搜索失败"
                except Exception as exc:  # noqa: BLE001
                    outcome = SearchOutcome(
                        question=question,
                        documents=[],
                        rounds=0,
                        log=[f"搜索失败：{exc}"],
                    )
                outcomes[question] = outcome
                logs.append(f"搜索完成「{question}」：{len(outcome.documents)} 条资料，{outcome.rounds} 轮")

        return {
            "search_outcomes": outcomes,
            "status": "analyzing",
            "log": logs,
        }

    def _analyze_node(self, state: ResearchState) -> dict:
        outcomes = state.get("search_outcomes", {})
        analysis_results: dict[str, Any] = {}
        logs: list[str] = []
        for question, outcome in outcomes.items():
            analysis = self.analyzer.analyze(question, [outcome.as_text()])
            analysis["sources"] = outcome.sources()
            analysis_results[question] = analysis
            logs.append(f"分析完成「{question}」：{len(analysis.get('key_findings', []))} 条关键发现")
        return {"analysis_results": analysis_results, "status": "writing", "log": logs}

    def _write_node(self, state: ResearchState) -> dict:
        topic = state["topic"]
        analysis_results = state.get("analysis_results", {})
        feedback = state.get("review_feedback", "")
        draft = state.get("draft_report", "")

        if feedback and draft:
            report = self.writer.revise(topic, draft, feedback)
            return {"draft_report": report, "status": "reviewing", "log": ["已根据审核意见修订报告"]}
        report = self.writer.write(topic, analysis_results)
        return {"draft_report": report, "status": "reviewing", "log": ["报告初稿完成"]}

    def _review_node(self, state: ResearchState) -> dict:
        topic = state["topic"]
        draft = state["draft_report"]
        result = self.reviewer.review(topic, draft)

        review_rounds = state.get("review_rounds", 0) + 1
        review_entry = {
            "round": review_rounds,
            "score": result["score"],
            "suggestions": result["suggestions"],
            "issues": result["issues"],
        }
        feedback = "\n".join(result.get("suggestions", []))
        return {
            "review_rounds": review_rounds,
            "review_feedback": feedback,
            "review_history": [review_entry],
            "log": [f"第{review_rounds}轮审核：{result['score']} 分"],
        }

    def _human_review_node(self, state: ResearchState) -> dict:
        """planner 后暂停，等待用户确认/编辑子问题（需要 checkpointer）。"""
        proposed = list(state.get("sub_questions") or [])
        edited = interrupt({"sub_questions": proposed, "message": "请确认或编辑子问题后继续"})
        if isinstance(edited, dict):
            edited = edited.get("sub_questions")
        questions: list[str] = []
        seen: set[str] = set()
        for question in edited or []:
            if isinstance(question, str) and question.strip() and question.strip() not in seen:
                seen.add(question.strip())
                questions.append(question.strip())
        if not questions:
            questions = proposed
        return {
            "sub_questions": questions,
            "current_question_index": 0,
            "status": "searching",
            "log": [f"人工确认：{len(questions)} 个子问题"],
        }

    @staticmethod
    def _route_after_review(state: ResearchState) -> str:
        rounds = state.get("review_rounds", 0)
        history = state.get("review_history", [])
        last_score = history[-1]["score"] if history else 0

        if last_score >= settings.review_pass_score or rounds >= settings.max_review_rounds:
            return "finalize"
        return "revise"

    def _finalize_node(self, state: ResearchState) -> dict:
        return {"final_report": state["draft_report"], "status": "completed"}

    def build(self, checkpointer=None, enable_human_review: bool = False):
        """构建并编译 LangGraph 工作流图。

        enable_human_review=True 时在 planner 后插入 human_review（interrupt），
        必须提供 checkpointer；默认 False 保持既有行为不变。
        """
        if enable_human_review and checkpointer is None:
            raise ValueError("enable_human_review=True 需要提供 checkpointer")
        graph = StateGraph(ResearchState)
        graph.add_node("planner", self._plan_node)
        graph.add_node("searcher", self._search_node)
        graph.add_node("analyzer", self._analyze_node)
        graph.add_node("writer", self._write_node)
        graph.add_node("reviewer", self._review_node)
        graph.add_node("finalize", self._finalize_node)

        graph.add_edge(START, "planner")
        if enable_human_review:
            graph.add_node("human_review", self._human_review_node)
            graph.add_edge("planner", "human_review")
            graph.add_edge("human_review", "searcher")
        else:
            graph.add_edge("planner", "searcher")
        graph.add_edge("searcher", "analyzer")
        graph.add_edge("analyzer", "writer")
        graph.add_edge("writer", "reviewer")
        graph.add_conditional_edges(
            "reviewer",
            self._route_after_review,
            {"revise": "writer", "finalize": "finalize"},
        )
        graph.add_edge("finalize", END)

        return graph.compile(checkpointer=checkpointer)
