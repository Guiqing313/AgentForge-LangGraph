"""LangGraph 共享状态定义。

所有节点通过该 State 通信：每个节点读取相关字段、返回部分更新，
LangGraph 负责合并（普通字段覆盖，Annotated 字段按归并函数追加）。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.agents.searcher import SearchOutcome


class ResearchState(TypedDict, total=False):
    """研究任务的工作流状态。"""

    # 输入
    topic: str

    # 跨任务经验记忆（A2；由 task_service 注入，供 planner 参考）
    relevant_memories: list[str]

    # 规划
    sub_questions: list[str]
    current_question_index: int

    # 搜索（question -> SearchOutcome 对象）
    search_outcomes: dict[str, SearchOutcome]

    # 分析（question -> 结构化分析结果）
    analysis_results: dict[str, Any]

    # 撰写与审核
    draft_report: str
    final_report: str
    review_rounds: int
    review_feedback: str
    review_history: Annotated[list[dict], operator.add]

    # 状态与过程记录
    status: str
    log: Annotated[list[str], operator.add]


def initial_state(topic: str, relevant_memories: list[str] | None = None) -> dict:
    """构造任务初始状态。"""
    return {
        "topic": topic,
        "relevant_memories": relevant_memories or [],
        "sub_questions": [],
        "current_question_index": 0,
        "search_outcomes": {},
        "analysis_results": {},
        "draft_report": "",
        "final_report": "",
        "review_rounds": 0,
        "review_feedback": "",
        "review_history": [],
        "status": "planning",
        "log": [],
    }
