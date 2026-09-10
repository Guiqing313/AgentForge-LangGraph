"""本地知识库检索工具（ChromaDB + bge-m3 向量）。

与旧版的区别：
- 集合名来自配置（默认 agentforge_kb），不再硬编码 "default"；
- 使用自定义 embedding 函数（默认调用本地 bge-m3 服务），保证写入/查询同一向量空间；
- 知识库为空时返回 []；embedding 服务不可用时抛出明确异常（由 SearcherAgent 记录并降级）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class LocalSearchTool:
    """在本地 ChromaDB 知识库中检索相关文档片段。"""

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
        embedding_function: Any | None = None,
        n_results: int = 3,
    ) -> None:
        self.persist_dir = persist_dir or settings.chroma_persist_dir
        self.collection_name = collection_name or settings.chroma_collection
        self.embedding_function = embedding_function
        self.n_results = n_results

    def _get_embedding_function(self) -> Any:
        if self.embedding_function is not None:
            return self.embedding_function
        from app.kb.embedding import get_embedding_function

        return get_embedding_function()

    def search(self, query: str, collection_name: str | None = None, n_results: int | None = None) -> list[dict]:
        """返回 ``[{"title", "content", "url"}]``；空知识库返回空列表，服务错误向上抛出。"""
        try:
            import chromadb
        except ImportError:
            logger.warning("未安装 chromadb，本地知识库检索不可用")
            return []

        name = collection_name or self.collection_name
        limit = n_results or self.n_results
        try:
            client = chromadb.PersistentClient(path=self.persist_dir)
            collection = client.get_or_create_collection(name, embedding_function=self._get_embedding_function())
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库不可用：%s", exc)
            raise RuntimeError(f"知识库不可用：{exc}") from exc

        if collection.count() == 0:
            logger.info("知识库为空（collection=%s），请先运行 scripts/build_kb.py", name)
            return []

        try:
            response = collection.query(query_texts=[query], n_results=limit)
        except Exception as exc:  # noqa: BLE001 —— fail-closed：不静默返回空
            logger.warning("知识库检索失败：%s", exc)
            raise RuntimeError(f"知识库检索失败：{exc}") from exc

        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        results: list[dict] = []
        for index, doc in enumerate(documents):
            meta = metadatas[index] if index < len(metadatas) else {}
            results.append(
                {
                    "title": (meta or {}).get("source", "本地知识库"),
                    "content": doc,
                    "url": "",
                }
            )
        return results
