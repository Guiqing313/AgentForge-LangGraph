"""任务服务：CRUD + 后台执行工作流 + 结果落库 + interrupt/resume（B1）。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from sqlalchemy import select

from app import observability
from app.config import settings
from app.db.database import SessionLocal
from app.db.models import ResearchTask
from app.graph.research_graph import ResearchGraph
from app.graph.state import initial_state
from app.services.memory_service import MemoryRecord, MemoryService

logger = logging.getLogger(__name__)


def _serialize_state(state: dict) -> dict:
    """把工作流最终状态转成可持久化的 JSON 字段。"""
    outcomes = state.get("search_outcomes", {}) or {}
    search_results = []
    for question, outcome in outcomes.items():
        documents = getattr(outcome, "documents", None)
        if documents is None and isinstance(outcome, dict):
            documents = outcome.get("documents", [])
        rounds = getattr(outcome, "rounds", None)
        if rounds is None and isinstance(outcome, dict):
            rounds = outcome.get("rounds", 0)
        log = getattr(outcome, "log", None)
        if log is None and isinstance(outcome, dict):
            log = outcome.get("log", [])
        search_results.append(
            {"question": question, "documents": documents or [], "rounds": rounds or 0, "log": log or []}
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
    async def cancel_task(task_id: int) -> ResearchTask:
        """取消任务：pending/paused 直接 canceled；running 设置 cancel_requested（best-effort）。"""
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")
            if task.status in ("pending", "paused"):
                task.status = "canceled"
                task.cancel_requested = True
                task.locked_at = None
                task.heartbeat_at = None
                await session.commit()
                await session.refresh(task)
                return task
            if task.status == "running":
                task.cancel_requested = True
                await session.commit()
                await session.refresh(task)
                return task
            raise ValueError(f"任务状态为 {task.status}，无需取消")

    # ---- B1：interrupt/resume ----

    @staticmethod
    def _thread_config(task_id: int) -> dict:
        return {"configurable": {"thread_id": f"task-{task_id}"}}

    @staticmethod
    async def _mark_failed(task_id: int, exc: Exception) -> None:
        logger.exception("任务 %s 执行失败", task_id)
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if task is None:
                logger.warning("任务 %s 记录已不存在，跳过失败状态写回", task_id)
            else:
                task.status = "failed"
                task.error = str(exc)
                task.locked_at = None
                task.heartbeat_at = None
                await session.commit()

    @staticmethod
    async def _write_completed(task_id: int, serialized: dict, metrics: dict | None = None) -> ResearchTask:
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if task is None:
                raise ValueError(f"任务 {task_id} 不存在")
            task.status = "completed"
            task.sub_questions = serialized["sub_questions"]
            task.search_results = serialized["search_results"]
            task.analysis_results = serialized["analysis_results"]
            task.draft_report = serialized["draft_report"]
            task.final_report = serialized["final_report"]
            task.review_history = serialized["review_history"]
            task.review_rounds = serialized["review_rounds"]
            task.logs = serialized["logs"]
            task.metrics = metrics or {}
            task.completed_at = datetime.now()
            task.locked_at = None
            task.heartbeat_at = None
            await session.commit()
            await session.refresh(task)
        if settings.memory_enabled:
            try:
                MemoryService().save(MemoryRecord.from_state(task.topic, task_id, serialized))
            except Exception:  # noqa: BLE001 —— 记忆失败不影响任务完成
                logger.warning("记忆保存失败（不影响任务完成）", exc_info=True)
        return task

    @staticmethod
    async def _save_paused(task_id: int, state: dict) -> ResearchTask:
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if task is None:
                raise ValueError(f"任务 {task_id} 不存在")
            task.status = "paused"
            task.sub_questions = state.get("sub_questions") or []
            task.logs = state.get("log") or []
            task.locked_at = None
            task.heartbeat_at = None
            await session.commit()
            await session.refresh(task)
        return task

    @staticmethod
    def _collect_memories(topic: str) -> list[str]:
        memories: list[str] = []
        if settings.memory_enabled:
            try:
                hits = MemoryService().retrieve(topic)
                memories = [hit["document"] for hit in hits]
            except Exception:  # noqa: BLE001 —— 记忆失败不阻塞主任务
                logger.warning("记忆检索失败，降级为无记忆", exc_info=True)
        return memories

    @staticmethod
    async def run_task(task_id: int) -> ResearchTask:
        """执行完整工作流并把结果写回数据库（默认路径，无 interrupt）。"""
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")
            task.status = "running"
            await session.commit()
            topic = task.topic

        try:
            graph = ResearchGraph().build()
            state = initial_state(topic, relevant_memories=TaskService._collect_memories(topic))
            provider = settings.effective_provider
            with observability.track(
                task_id=task_id,
                provider=provider,
                max_llm_calls=settings.max_llm_calls_per_task,
                max_tavily_calls=settings.max_tavily_calls_per_task,
                max_cost_cny=settings.max_cost_cny_per_task,
                allow_paid=settings.allow_paid_provider,
            ) as tracker:
                timeout = settings.task_soft_timeout_seconds
                if timeout and timeout > 0:
                    try:
                        final_state = await asyncio.wait_for(
                            asyncio.to_thread(graph.invoke, state), timeout=timeout
                        )
                    except asyncio.TimeoutError as exc:
                        raise RuntimeError(
                            f"任务软超时（{timeout}s）；后台线程可能仍在收尾，本次结果不写回。"
                        ) from exc
                else:
                    final_state = await asyncio.to_thread(graph.invoke, state)
            return await TaskService._write_completed(task_id, _serialize_state(final_state), tracker.snapshot())
        except Exception as exc:  # noqa: BLE001
            await TaskService._mark_failed(task_id, exc)
            raise

    @staticmethod
    async def run_task_with_review(task_id: int) -> ResearchTask:
        """HUMAN_REVIEW_ENABLED=true 时的执行路径：planner 后暂停等待用户确认。"""
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")
            task.status = "running"
            await session.commit()
            topic = task.topic

        try:
            async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db) as saver:
                graph = ResearchGraph().build(checkpointer=saver, enable_human_review=True)
                state = initial_state(topic, relevant_memories=TaskService._collect_memories(topic))
                with observability.track(
                    task_id=task_id,
                    provider=settings.effective_provider,
                    max_llm_calls=settings.max_llm_calls_per_task,
                    max_tavily_calls=settings.max_tavily_calls_per_task,
                    max_cost_cny=settings.max_cost_cny_per_task,
                    allow_paid=settings.allow_paid_provider,
                ) as tracker:
                    result = await graph.ainvoke(state, config=TaskService._thread_config(task_id))
            if "__interrupt__" in result:
                return await TaskService._save_paused(task_id, result)
            return await TaskService._write_completed(task_id, _serialize_state(result), tracker.snapshot())
        except Exception as exc:  # noqa: BLE001
            await TaskService._mark_failed(task_id, exc)
            raise

    @staticmethod
    async def resume_task(task_id: int, sub_questions: list[str]) -> ResearchTask:
        """恢复被 interrupt 暂停的任务，并采用用户编辑后的子问题。"""
        async with SessionLocal() as session:
            task = await session.get(ResearchTask, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")
            if task.status != "paused":
                raise ValueError(f"任务当前状态为 {task.status}，只有 paused 状态可以恢复")
            task.status = "running"
            await session.commit()

        try:
            async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db) as saver:
                graph = ResearchGraph().build(checkpointer=saver, enable_human_review=True)
                with observability.track(
                    task_id=task_id,
                    provider=settings.effective_provider,
                    max_llm_calls=settings.max_llm_calls_per_task,
                    max_tavily_calls=settings.max_tavily_calls_per_task,
                    max_cost_cny=settings.max_cost_cny_per_task,
                    allow_paid=settings.allow_paid_provider,
                ) as tracker:
                    result = await graph.ainvoke(
                        Command(resume=sub_questions), config=TaskService._thread_config(task_id)
                    )
            return await TaskService._write_completed(task_id, _serialize_state(result), tracker.snapshot())
        except Exception as exc:  # noqa: BLE001
            await TaskService._mark_failed(task_id, exc)
            raise
