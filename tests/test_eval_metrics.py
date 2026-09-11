"""工程化检索评测指标测试（纯函数，不依赖索引/模型）。"""

from app.kb.eval_kb import DEFAULT_EVAL_QUERIES, REFUSAL_MIN_DISTANCE, EvalQuery, EvalResult, compute_metrics


def _hit(source: str, text: str = "", distance: float = 0.1) -> dict:
    return {"source": source, "text": text, "distance": distance}


def test_metrics_perfect_ranking():
    query = EvalQuery("q", "basic", ("a.md",), ("alpha",))
    result = EvalResult(query=query, hits=[_hit("a.md", "alpha"), _hit("b.md")])
    metrics = compute_metrics([result], (1, 3))
    assert metrics["hit_rate@1"] == 1.0
    assert metrics["mrr@1"] == 1.0
    assert metrics["recall@1"] == 1.0
    assert metrics["ndcg@1"] == 1.0


def test_metrics_partial_recall_and_miss_at_1():
    query = EvalQuery("q", "basic", ("a.md", "b.md"), ("alpha",))
    result = EvalResult(query=query, hits=[_hit("c.md"), _hit("a.md", "alpha")])
    metrics = compute_metrics([result], (1, 3))
    assert metrics["hit_rate@1"] == 0.0
    assert metrics["hit_rate@3"] == 1.0
    assert metrics["mrr@3"] == 0.5
    assert metrics["recall@3"] == 0.5


def test_refusal_proxy_metric():
    query = EvalQuery("北京天气", "refusal", should_refuse=True)
    safe = EvalResult(query=query, hits=[_hit("x.md", distance=REFUSAL_MIN_DISTANCE + 0.1)])
    unsafe = EvalResult(query=query, hits=[_hit("x.md", distance=0.1)])
    metrics = compute_metrics([safe, unsafe], (3,))
    assert metrics["refusal_accuracy"] == 0.5


def test_dataset_shape():
    categories = {query.category for query in DEFAULT_EVAL_QUERIES}
    assert len(DEFAULT_EVAL_QUERIES) >= 30
    assert {"basic", "long_tail", "multi_hop", "refusal"} <= categories
    assert len([q for q in DEFAULT_EVAL_QUERIES if q.should_refuse]) >= 5
