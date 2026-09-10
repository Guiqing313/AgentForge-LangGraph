"""知识库检索评估：10 条固定查询 → hit_rate@k / MRR。

相关性判定 = 返回结果的 source 命中期望文档 且（若提供关键词）文本包含任一关键词。
这是小语料库的简化标注方式，报告必须注明口径。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.kb import indexer


@dataclass(frozen=True)
class EvalQuery:
    question: str
    expected_sources: tuple[str, ...]
    expected_keywords: tuple[str, ...] = ()


@dataclass
class EvalResult:
    query: str
    hits: list[dict]
    relevant_ranks: list[int] = field(default_factory=list)

    @property
    def first_relevant_rank(self) -> int | None:
        return self.relevant_ranks[0] if self.relevant_ranks else None


DEFAULT_EVAL_QUERIES: tuple[EvalQuery, ...] = (
    EvalQuery("LangGraph 多 Agent 研究协作系统是如何设计的？", ("README.md", "tutorial-AgentForge.md"), ("LangGraph", "Agent")),
    EvalQuery("审核闭环如何避免死循环？", ("README.md", "tutorial-AgentForge.md"), ("审核", "死循环", "迭代")),
    EvalQuery("ReAct 搜索 Agent 的工作流程是什么？", ("tutorial-AgentForge.md", "README.md"), ("ReAct", "搜索")),
    EvalQuery("RAG 的完整流程是什么？", ("主流大模型与应用范式分析.md", "AI应用实习面试学习文档.md", "tutorial-AgentForge.md"), ("检索", "RAG")),
    EvalQuery("混合检索为什么要把向量和 BM25 结合？", ("主流大模型与应用范式分析.md", "AI应用实习面试学习文档.md"), ("BM25", "向量", "检索")),
    EvalQuery("Prompt 注入的风险如何工程化防御？", ("大模型幻觉与Prompt注入风险工程化应对.md",), ("注入", "防御", "Prompt")),
    EvalQuery("LoRA 和 QLoRA 有什么区别？", ("微调与LoRA知识.md", "主流大模型与应用范式分析.md"), ("LoRA", "微调")),
    EvalQuery("大模型幻觉是怎么产生的？", ("大模型幻觉与Prompt注入风险工程化应对.md", "主流大模型与应用范式分析.md"), ("幻觉",)),
    EvalQuery("AI 应用岗位面试通常考察哪些能力？", ("AI应用实习面试学习文档.md",), ("面试", "能力", "应用")),
    EvalQuery("向量数据库在 RAG 中起什么作用？", ("主流大模型与应用范式分析.md", "AI应用实习面试学习文档.md"), ("向量", "数据库")),
)


def is_relevant(hit: dict, query: EvalQuery) -> bool:
    if hit.get("source") not in query.expected_sources:
        return False
    if not query.expected_keywords:
        return True
    text = str(hit.get("text", ""))
    return any(keyword.lower() in text.lower() for keyword in query.expected_keywords)


def evaluate(queries: tuple[EvalQuery, ...] = DEFAULT_EVAL_QUERIES, k: int = 3) -> dict:
    results: list[EvalResult] = []
    for item in queries:
        hits = indexer.query(item.question, n_results=k)
        result = EvalResult(query=item.question, hits=hits)
        for rank, hit in enumerate(hits, start=1):
            if is_relevant(hit, item):
                result.relevant_ranks.append(rank)
        results.append(result)

    hit_count = sum(1 for r in results if r.first_relevant_rank is not None)
    reciprocal_sum = sum(1.0 / r.first_relevant_rank for r in results if r.first_relevant_rank)
    return {
        "k": k,
        "total": len(results),
        "hits": hit_count,
        "hit_rate": round(hit_count / len(results), 4) if results else 0.0,
        "mrr": round(reciprocal_sum / len(results), 4) if results else 0.0,
        "details": [
            {
                "query": r.query,
                "first_relevant_rank": r.first_relevant_rank,
                "top_sources": [h.get("source") for h in r.hits],
                "top_distances": [h.get("distance") for h in r.hits],
            }
            for r in results
        ],
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
