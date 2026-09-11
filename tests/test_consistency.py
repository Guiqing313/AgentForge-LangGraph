"""A3：一致性修复测试（reviewer 分数、DELETE 语义、mock e2e、文档一致）。"""

import asyncio
import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.config import settings
from app.llm.factory import MockLLM

ROOT = Path(__file__).resolve().parent.parent


def test_reviewer_prompt_uses_configured_pass_score(monkeypatch):
    import app.agents.reviewer as reviewer

    monkeypatch.setattr(reviewer, "settings", replace(settings, review_pass_score=9))
    prompt = reviewer.system_prompt()
    assert "9 分及以上为合格" in prompt
    assert "8 分及以上为合格" not in prompt


def test_delete_running_task_returns_409(monkeypatch):
    import app.routes.tasks as routes

    class FakeTask:
        status = "running"

    async def fake_get_task(task_id):
        return FakeTask()

    async def fake_delete_task(task_id):
        return True

    monkeypatch.setattr(routes.TaskService, "get_task", fake_get_task)
    monkeypatch.setattr(routes.TaskService, "delete_task", fake_delete_task)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.delete_task(1))
    assert exc.value.status_code == 409


def test_delete_completed_task_allowed(monkeypatch):
    import app.routes.tasks as routes

    class FakeTask:
        status = "completed"

    async def fake_get_task(task_id):
        return FakeTask()

    async def fake_delete_task(task_id):
        return True

    monkeypatch.setattr(routes.TaskService, "get_task", fake_get_task)
    monkeypatch.setattr(routes.TaskService, "delete_task", fake_delete_task)
    result = asyncio.run(routes.delete_task(1))
    assert result["code"] == 200


def test_run_e2e_skips_live_validation_in_mock(monkeypatch):
    spec = importlib.util.spec_from_file_location("run_e2e", ROOT / "scripts" / "run_e2e.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "settings", replace(settings, llm_mode="mock"))
    assert module.needs_live_validation() is False


def test_soft_timeout_config_present():
    assert isinstance(settings.task_soft_timeout_seconds, int)
    assert settings.task_soft_timeout_seconds >= 0


def test_docs_match_real_graph_structure():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    graph = (ROOT / "app" / "graph" / "research_graph.py").read_text(encoding="utf-8")
    assert "仍有子问题" not in readme
    assert "每个子问题内部最多 2 轮" in readme
    assert "C --> C" not in readme
    assert "没有\"搜索节点回到自身\"的图级条件边" in graph


def test_mock_llm_still_works():
    llm = MockLLM()
    response = llm.invoke([type("M", (), {"content": '输出 {"sub_questions": []}'})()])
    assert "sub_questions" in response.content


def test_tests_use_isolated_database():
    # 复测 P2-2：conftest 强制覆盖 DATABASE_URL，测试不得连接真实库
    assert "agentforge_test_" in settings.database_url


def test_task_service_attaches_budget_guard(monkeypatch):
    """复测第三轮 P1-C：普通 TaskService 路径也必须接入同一套单任务守卫。"""
    import asyncio

    import app.services.task_service as svc
    from app import observability
    from app.cost import BudgetExceeded
    from app.db.database import init_db
    from app.services.memory_service import MemoryService

    class FakeGraph:
        def build(self):
            class _Graph:
                def invoke(self, state):
                    tracker = observability.current_tracker()
                    assert tracker is not None
                    assert tracker.max_llm_calls == settings.max_llm_calls_per_task
                    assert tracker.max_tavily_calls == settings.max_tavily_calls_per_task
                    raise BudgetExceeded("test budget stop")

            return _Graph()

    monkeypatch.setattr(svc, "ResearchGraph", FakeGraph)
    monkeypatch.setattr(MemoryService, "retrieve", lambda self, topic: [])
    monkeypatch.setattr(MemoryService, "save", lambda self, record: None)

    async def scenario():
        await init_db()
        task = await svc.TaskService.create_task("预算守卫测试")
        with pytest.raises(BudgetExceeded):
            await svc.TaskService.run_task(task.id)
        saved = await svc.TaskService.get_task(task.id)
        assert saved is not None
        assert saved.status == "failed"
        assert "test budget stop" in (saved.error or "")

    asyncio.run(scenario())
