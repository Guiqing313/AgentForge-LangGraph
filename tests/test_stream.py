"""B4：SSE 事件流测试（不做断线续传）。"""

import asyncio

from fastapi.testclient import TestClient

from app.db.database import init_db
from app.main import app
from app.services.memory_service import MemoryService
from app.services.task_service import TaskService


def test_stream_404_for_missing_task():
    with TestClient(app) as client:
        assert client.get("/api/tasks/999999/stream").status_code == 404


def test_stream_emits_status_logs_nodes_and_done(monkeypatch):
    monkeypatch.setattr(MemoryService, "retrieve", lambda self, topic: [])
    monkeypatch.setattr(MemoryService, "save", lambda self, record: None)

    async def scenario():
        await init_db()
        task = await TaskService.create_task("B4 SSE 测试")
        await TaskService.run_task(task.id)
        return task.id

    task_id = asyncio.run(scenario())
    with TestClient(app) as client:
        with client.stream("GET", f"/api/tasks/{task_id}/stream") as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    assert "event: status" in body
    assert "event: log" in body
    assert "event: node" in body
    assert "event: done" in body
