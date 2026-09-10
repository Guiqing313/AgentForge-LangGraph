"""任务服务：CRUD + 后台执行工作流 + 结果落库。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import ResearchTask
from app.graph.research_graph import ResearchGraph
from app.graph.state import initial_state
from app.services.memory_service import MemoryRecord, MemoryService

logger = logging.getLogger(__name__)


def _serialize_state(state: dict) -> dict:
    """把工作流最终状态转成可持久化的 JSON 字段。"""
    outcomes = state.get("search_outcomes", {})
    search_results = []
    for question, outcome in outcomes.items():
        search_results.append(
            {
                "question": question,
                "documents": outcome.documents,
                "rounds": outcome.rounds,
                "log": outcome.log,
            }
        )
    return {
        "sub_questions": state.get("sub_questions", []),
        "search_results": search_results,
        "analysis_results": state.get("analysis_results", {}),
        "draft_report": state.get("draft_report", ""),
        "final_report": state.get("final_report", ""),
        "review_history": state.get("review_history", []),
        "review_rounds": state.get("review_rounds", 0),
        "logs": state.get("log", []),
    }


class TaskService:
    """研究任务的创建、查询、删除与执行。"""

    @staticmethod
    async def create_task(topic: str) -> ResearchTask:
        topic = topic.strip()
        if not topic:
            raise ValueError("研究主题不能为空")
        async with SessionLocal() as session:
            task = ResearchTask(topic=topic, status="pending")
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    @staticmethod
    async def get_task(task_id: int) -> ResearchTask | None:
        async with SessionLocal() as session:
            return await session.get(ResearchTask, task_id)

    @staticmethod
    async def list_tasks(limit: int = 50, offset: int = 0) -> list[ResearchTask]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ResearchTask)
                .order_by(ResearchTask.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    @staticmethod
    async def delete_task(task_id: int) -> bool:
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if not task:
                return False
            await session.delete(task)
            await session.commit()
            return True

    @staticmethod
    async def run_task(task_id: int) -> ResearchTask:
        """执行完整工作流并把结果写回数据库。"""
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")
            task.status = "running"
            await session.commit()

        try:
            graph = ResearchGraph().build()
            memories: list[str] = []
            if settings.memory_enabled:
                try:
                    hits = MemoryService().retrieve(task.topic)
                    memories = [hit["document"] for hit in hits]
                    if memories:
                        logger.info("任务 %s 注入 %d 条历史记忆", task_id, len(memories))
                except Exception:  # noqa: BLE001 —— 记忆失败不阻塞主任务
                    logger.warning("记忆检索失败，降级为无记忆", exc_info=True)
            state = initial_state(task.topic, relevant_memories=memories)
            # 同步图在独立线程中执行，避免阻塞事件循环
            timeout = settings.task_soft_timeout_seconds
            if timeout and timeout > 0:
                try:
                    final_state = await asyncio.wait_for(
                        asyncio.to_thread(graph.invoke, state), timeout=timeout
                    )
                except asyncio.TimeoutError as exc:
                    # 软超时：只取消 await，工作流线程可能仍在收尾；结果不会写回。
                    raise RuntimeError(
                        f"任务软超时（{timeout}s）；后台线程可能仍在收尾，本次结果不写回。"
                    ) from exc
            else:
                final_state = await asyncio.to_thread(graph.invoke, state)
            serialized = _serialize_state(final_state)

            async with SessionLocal() as session:
                task = await session.get(ResearchTask, task_id)
                task.status = "completed"
                task.sub_questions = serialized["sub_questions"]
                task.search_results = serialized["search_results"]
                task.analysis_results = serialized["analysis_results"]
                task.draft_report = serialized["draft_report"]
                task.final_report = serialized["final_report"]
                task.review_history = serialized["review_history"]
                task.review_rounds = serialized["review_rounds"]
                task.logs = serialized["logs"]
                task.completed_at = datetime.now()
                await session.commit()
                await session.refresh(task)
            if settings.memory_enabled:
                try:
                    MemoryService().save(MemoryRecord.from_state(task.topic, task_id, serialized))
                except Exception:  # noqa: BLE001 —— 记忆失败不影响任务完成
                    logger.warning("记忆保存失败（不影响任务完成）", exc_info=True)
            return task
        except Exception as exc:  # noqa: BLE001
            logger.exception("任务 %s 执行失败", task_id)
            async with SessionLocal() as session:
                task = await session.get(ResearchTask, task_id)
                if task is None:
                    logger.warning("任务 %s 记录已不存在，跳过失败状态写回", task_id)
                else:
                    task.status = "failed"
                    task.error = str(exc)
                    await session.commit()
            raise
