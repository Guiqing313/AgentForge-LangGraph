"""B2：worker 领取 / stale 恢复 / 取消 测试。"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.db.database import SessionLocal, init_db
from app.db.models import ResearchTask
from app.services.task_service import TaskService
from app.worker import claim_next_task, recover_stale_tasks


def test_claim_next_task_is_exclusive():
    async def scenario():
        await init_db()
        async with SessionLocal() as session:
            await session.execute(delete(ResearchTask))
            await session.commit()
        task = await TaskService.create_task("claim-唯一任务")
        first, second = await asyncio.gather(claim_next_task(), claim_next_task())
        claimed = [item for item in (first, second) if item is not None]
        assert len(claimed) == 1
        assert claimed[0].id == task.id
        assert await claim_next_task() is None
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, task.id)
            assert row.status == "running"
            assert row.attempts == 1
            assert row.locked_at is not None
            assert row.heartbeat_at is not None

    asyncio.run(scenario())


def test_recover_stale_tasks_resets_then_fails():
    async def scenario():
        await init_db()
        async with SessionLocal() as session:
            await session.execute(delete(ResearchTask))
            await session.commit()
        fresh = await TaskService.create_task("stale-恢复")
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, fresh.id)
            row.status = "running"
            row.attempts = 1
            old = datetime.now() - timedelta(seconds=9999)
            row.locked_at = old
            row.heartbeat_at = old
            await session.commit()

        await recover_stale_tasks()
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, fresh.id)
            assert row.status == "pending"
            assert row.locked_at is None

        dead = await TaskService.create_task("stale-超次数")
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, dead.id)
            row.status = "running"
            row.attempts = 99
            old = datetime.now() - timedelta(seconds=9999)
            row.locked_at = old
            row.heartbeat_at = old
            await session.commit()

        await recover_stale_tasks()
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, dead.id)
            assert row.status == "failed"
            assert "stale" in (row.error or "")

    asyncio.run(scenario())


def test_cancel_task_pending_and_running():
    async def scenario():
        await init_db()
        async with SessionLocal() as session:
            await session.execute(delete(ResearchTask))
            await session.commit()
        pending = await TaskService.create_task("cancel-pending")
        updated = await TaskService.cancel_task(pending.id)
        assert updated.status == "canceled"

        running = await TaskService.create_task("cancel-running")
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, running.id)
            row.status = "running"
            await session.commit()
        updated_running = await TaskService.cancel_task(running.id)
        assert updated_running.cancel_requested is True

    asyncio.run(scenario())


def test_completed_task_clears_lock_and_heartbeat(monkeypatch):
    """修复 A：完成/失败后不得残留 locked_at / heartbeat_at。"""
    async def scenario():
        await init_db()
        async with SessionLocal() as session:
            await session.execute(delete(ResearchTask))
            await session.commit()
        task = await TaskService.create_task("lock-clean")
        claimed = await claim_next_task()
        assert claimed is not None and claimed.locked_at is not None

        from app.services.memory_service import MemoryService

        monkeypatch.setattr(MemoryService, "save", lambda self, record: None)
        serialized = {
            "sub_questions": ["q"],
            "search_results": [],
            "analysis_results": {},
            "draft_report": "",
            "final_report": "# 报告",
            "review_history": [],
            "review_rounds": 0,
            "logs": [],
        }
        await TaskService._write_completed(task.id, serialized)
        async with SessionLocal() as session:
            row = await session.get(ResearchTask, task.id)
            assert row.status == "completed"
            assert row.locked_at is None
            assert row.heartbeat_at is None

    asyncio.run(scenario())
