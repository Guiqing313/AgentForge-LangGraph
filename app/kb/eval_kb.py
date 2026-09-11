"""知识库检索评测（工程化：分层查询集 + 多指标 + 分类聚合）。

评测口径：
- 相关性：命中期望来源 且（若给出关键词）文本包含任一关键词；
- 指标：hit_rate@k、MRR@k、recall@k、nDCG@k（二值相关），分别报告 overall 与 per-category；
- 库外拒答：用"top-1 距离 >= 阈值"作为检索层代理指标（真正的拒答由生成层保证，见 eval_real/RAGAS）；
- 输出：JSON（--out）与 Markdown（--markdown），可选 --limit 快速抽样。

用法：
    python -m app.kb.eval_kb --k 3 --out data/eval_report.json --markdown data/eval_report.md
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.kb import indexer

REFUSAL_MIN_DISTANCE = 0.35  # cosine distance：>= 该值视为"没有强匹配"，检索层拒答代理


@dataclass(frozen=True)
class EvalQuery:
    question: str
    category: str
    expected_sources: tuple[str, ...] = ()
    expected_keywords: tuple[str, ...] = ()
    should_refuse: bool = False


@dataclass
class EvalResult:
    query: EvalQuery
    hits: list[dict] = field(default_factory=list)

    def relevant_hits(self) -> list[tuple[int, dict]]:
        return [(rank, hit) for rank, hit in enumerate(self.hits, start=1) if is_relevant(hit, self.query)]

    @property
    def top_distance(self) -> float | None:
        if not self.hits:
            return None
        distance = self.hits[0].get("distance")
        return float(distance) if distance is not None else None

    @property
    def refusal_pass(self) -> bool:
        distance = self.top_distance
        return distance is None or distance >= REFUSAL_MIN_DISTANCE


def is_relevant(hit: dict, query: EvalQuery) -> bool:
    if query.should_refuse:
        return False
    if hit.get("source") not in query.expected_sources:
        return False
    if not query.expected_keywords:
        return True
    text = str(hit.get("text", "")).lower()
    return any(keyword.lower() in text for keyword in query.expected_keywords)


BASIC: tuple[EvalQuery, ...] = (
    EvalQuery("RAG 的完整流程是什么？", "basic", ("主流大模型与应用范式分析.md", "tutorial-AgentForge.md"), ("RAG", "检索")),
    EvalQuery("什么是混合检索？", "basic", ("主流大模型与应用范式分析.md", "tutorial-AgentForge.md"), ("混合检索", "BM25", "向量")),
    EvalQuery("LoRA 和 QLoRA 有什么区别？", "basic", ("微调与LoRA知识.md", "主流大模型与应用范式分析.md"), ("LoRA", "QLoRA")),
    EvalQuery("大模型幻觉是怎么产生的？", "basic", ("大模型幻觉与Prompt注入风险工程化应对.md", "主流大模型与应用范式分析.md"), ("幻觉",)),
    EvalQuery("Prompt 注入的风险如何防御？", "basic", ("大模型幻觉与Prompt注入风险工程化应对.md",), ("注入", "防御")),
    EvalQuery("AgentForge 包含哪几个 Agent？", "basic", ("README.md", "tutorial-AgentForge.md"), ("规划", "搜索", "审核")),
    EvalQuery("LangGraph 在 AgentForge 中起什么作用？", "basic", ("README.md", "tutorial-AgentForge.md"), ("LangGraph", "状态图")),
    EvalQuery("审核闭环如何避免死循环？", "basic", ("README.md", "tutorial-AgentForge.md"), ("审核", "死循环", "轮次")),
    EvalQuery("任务指标里有哪些内容？", "basic", ("README.md", "tutorial-AgentForge.md"), ("指标", "耗时", "成本")),
    EvalQuery("MCP 暴露了哪些工具？", "basic", ("README.md", "tutorial-AgentForge.md"), ("MCP", "local_search", "calculate")),
    EvalQuery("人机协同如何暂停和恢复？", "basic", ("README.md", "tutorial-AgentForge.md"), ("resume", "暂停", "interrupt")),
    EvalQuery("向量数据库在 RAG 中起什么作用？", "basic", ("主流大模型与应用范式分析.md",), ("向量", "数据库")),
)

LONG_TAIL: tuple[EvalQuery, ...] = (
    EvalQuery("我只有 8G 显存，想微调 7B 模型，有什么办法？", "long_tail", ("微调与LoRA知识.md", "主流大模型与应用范式分析.md"), ("QLoRA", "显存")),
    EvalQuery("为什么回答总是照抄资料？怎么让回答更自然？", "long_tail", ("大模型幻觉与Prompt注入风险工程化应对.md", "主流大模型与应用范式分析.md"), ("照抄", "提示词", "组织")),
    EvalQuery("怎样让检索既懂语义又能精确匹配关键词？", "long_tail", ("主流大模型与应用范式分析.md", "tutorial-AgentForge.md"), ("BM25", "向量", "RRF")),
    EvalQuery("多 Agent 系统如何控制搜索轮次、避免无限循环？", "long_tail", ("README.md", "tutorial-AgentForge.md"), ("最大", "轮次", "充分性")),
    EvalQuery("如何保证报告里的来源是真实的、不编造？", "long_tail", ("大模型幻觉与Prompt注入风险工程化应对.md", "README.md", "tutorial-AgentForge.md"), ("来源", "编造", "拒答")),
    EvalQuery("服务重启后任务还能继续吗？", "long_tail", ("README.md", "tutorial-AgentForge.md"), ("checkpoint", "恢复", "任务")),
    EvalQuery("如何看到每个节点的耗时和调用成本？", "long_tail", ("README.md", "tutorial-AgentForge.md"), ("节点", "耗时", "成本")),
    EvalQuery("前端如何查看知识库里有哪些文档？", "long_tail", ("README.md", "tutorial-AgentForge.md"), ("知识库", "文档", "manifest")),
    EvalQuery("怎样防止知识库文档里的恶意指令影响模型？", "long_tail", ("大模型幻觉与Prompt注入风险工程化应对.md",), ("注入", "不可信", "资料")),
    EvalQuery("为什么需要跨任务记忆？它怎么工作？", "long_tail", ("README.md", "tutorial-AgentForge.md"), ("记忆", "参考背景")),
)

MULTI_HOP: tuple[EvalQuery, ...] = (
    EvalQuery("把 AgentForge 的检索链路和技术文档里的混合检索知识对应起来说明", "multi_hop", ("README.md", "tutorial-AgentForge.md", "主流大模型与应用范式分析.md"), ("混合检索", "BM25", "重排")),
    EvalQuery("如果要给多 Agent 系统做评测，应该看哪些指标？", "multi_hop", ("主流大模型与应用范式分析.md", "tutorial-AgentForge.md", "README.md"), ("评测", "faithfulness", "指标")),
    EvalQuery("本地部署 7B 模型和向量库需要哪些组件？", "multi_hop", ("主流大模型与应用范式分析.md", "README.md"), ("Ollama", "Milvus", "embedding")),
    EvalQuery("如何同时保证回答忠实、可溯源，并且不泄露密钥？", "multi_hop", ("大模型幻觉与Prompt注入风险工程化应对.md", "README.md", "tutorial-AgentForge.md"), ("引用", "拒答", "密钥")),
    EvalQuery("worker 和 checkpoint 在任务生命周期中怎么配合？", "multi_hop", ("README.md", "tutorial-AgentForge.md"), ("worker", "checkpoint", "暂停")),
)

REFUSAL: tuple[EvalQuery, ...] = (
    EvalQuery("北京今天的天气怎么样？", "refusal", should_refuse=True),
    EvalQuery("明天哪只股票会涨？", "refusal", should_refuse=True),
    EvalQuery("帮我起草一份购房合同的关键条款。", "refusal", should_refuse=True),
    EvalQuery("我头疼应该吃什么药？", "refusal", should_refuse=True),
    EvalQuery("2026年英语四六级报名时间是什么时候？", "refusal", should_refuse=True),
)

DEFAULT_EVAL_QUERIES: tuple[EvalQuery, ...] = BASIC + LONG_TAIL + MULTI_HOP + REFUSAL


def _dcg(ranks: list[int], k: int) -> float:
    return sum(1.0 / math.log2(rank + 1) for rank in ranks if rank <= k)


def _idcg(relevant_count: int, k: int) -> float:
    return sum(1.0 / math.log2(rank + 1) for rank in range(1, min(relevant_count, k) + 1))


def compute_metrics(results: list[EvalResult], k_values: tuple[int, ...] = (1, 3, 5)) -> dict:
    """纯函数：从 EvalResult 计算 overall 指标（便于单测，不需要索引）。"""
    answerable = [r for r in results if not r.query.should_refuse]
    refusal = [r for r in results if r.query.should_refuse]
    metrics: dict = {"query_count": len(results), "k_values": list(k_values)}
    for k in k_values:
        hits = 0
        reciprocal = 0.0
        recall = 0.0
        ndcg = 0.0
        for result in answerable:
            ranks = [rank for rank, _ in result.relevant_hits()]
            if any(rank <= k for rank in ranks):
                hits += 1
            first = next((rank for rank in ranks if rank <= k), None)
            if first is not None:
                reciprocal += 1.0 / first
            expected = set(result.query.expected_sources)
            matched = {hit.get("source") for rank, hit in result.relevant_hits() if rank <= k}
            recall += (len(matched & expected) / len(expected)) if expected else 0.0
            ideal = _idcg(len(expected), k) if expected else 0.0
            ndcg += (_dcg(ranks, k) / ideal) if ideal > 0 else 0.0
        denominator = len(answerable) or 1
        metrics[f"hit_rate@{k}"] = round(hits / denominator, 4)
        metrics[f"mrr@{k}"] = round(reciprocal / denominator, 4)
        metrics[f"recall@{k}"] = round(recall / denominator, 4)
        metrics[f"ndcg@{k}"] = round(ndcg / denominator, 4)
    if refusal:
        metrics["refusal_accuracy"] = round(sum(1 for r in refusal if r.refusal_pass) / len(refusal), 4)
    return metrics


def _per_category(results: list[EvalResult], k_values: tuple[int, ...]) -> dict:
    categories = sorted({r.query.category for r in results})
    return {category: compute_metrics([r for r in results if r.query.category == category], k_values) for category in categories}


def evaluate(queries: tuple[EvalQuery, ...] = DEFAULT_EVAL_QUERIES, k: int = 3, limit: int | None = None) -> dict:
    k_values = tuple(sorted({1, 3, 5} | {max(1, k)}))
    selected = queries[:limit] if limit else queries
    results: list[EvalResult] = []
    for query in selected:
        hits = indexer.query(query.question, n_results=max(k_values))
        results.append(EvalResult(query=query, hits=hits))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "k": k,
        "refusal_min_distance": REFUSAL_MIN_DISTANCE,
        "overall": compute_metrics(results, k_values),
        "by_category": _per_category(results, k_values),
        "details": [
            {
                "question": result.query.question,
                "category": result.query.category,
                "top_sources": [hit.get("source") for hit in result.hits],
                "top_distances": [hit.get("distance") for hit in result.hits],
                "relevant_ranks": [rank for rank, _ in result.relevant_hits()],
                "refusal_pass": result.refusal_pass if result.query.should_refuse else None,
            }
            for result in results
        ],
    }
    return report


def format_markdown(report: dict) -> str:
    overall = report["overall"]
    lines = [
        "# RAG 检索评测报告",
        "",
        f"- 时间：{report['generated_at']}",
        f"- 查询数：{overall['query_count']}；k 值：{report['k_values']}",
        f"- 拒答阈值（cosine distance）：{report['refusal_min_distance']}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 值 |",
        "|---|---|",
    ]
    for key, value in overall.items():
        if key in ("query_count", "k_values"):
            continue
        lines.append(f"| {key} | {value} |")
    lines += ["", "## 分类指标", ""]
    for category, metrics in report["by_category"].items():
        lines.append(f"### {category}（{metrics['query_count']} 题）")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|---|---|")
        for key, value in metrics.items():
            if key in ("query_count", "k_values"):
                continue
            lines.append(f"| {key} | {value} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 检索评测（工程化）")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（快速抽样）")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--markdown", default=None, help="输出 Markdown 路径")
    args = parser.parse_args()

    report = evaluate(k=args.k, limit=args.limit)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(payload)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(format_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
