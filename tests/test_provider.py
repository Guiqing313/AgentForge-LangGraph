"""A0：provider 选择与 UsageTracker 测试（全部离线，不产生真实调用）。"""

from dataclasses import replace

from app import observability
from app.agents.planner import PlannerAgent
from app.config import settings
from app.llm import factory
from app.llm.factory import MockLLM, get_llm, get_provider_name


def _fake_settings(**overrides):
    return replace(settings, **overrides)


def test_mock_mode_forces_mock(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings(llm_mode="mock", llm_provider="ollama"))
    assert get_provider_name() == "mock"
    assert isinstance(get_llm(), MockLLM)


def test_default_ollama_provider(monkeypatch):
    monkeypatch.setattr(factory, "settings", _fake_settings(llm_mode="live", llm_provider="ollama"))
    assert get_provider_name() == "ollama"
    llm = get_llm()
    assert type(llm).__name__ == "ChatOpenAI"


def test_deepseek_without_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(
        factory,
        "settings",
        _fake_settings(llm_mode="live", llm_provider="deepseek", deepseek_api_key=""),
    )
    assert get_provider_name() == "mock"
    assert isinstance(get_llm(), MockLLM)


def test_usage_tracker_snapshot():
    with observability.track(task_id=7) as tracker:
        tracker.record_llm(provider="ollama", latency_ms=12.34, prompt_tokens=10, completion_tokens=5)
        tracker.record_search(backend="tavily", query="q", ok=True, n_results=3)
        tracker.record_json_failure()
    snap = tracker.snapshot()
    assert snap["task_id"] == 7
    assert snap["llm_calls"] == 1
    assert snap["prompt_tokens"] == 10
    assert snap["completion_tokens"] == 5
    assert snap["search_by_backend"] == {"tavily": 1}
    assert snap["json_parse_failures"] == 1


def test_tracker_none_outside_context():
    assert observability.current_tracker() is None


def test_base_agent_records_llm_call():
    with observability.track(task_id=1) as tracker:
        PlannerAgent().plan("测试主题")
    snap = tracker.snapshot()
    assert snap["llm_calls"] == 1
    assert snap["details"]["llm"][0]["provider"] == "mock"
    assert snap["details"]["llm"][0]["ok"] is True
