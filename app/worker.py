"""单进程 worker（B2）。

设计（用户选择单进程方案）：
- FastAPI lifespan 内启动一个后台协程，轮询 pending 任务；
- claim 用原子 UPDATE + RETURNING，保证同一任务只被领取一次；
- 运行期间周期性更新 heartbeat_at；
- 启动时 recover_stale_tasks：把心跳过期的 running 任务恢复为 pending（超次数则 failed）；
- 取消为 best-effort：pending 直接 canceled；running 设置 cancel_requested，worker 在安全点（任务结束后）收敛。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import ResearchTask
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now()


async def claim_next_task(max_retries: int = 3) -> ResearchTask | None:
    """原子领取一个 pending 任务；无任务返回 None。"""
    for attempt in range(max_retries):
        try:
            async with SessionLocal() as session:
                subquery = (
                    select(ResearchTask.id)
                    .where(ResearchTask.status == "pending")
                    .order_by(ResearchTask.created_at)
                    .limit(1)
                    .scalar_subquery()
                )
                result = await session.execute(
                    update(ResearchTask)
                    .where(ResearchTask.id == subquery, ResearchTask.status == "pending")
                    .values(
                        status="running",
                        locked_at=_now(),
                        heartbeat_at=_now(),
                        attempts=(ResearchTask.attempts or 0) + 1,
                    )
                    .returning(ResearchTask.id)
                )
                claimed_id = result.scalar_one_or_none()
                await session.commit()
                if claimed_id is None:
                    return None
                return await session.get(ResearchTask, claimed_id)
        except OperationalError as exc:  # SQLite 并发写冲突：短暂退避后重试
            logger.warning("claim 冲突，重试 %s/%s：%s", attempt + 1, max_retries, exc)
            await asyncio.sleep(0.2)
    return None


async def recover_stale_tasks() -> int:
    """把心跳过期的 running 任务恢复为 pending（超过最大尝试次数则 failed）。"""
    cutoff = _now() - timedelta(seconds=settings.worker_stale_seconds)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ResearchTask).where(ResearchTask.status == "running"))).scalars().all()
        recovered = 0
        for task in rows:
            heartbeat = task.heartbeat_at or task.locked_at
            if heartbeat is not None and heartbeat > cutoff:
                continue
            if (task.attempts or 0) >= settings.worker_max_attempts:
                task.status = "failed"
                task.error = "worker stale：超过最大重试次数"
            else:
                task.status = "pending"
                task.locked_at = None
                task.heartbeat_at = None
            recovered += 1
        await session.commit()
    if recovered:
        logger.warning("恢复/终止 %d 个 stale 任务", recovered)
    return recovered


async def _heartbeat_loop(task_id: int) -> None:
    while True:
        await asyncio.sleep(settings.worker_heartbeat_interval)
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if task is None or task.status != "running":
                return
            task.heartbeat_at = _now()
            if task.cancel_requested:
                logger.info("任务 %s 收到取消请求（当前执行将在安全点收敛）", task_id)
            await session.commit()


async def _run_claimed(task_id: int) -> None:
    async with SessionLocal() as session:
        task = await session.get(ResearchTask, task_id)
        if task is None:
            return
        if task.cancel_requested:
            task.status = "canceled"
            task.locked_at = None
            await session.commit()
            return

    heartbeat = asyncio.create_task(_heartbeat_loop(task_id))
    try:
        if settings.human_review_enabled:
            await TaskService.run_task_with_review(task_id)
        else:
            await TaskService.run_task(task_id)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat

    async with SessionLocal() as session:
        task = await session.get(ResearchTask, task_id)
        if task is not None and task.cancel_requested and task.status == "completed":
            task.status = "canceled"
            task.error = "用户取消（任务在安全点收敛）"
            await session.commit()


async def worker_loop(stop_event: asyncio.Event) -> None:
    logger.info(
        "worker 启动：poll=%ss stale=%ss max_attempts=%s",
        settings.worker_poll_interval,
        settings.worker_stale_seconds,
        settings.worker_max_attempts,
    )
    while not stop_event.is_set():
        try:
            task = await claim_next_task()
            if task is None:
                await asyncio.sleep(settings.worker_poll_interval)
                continue
            await _run_claimed(task.id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 —— 单个任务失败不应杀死 worker
            logger.exception("worker 处理任务异常")
            await asyncio.sleep(1)
