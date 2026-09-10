"""跨任务经验记忆（ChromaDB + bge-m3）。

定位说明（重要）：
- 本模块只做「已完成任务的经验复用」——把主题、子问题、关键发现写入向量库，
  后续相似主题在规划前检索参考；
- 它**不是**完整的短期/长期记忆系统；短期对话/图状态由 checkpoint（B1）负责；
- 对外表述只能是"跨任务经验记忆"，直到实现与测试齐全并经用户确认。

失败策略：记忆检索/写入失败时降级为"无记忆"并记录日志，不阻塞主任务。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

NAMESPACE = uuid.UUID("b1c9d0e2-6f4a-4b3d-9c1e-2a7d5f8e0c11")


@dataclass(frozen=True)
class MemoryRecord:
    """一次已完成任务的经验记录。"""

    topic: str
    sub_questions: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    source_count: int = 0
    task_id: int | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def memory_id(self) -> str:
        """确定性 id：同 topic/task_id/created_at 稳定，不依赖 Python hash()。"""
        return str(uuid.uuid5(NAMESPACE, f"{self.topic}:{self.task_id}:{self.created_at}"))

    def to_document(self) -> str:
        questions = "\n".join(f"- {q}" for q in self.sub_questions[:10])
        findings = "\n".join(f"- {f}" for f in self.key_findings[:20])
        return (
            f"主题：{self.topic}\n"
            f"子问题：\n{questions}\n"
            f"关键发现：\n{findings}\n"
            f"来源数量：{self.source_count}\n"
            f"完成时间：{self.created_at}"
        )

    @classmethod
    def from_state(cls, topic: str, task_id: int | None, state: dict) -> "MemoryRecord":
        analysis = state.get("analysis_results") or {}
        findings: list[str] = []
        for item in analysis.values():
            for finding in (item or {}).get("key_findings", []) or []:
                if isinstance(finding, str) and finding.strip():
                    findings.append(finding.strip())
        search_results = state.get("search_results") or []
        source_count = 0
        for entry in search_results:
            source_count += len((entry or {}).get("documents", []) or [])
        return cls(
            topic=topic,
            sub_questions=[q for q in (state.get("sub_questions") or []) if isinstance(q, str)],
            key_findings=findings,
            source_count=source_count,
            task_id=task_id,
        )


class MemoryService:
    """基于 ChromaDB 的跨任务经验记忆。"""

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
        embedding_function: Any | None = None,
    ) -> None:
        self.persist_dir = persist_dir or settings.chroma_persist_dir
        self.collection_name = collection_name or settings.memory_collection
        self.embedding_function = embedding_function

    def _get_embedding_function(self) -> Any:
        if self.embedding_function is not None:
            return self.embedding_function
        from app.kb.embedding import get_embedding_function

        return get_embedding_function()

    def _collection(self):
        import chromadb

        client = chromadb.PersistentClient(path=self.persist_dir)
        return client.get_or_create_collection(
            self.collection_name,
            embedding_function=self._get_embedding_function(),
        )

    def count(self) -> int:
        try:
            return self._collection().count()
        except Exception as exc:  # noqa: BLE001
            logger.info("读取记忆数量失败：%s", exc)
            return 0

    def save(self, record: MemoryRecord) -> str:
        collection = self._collection()
        memory_id = record.memory_id()
        collection.upsert(
            ids=[memory_id],
            documents=[record.to_document()],
            metadatas=[
                {
                    "topic": record.topic,
                    "task_id": record.task_id if record.task_id is not None else -1,
                    "source_count": record.source_count,
                    "created_at": record.created_at,
                }
            ],
        )
        return memory_id

    def retrieve(
        self,
        topic: str,
        top_k: int | None = None,
        min_similarity: float | None = None,
        max_chars: int | None = None,
    ) -> list[dict]:
        """返回 [{document, similarity, metadata}]；无记忆时返回 []，失败时抛出异常。"""
        top_k = top_k or settings.memory_top_k
        min_similarity = settings.memory_min_similarity if min_similarity is None else min_similarity
        max_chars = max_chars or settings.memory_max_chars

        collection = self._collection()
        total = collection.count()
        if total == 0:
            return []

        response = collection.query(query_texts=[topic], n_results=min(max(top_k * 3, 6), total))
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]

        results: list[dict] = []
        for index, document in enumerate(documents):
            distance = distances[index] if index < len(distances) else None
            similarity = 1.0 - float(distance) if distance is not None else None
            if min_similarity is not None and similarity is not None and similarity < min_similarity:
                continue
            results.append(
                {
                    "document": document[:max_chars] if max_chars else document,
                    "similarity": round(similarity, 4) if similarity is not None else None,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                }
            )
        results.sort(key=lambda item: item["similarity"] if item["similarity"] is not None else -1, reverse=True)
        return results[:top_k]

    # ---- 向后兼容的旧接口（当前主流程不依赖） ----
    def save_experience(self, topic: str, summary: str, findings: list[str]) -> None:
        record = MemoryRecord(
            topic=topic,
            sub_questions=[],
            key_findings=([summary] if summary else []) + [f for f in findings if isinstance(f, str)],
            source_count=0,
        )
        self.save(record)

    def retrieve_experience(self, topic: str, top_k: int = 3) -> list[str]:
        try:
            return [item["document"] for item in self.retrieve(topic, top_k=top_k)]
        except Exception as exc:  # noqa: BLE001
            logger.info("检索长期记忆失败：%s", exc)
            return []