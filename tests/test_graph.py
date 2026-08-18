"""LangGraph 工作流的集成测试（注入 fake Agent，离线验证编排逻辑）。"""

from app.agents.searcher import SearchOutcome
from app.graph.research_graph import ResearchGraph
from app.graph.state import initial_state


class FakePlanner:
    def plan(self, topic):
        return ["子问题A", "子问题B"]


class FakeSearcher:
    def search(self, question):
        return SearchOutcome(
            question=question,
            documents=[{"title": "资料", "content": "示例内容", "url": "https://example.com"}],
            rounds=1,
            log=[f"搜索 {question}"],
        )


class FakeAnalyzer:
    def analyze(self, question, results):
        return {
            "key_findings": ["发现"],
            "credibility": "中",
            "contradictions": [],
            "summary": "总结",
        }


class FakeWriter:
    def __init__(self):
        self.write_calls = 0
        self.revise_calls = 0

    def write(self, topic, analysis_results):
        self.write_calls += 1
        return "# 初稿"

    def revise(self, topic, draft, feedback):
        self.revise_calls += 1
        return "# 修订稿"


class FakeReviewer:
    def __init__(self, scores):
        self.scores = list(scores)
        self.calls = 0

    def review(self, topic, draft):
        score = self.scores[min(self.calls, len(self.scores) - 1)]
        self.calls += 1
        return {"score": score, "suggestions": ["建议"], "issues": []}


def test_full_flow_single_pass():
    writer = FakeWriter()
    reviewer = FakeReviewer([8])
    graph = ResearchGraph(
        planner=FakePlanner(),
        searcher=FakeSearcher(),
        analyzer=FakeAnalyzer(),
        writer=writer,
        reviewer=reviewer,
    ).build()

    result = graph.invoke(initial_state("测试主题"))

    assert result["status"] == "completed"
    assert result["final_report"] == "# 初稿"
    assert len(result["search_outcomes"]) == 2
    assert writer.write_calls == 1
    assert writer.revise_calls == 0
    assert reviewer.calls == 1


def test_review_loop_revises_then_passes():
    writer = FakeWriter()
    # 第一次审核 5 分（不合格），第二次 9 分（合格）
    reviewer = FakeReviewer([5, 9])
    graph = ResearchGraph(
        planner=FakePlanner(),
        searcher=FakeSearcher(),
        analyzer=FakeAnalyzer(),
        writer=writer,
        reviewer=reviewer,
    ).build()

    result = graph.invoke(initial_state("测试主题"))

    assert result["status"] == "completed"
    assert writer.write_calls == 1
    assert writer.revise_calls == 1
    assert reviewer.calls == 2
    assert result["final_report"] == "# 修订稿"


def test_review_loop_hits_max_rounds():
    writer = FakeWriter()
    # 永远 5 分，验证达到 max_review_rounds 后强制结束，不会死循环
    reviewer = FakeReviewer([5])
    graph = ResearchGraph(
        planner=FakePlanner(),
        searcher=FakeSearcher(),
        analyzer=FakeAnalyzer(),
        writer=writer,
        reviewer=reviewer,
    ).build()

    result = graph.invoke(initial_state("测试主题"))

    assert result["status"] == "completed"
    assert writer.revise_calls == 1  # max_review_rounds=2：一次初稿 + 一次修订
    assert reviewer.calls == 2