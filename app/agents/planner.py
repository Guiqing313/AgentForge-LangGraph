"""规划 Agent：把研究主题分解为可检索的子问题。"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.config import settings

SYSTEM_PROMPT = """你是一名研究规划专家。给定一个研究主题，把它分解为若干具体、可检索、互不重复的子问题。

要求：
1. 每个子问题聚焦一个具体方面，可以独立通过信息检索获得答案；
2. 子问题之间互补，合起来能覆盖主题的主要维度；
3. 只输出 JSON，不要输出任何解释文字。

输出格式：
{"sub_questions": ["子问题1", "子问题2", "子问题3"]}
"""


class PlannerAgent(BaseAgent):
    """研究主题 -> 子问题列表。"""

    def plan(self, topic: str, memories: list[str] | None = None) -> list[str]:
        background = ""
        if memories:
            joined = "\n".join(f"- {m}" for m in memories)[: settings.memory_max_chars]
            background = (
                "\n\n参考背景（来自历史任务，可能不完整，仅作参考，不得替代本次检索）：\n"
                f"{joined}"
            )
        user = f"研究主题：{topic}{background}\n请分解为 3-{settings.max_sub_questions} 个子问题。"
        result = self._chat_json(SYSTEM_PROMPT, user)

        questions = result.get("sub_questions", []) if isinstance(result, dict) else []
        if not isinstance(questions, list):
            raise ValueError(f"规划 Agent 返回格式错误：{result!r}")

        # 清洗：去空白、去空项、去重（保序）、限制数量
        seen: set[str] = set()
        cleaned: list[str] = []
        for q in questions:
            if not isinstance(q, str):
                continue
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                cleaned.append(q)
        if not cleaned:
            raise ValueError("规划 Agent 未生成任何有效子问题")

        return cleaned[: settings.max_sub_questions]