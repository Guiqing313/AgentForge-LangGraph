"""SQLAlchemy 数据模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class ResearchTask(Base):
    """一次研究任务的持久化记录。"""

    __tablename__ = "research_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String(500), nullable=False)
    status = Column(String(20), default="pending")  # pending/running/completed/failed

    sub_questions = Column(JSON, default=list)
    search_results = Column(JSON, default=list)
    analysis_results = Column(JSON, default=dict)
    draft_report = Column(Text, default="")
    final_report = Column(Text, default="")
    review_history = Column(JSON, default=list)
    review_rounds = Column(Integer, default=0)
    logs = Column(JSON, default=list)
    error = Column(Text, default="")

    created_at = Column(DateTime, default=lambda: datetime.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())
    completed_at = Column(DateTime, nullable=True)