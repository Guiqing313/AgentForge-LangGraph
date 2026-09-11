"""B3：任务指标（节点耗时 / token / 搜索 / 成本）测试。"""

import asyncio

from fastapi.testclient import TestClient

from app import observability
from app.agents.searcher import SearchOutcome
from app.config import settings
from app.db.database import init_db
from app.graph.research_graph import ResearchGraph
from app.graph.state import initial_state
from app.main import app
from app.services.task_service import TaskService


class _Planner:
    def plan(self, topic):
        return ["q1", "q2"]


class _Searcher:
    def search(self, question):
        return SearchOutcome(question=question, documents=[{"title": "t", "content": "c", "url": "u"}], rounds=1)


class _Analyzer:
    def analyze(self, question, results):
        return {"key_findings": ["f"], "credibility": "中", "contradictions": [], "summary": "s"}


class _Writer:
    def write(self, topic, analysis_results):
        return "# 报告"

    def revise(self, topic, draft, feedback):
        return "# 修订报告"


class _Reviewer:
    def review(self, topic, draft):
        return {"score": 9, "suggestions": [], "issues": []}


def test_graph_records_node_latencies():
    graph = ResearchGraph(
        planner=_Planner(), searcher=_Searcher(), analyzer=_Analyzer(), writer=_Writer(), reviewer=_Reviewer()
    ).build()
    with observability.track(task_id=1, provider="mock") as tracker:
        graph.invoke(initial_state("指标测试"))
    snapshot = tracker.snapshot()
    nodes = {item["node"] for item in snapshot["node_latencies"]}
    assert {"planner", "searcher", "analyzer", "writer", "reviewer", "finalize"} <= nodes
    assert all(item["latency_ms"] >= 0 for item in snapshot["node_latencies"])


def test_metrics_api_after_run(monkeypatch):
    from app.services.memory_service import MemoryService

    monkeypatch.setattr(MemoryService, "retrieve", lambda self, topic: [])
    monkeypatch.setattr(MemoryService, "save", lambda self, record: None)

    async def scenario():
        await init_db()
        task = await TaskService.create_task("B3 metrics api")
        await TaskService.run_task(task.id)
        return task.id

    task_id = asyncio.run(scenario())
    with TestClient(app) as client:
        response = client.get(f"/api/tasks/{task_id}/metrics")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["llm_calls"] >= 1
        assert data["node_latencies"]
        assert "estimated_cost_cny" in data

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["metrics"]["llm_calls"] >= 1

        assert client.get("/api/tasks/999999/metrics").status_code == 404
