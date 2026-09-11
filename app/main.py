"""FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.migrations import ensure_schema
from app.routes import insights, reports, tasks
from app.worker import recover_stale_tasks, worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_schema()
    stop_event = asyncio.Event()
    worker_task: asyncio.Task | None = None
    if settings.worker_enabled:
        await recover_stale_tasks()
        worker_task = asyncio.create_task(worker_loop(stop_event))
    try:
        yield
    finally:
        if worker_task is not None:
            stop_event.set()
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(
    title="AgentForge API",
    description="基于 LangGraph 的多 Agent 智能研究协作系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(reports.router)
app.include_router(insights.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agentforge"}
