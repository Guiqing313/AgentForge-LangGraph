"""长期记忆服务（跨任务经验复用）。

把每个已完成任务的核心结论写入 ChromaDB，后续相似主题任务可在规划前
检索相关历史经验。该服务独立可用，核心流程不强依赖它。
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class MemoryService:
    """基于 ChromaDB 的长期记忆。"""

    COLLECTION = "agent_memory"

    def __init__(self, persist_dir: str | None = None) -> None:
        self.persist_dir = persist_dir or settings.chroma_persist_dir

    def _client(self):
        import chromadb

        return chromadb.PersistentClient(path=self.persist_dir)

    def save_experience(self, topic: str, summary: str, findings: list[str]) -> None:
        try:
            client = self._client()
            collection = client.get_or_create_collection(self.COLLECTION)
            document = f"主题：{topic}\n总结：{summary}\n关键发现：\n" + "\n".join(
                f"- {f}" for f in findings
            )
            collection.upsert(
                ids=[str(abs(hash(topic)))[:20]],
                documents=[document],
                metadatas=[{"topic": topic}],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("保存长期记忆失败：%s", exc)

    def retrieve_experience(self, topic: str, top_k: int = 3) -> list[str]:
        try:
            client = self._client()
            collection = client.get_or_create_collection(self.COLLECTION)
            result = collection.query(query_texts=[topic], n_results=top_k)
            return result.get("documents", [[]])[0]
        except Exception as exc:  # noqa: BLE001
            logger.info("检索长期记忆失败：%s", exc)
            return []