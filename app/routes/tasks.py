"""研究任务相关 API。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class TaskCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="研究主题")


class ResumeRequest(BaseModel):
    sub_questions: list[str] = Field(default_factory=list, description="用户编辑后的子问题（空则沿用原提案）")


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
            "metrics": task.metrics or {},
        }
    )
    return data


@router.post("", status_code=201)
async def create_task(payload: TaskCreate) -> dict:
    task = await TaskService.create_task(payload.topic)
    # B2：任务由单进程 worker 领取执行（不再在 API 进程内直接起协程）
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

@router.post("/{task_id}/resume")
async def resume_task(task_id: int, payload: ResumeRequest) -> dict:
    """恢复被 interrupt 暂停的任务（B1 人机协同）。"""
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "paused":
        raise HTTPException(status_code=409, detail=f"任务当前状态为 {task.status}，只有 paused 可以恢复")
    try:
        updated = await TaskService.resume_task(task_id, payload.sub_questions)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 200, "message": "success", "data": _task_detail(updated)}

@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int) -> dict:
    """取消任务：pending/paused 直接取消；running 为 best-effort（安全点收敛）。"""
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status in ("completed", "failed", "canceled"):
        raise HTTPException(status_code=409, detail=f"任务状态为 {task.status}，无需取消")
    try:
        updated = await TaskService.cancel_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 200, "message": "success", "data": _task_detail(updated)}

@router.get("/{task_id}/metrics")
async def get_metrics(task_id: int) -> dict:
    """返回任务指标（节点耗时/token/搜索次数/估算成本）。"""
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"code": 200, "message": "success", "data": task.metrics or {}}

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/{task_id}/stream")
async def stream_task(task_id: int):
    """SSE 事件流：status / log / node / done / error（不做断线续传）。"""
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_generator():
        last_status = None
        sent_logs = 0
        sent_nodes = 0
        while True:
            current = await TaskService.get_task(task_id)
            if current is None:
                yield _sse("error", {"error": "任务已不存在"})
                return
            if current.status != last_status:
                last_status = current.status
                yield _sse("status", {"status": last_status})
            logs = current.logs or []
            for line in logs[sent_logs:]:
                sent_logs += 1
                yield _sse("log", {"line": line})
            metrics = current.metrics or {}
            for node in (metrics.get("node_latencies") or [])[sent_nodes:]:
                sent_nodes += 1
                yield _sse("node", node)
            if current.status in ("completed", "failed", "canceled"):
                if current.status == "completed":
                    yield _sse("done", {"status": current.status})
                else:
                    yield _sse("error", {"status": current.status, "error": current.error or ""})
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
