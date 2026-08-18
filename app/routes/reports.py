"""报告导出相关 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.services.task_service import TaskService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{task_id}/download", response_class=PlainTextResponse)
async def download_report(task_id: int) -> str:
    task = await TaskService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed" or not task.final_report:
        raise HTTPException(status_code=409, detail="报告尚未生成")
    return task.final_report