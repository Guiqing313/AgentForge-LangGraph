"""分析 Agent：对检索结果进行提取、交叉验证与总结。"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent

SYSTEM_PROMPT = """你是一名信息分析专家。给定一个子问题和检索结果，完成以下任务：
1. 提取与问题相关的关键信息（key_findings）；
2. 标注整体可信度（credibility：高/中/低）；
3. 指出不同来源之间的矛盾点（contradictions，没有则为空数组）；
4. 用 2-3 句话给出综合总结（summary）。

真实性约束（最高优先级）：
- 只能基于提供的检索结果进行分析，禁止使用你自己的知识补充、推测或编造；
- 如果检索结果为空、全部为错误信息，或标记为「未检索到有效结果」，则 key_findings 必须为空数组，credibility 为「低」，summary 必须明确写「未检索到有效信息，无法进行可靠分析」；
- 不得虚构论文、机构、数据或来源。

只输出 JSON，不要输出解释文字。

输出格式：
{
  "key_findings": ["发现1", "发现2"],
  "credibility": "中",
  "contradictions": [],
  "summary": "综合总结"
}
"""


class AnalyzerAgent(BaseAgent):
    """检索结果 -> 结构化分析结论。"""

    def analyze(self, question: str, search_results: list[str]) -> dict[str, Any]:
        joined = "\n\n".join(
            f"[资料{i + 1}]\n{text}" for i, text in enumerate(search_results)
        ) or "（无检索结果）"

        user = f"子问题：{question}\n\n检索结果：\n{joined}"
        result = self._chat_json(SYSTEM_PROMPT, user)

        if not isinstance(result, dict):
            raise ValueError(f"分析 Agent 返回格式错误：{result!r}")
        return {
            "key_findings": result.get("key_findings", []),
            "credibility": result.get("credibility", "未知"),
            "contradictions": result.get("contradictions", []),
            "summary": result.get("summary", ""),
        }