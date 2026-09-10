"""知识库索引：分块（确定性 id）→ 向量化（embedding 函数）→ Chroma 持久化。"""

from __future__ import annotations

import uuid
from typing import Any

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.kb.embedding import get_embedding_function
from app.kb.loader import Document, load_documents, sha256_text

# 固定命名空间，保证 chunk id 在多次构建/多进程之间稳定
NAMESPACE = uuid.UUID("6f2f0b7e-6f3a-4c1f-9f2e-7c0c5b5f7a01")


def split_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    """按段落/句子边界递归切分（默认 500 字符、重叠 50）。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.chunk_size,
        chunk_overlap=overlap or settings.chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    return [piece.strip() for piece in splitter.split_text(text) if piece.strip()]


def chunk_id(source: str, index: int, text: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{source}:{index}:{sha256_text(text)[:16]}"))


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_collection(client: chromadb.ClientAPI | None = None, embedding_function: Any | None = None, create: bool = True):
    client = client or get_client()
    ef = embedding_function or get_embedding_function()
    if create:
        return client.get_or_create_collection(settings.chroma_collection, embedding_function=ef)
    return client.get_collection(settings.chroma_collection, embedding_function=ef)


def build_index(
    documents: list[Document] | None = None,
    rebuild: bool = False,
    docs_dir: str | None = None,
    embedding_function: Any | None = None,
) -> dict:
    """构建/更新索引；返回统计信息。rebuild=True 时先删除旧集合。"""
    docs = documents if documents is not None else load_documents(docs_dir)
    client = get_client()
    ef = embedding_function or get_embedding_function()

    if rebuild:
        try:
            client.delete_collection(settings.chroma_collection)
        except Exception:  # noqa: BLE001 —— 集合不存在时忽略
            pass

    collection = client.get_or_create_collection(settings.chroma_collection, embedding_function=ef)

    corpus_hash = sha256_text("".join(f"{d.source}:{d.sha256}" for d in docs))[:16]
    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict] = []
    per_source: dict[str, int] = {}

    for doc in docs:
        chunks = split_text(doc.text)
        per_source[doc.source] = len(chunks)
        for index, chunk in enumerate(chunks):
            ids.append(chunk_id(doc.source, index, chunk))
            texts.append(chunk)
            metadatas.append(
                {
                    "source": doc.source,
                    "chunk_index": index,
                    "doc_sha256": doc.sha256,
                    "corpus_version": corpus_hash,
                }
            )

    if ids:
        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)

    return {
        "documents": len(docs),
        "chunks": len(ids),
        "per_source": per_source,
        "collection": settings.chroma_collection,
        "collection_count": collection.count(),
        "corpus_version": corpus_hash,
        "rebuild": rebuild,
    }


def query(question: str, n_results: int = 3, collection: Any | None = None, embedding_function: Any | None = None) -> list[dict]:
    """检索相关 chunk；返回 [{text, source, chunk_index, distance}]。"""
    collection = collection or get_collection(embedding_function=embedding_function)
    response = collection.query(query_texts=[question], n_results=n_results)
    documents = (response.get("documents") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    results: list[dict] = []
    for index, text in enumerate(documents):
        meta = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        results.append(
            {
                "text": text,
                "source": (meta or {}).get("source", "未知"),
                "chunk_index": (meta or {}).get("chunk_index"),
                "distance": distance,
            }
        )
    return results
