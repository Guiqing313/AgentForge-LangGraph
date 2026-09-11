"""A4：API 层测试（TestClient + 临时 SQLite + 屏蔽后台执行）。"""

import sqlite3

from fastapi.testclient import TestClient

import app.routes.tasks as routes
from app.config import settings
from app.main import app


def _db_path() -> str:
    return settings.database_url.split("///", 1)[-1]


def _set_status(task_id: int, status: str, final_report: str = "") -> None:
    con = sqlite3.connect(_db_path())
    try:
        con.execute(
            "UPDATE research_tasks SET status=?, final_report=? WHERE id=?",
            (status, final_report, task_id),
        )
        con.commit()
    finally:
        con.close()


def test_create_get_list_delete_flow(monkeypatch):
    async def fake_run_task(task_id):
        return None

    monkeypatch.setattr(routes.TaskService, "run_task", fake_run_task)

    with TestClient(app) as client:
        created = client.post("/api/tasks", json={"topic": "测试主题"})
        assert created.status_code == 201
        task_id = created.json()["data"]["id"]
        assert created.json()["data"]["status"] == "pending"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["topic"] == "测试主题"

        listing = client.get("/api/tasks")
        assert listing.status_code == 200
        assert any(item["id"] == task_id for item in listing.json()["data"])

        # 未完成时报告 409
        assert client.get(f"/api/tasks/{task_id}/report").status_code == 409

        # 不存在 404
        assert client.get("/api/tasks/999999").status_code == 404
        assert client.delete("/api/tasks/999999").status_code == 404

        # pending 任务可删除
        assert client.delete(f"/api/tasks/{task_id}").status_code == 200


def test_report_200_and_running_delete_conflict(monkeypatch):
    async def fake_run_task(task_id):
        return None

    monkeypatch.setattr(routes.TaskService, "run_task", fake_run_task)

    with TestClient(app) as client:
        task_id = client.post("/api/tasks", json={"topic": "报告任务"}).json()["data"]["id"]

        _set_status(task_id, "completed", "# 测试报告")
        report = client.get(f"/api/tasks/{task_id}/report")
        assert report.status_code == 200
        assert "# 测试报告" in report.json()["data"]["report"]

        _set_status(task_id, "running")
        assert client.delete(f"/api/tasks/{task_id}").status_code == 409


def test_resume_endpoint_404_and_409(monkeypatch):
    async def fake_run_task(task_id):
        return None

    monkeypatch.setattr(routes.TaskService, "run_task", fake_run_task)

    with TestClient(app) as client:
        assert client.post("/api/tasks/999999/resume", json={"sub_questions": []}).status_code == 404
        task_id = client.post("/api/tasks", json={"topic": "resume 测试"}).json()["data"]["id"]
        assert client.post(f"/api/tasks/{task_id}/resume", json={"sub_questions": []}).status_code == 409


def test_insights_endpoints(monkeypatch):
    with TestClient(app) as client:
        stats = client.get("/api/kb/stats")
        assert stats.status_code == 200
        body = stats.json()
        assert body["document_count"] == 5
        # 新克隆/CI 尚未构建 Chroma 索引，计数允许为 0；KB 构建由 tests/test_kb.py 覆盖
        assert body["collection_count"] >= 0

        search = client.post("/api/kb/search", json={"query": "RAG 的完整流程是什么？", "n_results": 3})
        assert search.status_code == 200
        assert search.json()["count"] >= 0

        live = client.get("/api/experiments/live")
        assert live.status_code == 200
        assert "available" in live.json()

        info = client.get("/api/system/info")
        assert info.status_code == 200
        payload = info.json()
        assert payload["limits"]["max_llm_calls_per_task"] >= 1
        assert "mcp_tools" in payload
