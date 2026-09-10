"""A1：知识库 loader/indexer/embedding 的离线测试（确定性假向量，不访问网络）。"""

from dataclasses import replace

from app.config import settings
from app.kb import indexer
from app.kb.embedding import DeterministicHashEmbeddingFunction
from app.kb.loader import load_documents, sha256_text


def _write_corpus(tmp_path):
    docs_dir = tmp_path / "kb"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("RAG 是检索增强生成。\n\n它通过检索文档辅助生成。", encoding="utf-8")
    (docs_dir / "b.txt").write_text("LangGraph 用于编排多 Agent 工作流。", encoding="utf-8")
    (docs_dir / "empty.md").write_text("   ", encoding="utf-8")
    return docs_dir


def test_load_documents_skips_empty(tmp_path):
    docs = load_documents(_write_corpus(tmp_path))
    assert {d.source for d in docs} == {"a.md", "b.txt"}
    assert all(d.sha256 for d in docs)


def test_split_text_and_deterministic_chunk_id():
    text = "大模型是人工智能的核心技术。" * 60
    chunks = indexer.split_text(text, chunk_size=100, overlap=10)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)
    assert indexer.chunk_id("a.md", 0, chunks[0]) == indexer.chunk_id("a.md", 0, chunks[0])


def test_build_and_query_with_fake_embedding(tmp_path, monkeypatch):
    docs_dir = _write_corpus(tmp_path)
    fake = DeterministicHashEmbeddingFunction(dim=64)
    monkeypatch.setattr(
        indexer,
        "settings",
        replace(
            settings,
            chroma_persist_dir=str(tmp_path / "chroma"),
            chroma_collection="test_kb",
            docs_dir=str(docs_dir),
        ),
    )

    stats = indexer.build_index(docs_dir=str(docs_dir), rebuild=True, embedding_function=fake)
    assert stats["documents"] == 2
    assert stats["chunks"] >= 2
    assert stats["collection_count"] == stats["chunks"]

    results = indexer.query("RAG 检索", n_results=2, embedding_function=fake)
    assert isinstance(results, list) and results
    assert all("source" in r and "text" in r for r in results)

    again = indexer.build_index(docs_dir=str(docs_dir), rebuild=True, embedding_function=fake)
    assert again["collection_count"] == again["chunks"]
    assert sha256_text("x") == sha256_text("x")