"""审核 Agent：对报告打分并给出定向修改建议。"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一名严谨的研究报告审核专家。请从以下四个维度审核报告：
1. 完整性（是否覆盖所有子问题）；
2. 准确性（结论是否有检索结果支撑）；
3. 逻辑性（结构是否清晰、论证是否连贯）；
4. 可读性（语言是否专业易懂）。

评分规则：1-10 的整数，8 分及以上为合格。

只输出 JSON，不要输出解释文字。

输出格式：
{
  "score": 8,
  "suggestions": ["改进建议1", "改进建议2"],
  "issues": ["存在的问题1"]
}
"""


class ReviewerAgent(BaseAgent):
    """报告 -> 评分与修改建议。"""

    def review(self, topic: str, draft: str) -> dict[str, Any]:
        user = f"研究主题：{topic}\n\n待审核报告：\n{draft}"
        result = self._chat_json(SYSTEM_PROMPT, user)

        if not isinstance(result, dict):
            raise ValueError(f"审核 Agent 返回格式错误：{result!r}")

        try:
            score = int(result.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(1, min(10, score))

        return {
            "score": score,
            "suggestions": result.get("suggestions", []),
            "issues": result.get("issues", []),
        }