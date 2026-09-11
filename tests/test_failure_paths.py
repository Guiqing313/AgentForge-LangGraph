"""A4：失败路径测试（搜索失败不编造、空分析如实降级）。"""

from app.agents.analyzer import AnalyzerAgent
from app.agents.base import BaseAgent
from app.agents.searcher import SearcherAgent, SearchOutcome
from app.agents.writer import WriterAgent


class _StubWebSearch:
    def search(self, query):
        raise RuntimeError("网络不可用")


def test_searcher_degrades_on_web_failure():
    agent = SearcherAgent(web_search=_StubWebSearch())
    docs, error = agent._try_web("任意查询")
    assert docs == []
    assert "网络不可用" in error


def test_empty_outcome_is_marked_as_no_result():
    outcome = SearchOutcome(question="q")
    assert outcome.as_text() == "（未检索到有效结果）"
    assert outcome.sources() == []


class _NoFabricationLLM:
    """模拟"看到无结果就如实返回空发现"的模型。"""

    def invoke(self, messages, **kwargs):
        text = "\n".join(getattr(m, "content", "") for m in messages)
        from app.llm.factory import _FakeMessage

        if "未检索到有效结果" in text:
            return _FakeMessage(
                '{"key_findings": [], "credibility": "低", "contradictions": [], '
                '"summary": "未检索到有效信息，无法进行可靠分析"}'
            )
        return _FakeMessage(
            '{"key_findings": ["发现"], "credibility": "中", "contradictions": [], "summary": "总结"}'
        )


def test_analyzer_returns_empty_findings_without_evidence(monkeypatch):
    monkeypatch.setattr("app.agents.base.get_llm", lambda: _NoFabricationLLM())
    result = AnalyzerAgent().analyze("无资料问题", ["（未检索到有效结果）"])
    assert result["key_findings"] == []
    assert result["credibility"] == "低"
    assert "未检索到有效信息" in result["summary"]


def test_writer_prompt_marks_missing_findings():
    prompt = WriterAgent._build_user_prompt(
        "主题",
        {"子问题": {"key_findings": [], "sources": [], "summary": "未检索到有效信息", "credibility": "低"}},
    )
    assert "（无）" in prompt
    assert "未检索到有效信息" in prompt


def test_base_agent_records_json_parse_failure(monkeypatch):
    from app import observability

    class _BadJsonLLM:
        def invoke(self, messages, **kwargs):
            from app.llm.factory import _FakeMessage

            return _FakeMessage("not-json-at-all")

    monkeypatch.setattr("app.agents.base.get_llm", lambda: _BadJsonLLM())
    with observability.track(task_id=1) as tracker:
        try:
            BaseAgent()._chat_json("s", "u")
        except ValueError:
            pass
    # 解析失败后会有一次严格重试，因此计 2 次失败
    assert tracker.snapshot()["json_parse_failures"] == 2


def test_tracker_propagates_to_search_threads():
    from app import observability
    from app.graph.research_graph import ResearchGraph

    class TrackerSearcher:
        def search(self, question):
            from app.agents.searcher import SearchOutcome

            tracker = observability.current_tracker()
            if tracker is not None:
                tracker.record_search(backend="tavily", query=question, ok=True, n_results=1)
            return SearchOutcome(question=question, documents=[{"title": "t", "content": "c", "url": "u"}], rounds=1)

    graph = ResearchGraph(searcher=TrackerSearcher())
    with observability.track(task_id=1) as tracker:
        graph._search_node({"sub_questions": ["a", "b"]})
    assert tracker.snapshot()["search_calls"] == 2


def test_chat_json_retries_once_on_parse_failure(monkeypatch):
    from app import observability
    from app.agents.base import BaseAgent
    from app.llm.factory import _FakeMessage

    class FlakyLLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return _FakeMessage("这不是 JSON")
            return _FakeMessage('{"ok": true}')

    flaky = FlakyLLM()
    monkeypatch.setattr("app.agents.base.get_llm", lambda: flaky)
    with observability.track(task_id=1) as tracker:
        result = BaseAgent()._chat_json("s", "u")
    assert result == {"ok": True}
    assert flaky.calls == 2
    assert tracker.snapshot()["json_parse_failures"] == 1


def test_reformulate_does_not_swallow_hard_stops(monkeypatch):
    """复测第五轮 P1：预算/付费硬停止必须从 _reformulate 穿透。"""
    import pytest

    from app.agents.searcher import SearcherAgent
    from app.cost import BudgetExceeded, PaidProviderNotVerified

    agent = SearcherAgent(web_search=_StubWebSearch())

    def budget_stop(system_prompt, user_prompt):
        raise BudgetExceeded("budget stop")

    monkeypatch.setattr(agent, "_chat_json", budget_stop)
    with pytest.raises(BudgetExceeded):
        agent._reformulate("q")

    def paid_stop(system_prompt, user_prompt):
        raise PaidProviderNotVerified("paid stop")

    monkeypatch.setattr(agent, "_chat_json", paid_stop)
    with pytest.raises(PaidProviderNotVerified):
        agent._reformulate("q")


def test_web_search_can_be_disabled(monkeypatch):
    """WEB_SEARCH_ENABLED=false 时不得发起网络搜索（演示/离线）。"""
    from dataclasses import replace

    import app.agents.searcher as searcher_module
    from app.agents.searcher import SearcherAgent, SearchOutcome

    called = {"web": 0, "local": 0}

    class _NeverWeb:
        def search(self, query):
            called["web"] += 1
            raise AssertionError("web search should be disabled")

    class _Local:
        def search(self, query):
            called["local"] += 1
            return [{"title": "local", "content": "本地资料", "url": ""}]

    # 替换模块级 settings：关闭网络搜索并强制 live 分支（绕过 mock 短路）
    monkeypatch.setattr(
        searcher_module,
        "settings",
        replace(searcher_module.settings, web_search_enabled=False, llm_mode="live"),
    )
    agent = SearcherAgent(web_search=_NeverWeb(), local_search=_Local())
    monkeypatch.setattr(agent, "plan_queries", lambda question: {"search_queries": ["q"], "prefer_local": True})
    outcome = agent.search("测试问题")
    assert isinstance(outcome, SearchOutcome)
    assert called["web"] == 0
    assert any("网络检索已禁用" in line for line in outcome.log)
