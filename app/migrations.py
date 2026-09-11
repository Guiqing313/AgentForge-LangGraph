"""轻量 schema 迁移（SQLite；B2 新增 worker 字段）。

不引入 Alembic：启动时用 PRAGMA table_info 检查缺失列并 ALTER TABLE ADD COLUMN。
"""

from __future__ import annotations

import logging

from app.db.database import engine

logger = logging.getLogger(__name__)

_MIGRATIONS = [
    ("locked_at", "locked_at DATETIME"),
    ("heartbeat_at", "heartbeat_at DATETIME"),
    ("attempts", "attempts INTEGER DEFAULT 0"),
    ("cancel_requested", "cancel_requested BOOLEAN DEFAULT 0"),
]


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        def _migrate(sync_conn) -> None:
            rows = sync_conn.exec_driver_sql("PRAGMA table_info(research_tasks)").fetchall()
            columns = {row[1] for row in rows}
            for name, ddl in _MIGRATIONS:
                if name not in columns:
                    logger.info("迁移：research_tasks 增加列 %s", name)
                    sync_conn.exec_driver_sql(f"ALTER TABLE research_tasks ADD COLUMN {ddl}")

        await conn.run_sync(_migrate)
