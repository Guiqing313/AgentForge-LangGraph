"""B2：并发 claim 竞态测试（两个 worker 只能有一个领取同一任务）。"""

import asyncio

from sqlalchemy import delete

from app.db.database import SessionLocal, init_db
from app.db.models import ResearchTask
from app.services.task_service import TaskService
from app.worker import claim_next_task


def test_two_concurrent_claims_only_one_wins():
    async def scenario():
        await init_db()
        async with SessionLocal() as session:
            await session.execute(delete(ResearchTask))
            await session.commit()
        task = await TaskService.create_task("race-单任务")
        results = await asyncio.gather(claim_next_task(), claim_next_task(), claim_next_task())
        claimed = [item for item in results if item is not None]
        assert len(claimed) == 1
        assert claimed[0].id == task.id

    asyncio.run(scenario())
