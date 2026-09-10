"""研究任务相关 API。"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# 保存后台任务引用，防止被垃圾回收而中断
_background_tasks: set[asyncio.Task] = set()


class TaskCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="研究主题")


def _task_to_dict(task: Any) -> dict:
    return {
        "id": task.id,
        "topic": task.topic,
        "status": task.status,
        "sub_questions": task.sub_questions or [],
        "review_rounds": task.review_rounds or 0,
        "logs": task.logs or [],
        "error": task.error or "",
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _task_detail(task: Any) -> dict:
    data = _task_to_dict(task)
    data.update(
        {
            "analysis_results": task.analysis_results or {},
            "draft_report": task.draft_report or "",
            "final_report": task.final_report or "",
            "review_history": task.review_history or [],
        }
    )
    return data


@router.post("", status_code=201)
async def create_task(payload: TaskCreate) -> dict:
    task = await TaskService.create_task(payload.topic)
    bg = asyncio.create_task(TaskService.run_task(task.id))
    _background_tasks.add(bg)
    bg.add_done_callback(_background_tasks.discard)
    return {"code": 200, "message": "success", "data": _task_to_dict(task)}


@router.get("")
async def list_tasks(limit: int = 50, offset: int = 0) -> dict:
    tasks = await TaskService.list_tasks(limit=limit, offset=offset)
    return {"code": 200, "message": "success", "data": [_task_to_dict(t) for t in tasks]}


@router.get("/{task_id}")
async def get_task(task_id: int) -> dict:
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"code": 200, "message": "success", "data": _task_detail(task)}


@router.get("/{task_id}/report")
async def get_report(task_id: int) -> dict:
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail=f"任务尚未完成（当前状态：{task.status}）")
    return {
        "code": 200,
        "message": "success",
        "data": {
            "topic": task.topic,
            "report": task.final_report,
            "review_rounds": task.review_rounds,
            "review_history": task.review_history,
        },
    }


@router.delete("/{task_id}")
async def delete_task(task_id: int) -> dict:
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in ("running", "paused"):
        raise HTTPException(status_code=409, detail=f"任务正在执行（状态：{task.status}），不能删除")
    ok = await TaskService.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"code": 200, "message": "success", "data": None}
