"""B4：SSE 事件流测试（顺序 / interrupt / 404）。"""

import asyncio

from fastapi.testclient import TestClient

from app.db.database import SessionLocal, init_db
from app.db.models import ResearchTask
from app.main import app
from app.services.memory_service import MemoryService
from app.services.task_service import TaskService


def _event_names(body: str) -> list[str]:
    names = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            if line.startswith("event:"):
                names.append(line.split(":", 1)[1].strip())
                break
    return names


def test_stream_404_for_missing_task():
    with TestClient(app) as client:
        assert client.get("/api/tasks/999999/stream").status_code == 404


def test_stream_event_order(monkeypatch):
    monkeypatch.setattr(MemoryService, "retrieve", lambda self, topic: [])
    monkeypatch.setattr(MemoryService, "save", lambda self, record: None)

    async def scenario():
        await init_db()
        task = await TaskService.create_task("B4 SSE 顺序")
        await TaskService.run_task(task.id)
        return task.id

    task_id = asyncio.run(scenario())
    with TestClient(app) as client:
        with client.stream("GET", f"/api/tasks/{task_id}/stream") as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())

    names = _event_names(body)
    assert names.index("status") < names.index("log") < names.index("node") < names.index("done")


def test_stream_emits_interrupt_when_paused():
    async def scenario():
        await init_db()
        task = await TaskService.create_task("B4 SSE interrupt")
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, task.id)
            row.status = "paused"
            row.sub_questions = ["编辑1", "编辑2"]
            await session.commit()
        return task.id

    task_id = asyncio.run(scenario())
    with TestClient(app) as client:
        with client.stream("GET", f"/api/tasks/{task_id}/stream") as response:
            body = "".join(response.iter_text())
    names = _event_names(body)
    assert "interrupt" in names
    assert names.index("status") < names.index("interrupt")
