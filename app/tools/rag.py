"""本地知识库检索工具（复用 ChromaDB）。"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


class LocalSearchTool:
    """在本地 ChromaDB 知识库中检索相关文档片段。"""

    def __init__(self, persist_dir: str | None = None) -> None:
        self.persist_dir = persist_dir or settings.chroma_persist_dir

    def search(self, query: str, collection_name: str = "default", n_results: int = 3) -> list[dict]:
        """返回 ``[{"title", "content", "url"}]``；知识库为空时返回空列表。"""
        try:
            import chromadb
        except ImportError:
            logger.warning("未安装 chromadb，本地知识库检索不可用")
            return []

        try:
            client = chromadb.PersistentClient(path=self.persist_dir)
            collection = client.get_collection(collection_name)
        except Exception as exc:  # noqa: BLE001
            logger.info("知识库不存在或不可用：%s", exc)
            return []

        try:
            response = collection.query(query_texts=[query], n_results=n_results)
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库检索失败：%s", exc)
            return []

        results: list[dict] = []
        docs = response.get("documents", [[]])[0]
        metas = response.get("metadatas", [[]])[0]
        for doc, meta in zip(docs, metas):
            results.append(
                {
                    "title": (meta or {}).get("source", "本地知识库"),
                    "content": doc,
                    "url": (meta or {}).get("url", ""),
                }
            )
        return results