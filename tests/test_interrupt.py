"""B1：interrupt/resume（图级）测试。"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.searcher import SearchOutcome
from app.graph.research_graph import ResearchGraph
from app.graph.state import initial_state


class FakePlanner:
    def __init__(self):
        self.calls = 0

    def plan(self, topic):
        self.calls += 1
        return ["原始1", "原始2"]


class FakeSearcher:
    def __init__(self):
        self.received: list[str] = []

    def search(self, question):
        self.received.append(question)
        return SearchOutcome(question=question, documents=[{"title": "t", "content": "c", "url": "u"}], rounds=1)


class FakeAnalyzer:
    def analyze(self, question, results):
        return {"key_findings": ["f"], "credibility": "中", "contradictions": [], "summary": "s"}


class FakeWriter:
    def write(self, topic, analysis_results):
        return "# 初稿"

    def revise(self, topic, draft, feedback):
        return "# 修订稿"


class FakeReviewer:
    def review(self, topic, draft):
        return {"score": 9, "suggestions": [], "issues": []}


def _graph(planner, searcher, checkpointer):
    return ResearchGraph(
        planner=planner,
        searcher=searcher,
        analyzer=FakeAnalyzer(),
        writer=FakeWriter(),
        reviewer=FakeReviewer(),
    ).build(checkpointer=checkpointer, enable_human_review=True)


def test_interrupt_resume_adopts_edited_questions():
    planner = FakePlanner()
    searcher = FakeSearcher()
    graph = _graph(planner, searcher, InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    first = graph.invoke(initial_state("测试主题"), config)
    assert "__interrupt__" in first
    assert planner.calls == 1
    assert first["sub_questions"] == ["原始1", "原始2"]

    second = graph.invoke(Command(resume=["编辑A", "编辑B"]), config)
    assert second["status"] == "completed"
    assert searcher.received == ["编辑A", "编辑B"]
    assert planner.calls == 1  # 恢复不重跑 planner


def test_human_review_requires_checkpointer():
    with pytest.raises(ValueError):
        ResearchGraph().build(enable_human_review=True)


def test_resume_with_empty_edit_falls_back_to_proposed():
    planner = FakePlanner()
    searcher = FakeSearcher()
    graph = _graph(planner, searcher, InMemorySaver())
    config = {"configurable": {"thread_id": "t2"}}
    graph.invoke(initial_state("测试主题"), config)
    second = graph.invoke(Command(resume=[]), config)
    assert second["status"] == "completed"
    assert searcher.received == ["原始1", "原始2"]
