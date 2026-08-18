"""撰写 Agent：整合分析结果，生成/修订结构化研究报告。"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent

REPORT_SYSTEM_PROMPT = """你是一名专业的研究报告撰写专家。请基于给定分析结果撰写一份结构化研究报告。

要求：
1. 使用 Markdown，包含「研究摘要」「正文」「结论」三个部分；
2. 正文按子问题分章节，每章末尾标注信息来源；
3. 结论要综合各章发现，给出整体判断；
4. 语言专业、逻辑清晰，用数据支撑观点；
5. 直接输出报告正文，不要输出解释文字。

真实性约束（最高优先级）：
- 只能基于提供的分析结果撰写，禁止编造任何数据、论文、机构或引用来源；
- 未检索到有效信息的子问题，必须如实写「信息不足 / 未检索到有效数据」，不得虚构内容；
- 引用的来源只能来自分析结果中提供的 sources，不得添加不存在的来源；
- 若所有子问题均无有效信息，摘要必须明确说明本次研究未能检索到有效信息。
"""

REVISE_SYSTEM_PROMPT = """你是一名专业的研究报告撰写专家。请根据审核意见对报告进行定向修订。

要求：
1. 只修改审核意见指出的问题，保留其他内容的原貌；
2. 保持 Markdown 结构和专业文风；
3. 直接输出修订后的完整报告，不要输出解释文字。

真实性约束（最高优先级）：
- 修订时禁止新增任何未经分析结果支撑的数据、论文、机构或来源；
- 不得为了满足审核意见而编造内容，信息不足就如实标注信息不足。
"""


class WriterAgent(BaseAgent):
    """分析结果 -> 结构化报告；并支持按反馈修订。"""

    def write(self, topic: str, analysis_results: dict[str, Any]) -> str:
        user = self._build_user_prompt(topic, analysis_results)
        return self._chat(REPORT_SYSTEM_PROMPT, user)

    def revise(self, topic: str, draft: str, feedback: str) -> str:
        user = (
            f"研究主题：{topic}\n\n"
            f"当前报告：\n{draft}\n\n"
            f"审核意见：\n{feedback}\n\n"
            "请据此修订报告。"
        )
        return self._chat(REVISE_SYSTEM_PROMPT, user)

    @staticmethod
    def _build_user_prompt(topic: str, analysis_results: dict[str, Any]) -> str:
        lines = [f"研究主题：{topic}", "", "分析结果："]
        for question, analysis in analysis_results.items():
            findings = "\n".join(f"  - {f}" for f in analysis.get("key_findings", []))
            sources = "\n".join(
                f"  - {s}" for s in analysis.get("sources", [])
            )
            lines.append(
                f"### 子问题：{question}\n"
                f"关键发现：\n{findings or '  （无）'}\n"
                f"可信度：{analysis.get('credibility', '未知')}\n"
                f"综合总结：{analysis.get('summary', '')}\n"
                f"来源：\n{sources or '  （无）'}\n"
            )
        return "\n".join(lines)