"""单个 Agent 的 mock 模式测试。"""

from app.agents.analyzer import AnalyzerAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import ReviewerAgent


def test_planner_mock():
    agent = PlannerAgent()
    questions = agent.plan("测试主题")
    assert isinstance(questions, list) and len(questions) > 0


def test_analyzer_mock():
    agent = AnalyzerAgent()
    result = agent.analyze("测试问题", ["一些资料内容"])
    assert "key_findings" in result
    assert "summary" in result


def test_reviewer_mock():
    agent = ReviewerAgent()
    result = agent.review("测试主题", "# 测试报告")
    assert 1 <= result["score"] <= 10
    assert isinstance(result["suggestions"], list)
