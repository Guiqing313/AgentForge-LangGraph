"""只读信息接口：知识库、实验对比、系统信息（供前端功能页使用）。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/api", tags=["insights"])
BASE_DIR = Path(__file__).resolve().parent.parent.parent


@router.get("/kb/stats")
def kb_stats() -> dict:
    """知识库语料与索引统计（不暴露密钥）。"""
    from app.kb import indexer
    from app.kb.loader import load_documents

    documents: list[dict] = []
    try:
        docs = load_documents(settings.docs_dir)
        documents = [
            {"file": doc.source, "sha256": doc.sha256[:12], "size_chars": len(doc.text)} for doc in docs
        ]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"语料加载失败：{exc}") from exc

    count = 0
    try:
        collection = indexer.get_collection(create=False)
        count = collection.count()
    except Exception:  # noqa: BLE001 —— 索引不存在时返回 0
        count = 0

    manifest_path = Path(settings.docs_dir) / "manifest.json"
    corpus_version = None
    if manifest_path.exists():
        corpus_version = json.loads(manifest_path.read_text(encoding="utf-8")).get("corpus_version")

    return {
        "collection": settings.chroma_collection,
        "collection_count": count,
        "document_count": len(documents),
        "documents": documents,
        "corpus_version": corpus_version,
    }


class KbSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    n_results: int = Field(default=3, ge=1, le=10)


@router.post("/kb/search")
def kb_search(payload: KbSearchRequest) -> dict:
    """在线检索预览（真实走本地 bge-m3 + Chroma）。"""
    from app.tools.rag import LocalSearchTool

    try:
        results = LocalSearchTool().search(payload.query, n_results=payload.n_results)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"检索失败：{exc}") from exc
    return {"query": payload.query, "count": len(results), "results": results}


@router.get("/experiments/live")
def live_experiments() -> dict:
    """读取 data/live_results.json（Ollama/DeepSeek 真实运行对比）。"""
    path = BASE_DIR / "data" / "live_results.json"
    if not path.exists():
        return {"available": False, "data": None}
    return {"available": True, "data": json.loads(path.read_text(encoding="utf-8"))}


@router.get("/system/info")
def system_info() -> dict:
    """运行配置与能力边界（不含密钥）。"""
    from app.cost import load_prices, price_status

    prices = load_prices()
    return {
        "provider": settings.effective_provider,
        "llm_mode": settings.llm_mode,
        "ollama_model": settings.ollama_model,
        "deepseek_model": settings.deepseek_model,
        "memory_enabled": settings.memory_enabled,
        "human_review_enabled": settings.human_review_enabled,
        "limits": {
            "max_llm_calls_per_task": settings.max_llm_calls_per_task,
            "max_tavily_calls_per_task": settings.max_tavily_calls_per_task,
            "max_prompt_chars_per_call": settings.max_prompt_chars_per_call,
            "max_cost_cny_per_task": settings.max_cost_cny_per_task,
        },
        "price_status": {
            "deepseek": price_status("deepseek", prices),
            "tavily": price_status("tavily", prices),
        },
        "paid_allowed": settings.allow_paid_provider,
        "mcp_tools": ["web_search", "local_search", "calculate"],
        "embedding": {"model": settings.embedding_model, "dim": settings.embedding_dim, "base_url": settings.embedding_base_url},
    }
