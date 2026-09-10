"""A2：跨任务经验记忆测试（离线，确定性假向量）。"""

from dataclasses import replace

from app.config import settings
from app.kb.embedding import DeterministicHashEmbeddingFunction
from app.llm.factory import MockLLM
from app.services.memory_service import MemoryRecord, MemoryService


def _service(tmp_path, name="test_memory"):
    return MemoryService(
        persist_dir=str(tmp_path / "chroma"),
        collection_name=name,
        embedding_function=DeterministicHashEmbeddingFunction(dim=64),
    )


def test_memory_id_deterministic():
    a = MemoryRecord(topic="RAG", task_id=1, created_at="2026-09-10T10:00:00")
    b = MemoryRecord(topic="RAG", task_id=1, created_at="2026-09-10T10:00:00")
    c = MemoryRecord(topic="RAG", task_id=2, created_at="2026-09-10T10:00:00")
    assert a.memory_id() == b.memory_id()
    assert a.memory_id() != c.memory_id()


def test_memory_save_and_retrieve(tmp_path):
    service = _service(tmp_path)
    assert service.count() == 0
    record = MemoryRecord(
        topic="RAG 检索增强生成",
        sub_questions=["什么是 RAG", "RAG 的流程"],
        key_findings=["RAG 通过检索文档辅助生成", "引用溯源可以降低幻觉"],
        source_count=5,
        task_id=101,
    )
    memory_id = service.save(record)
    assert memory_id == record.memory_id()
    assert service.count() == 1

    hits = service.retrieve("RAG 检索增强", top_k=3, min_similarity=-1.0)
    assert hits and hits[0]["metadata"]["task_id"] == 101
    assert "RAG" in hits[0]["document"]


def test_memory_min_similarity_filters(tmp_path):
    service = _service(tmp_path)
    service.save(MemoryRecord(topic="完全无关的主题", key_findings=["无关内容"], task_id=1))
    hits = service.retrieve("RAG 检索增强生成", top_k=3, min_similarity=0.999)
    assert hits == []


def test_memory_empty_collection_returns_empty(tmp_path):
    service = _service(tmp_path)
    assert service.retrieve("任意主题") == []


def test_planner_injects_memory(monkeypatch):
    captured = {}

    class CapturingLLM:
        def invoke(self, messages, **kwargs):
            captured["text"] = "\n".join(getattr(m, "content", "") for m in messages)
            from app.llm.factory import _FakeMessage

            return _FakeMessage('{"sub_questions": ["记忆注入成功"]}')

    monkeypatch.setattr("app.agents.base.get_llm", lambda: CapturingLLM())

    from app.agents.planner import PlannerAgent

    result = PlannerAgent().plan("RAG 检索增强", memories=["记忆标记：RAG 通过检索文档辅助生成"])
    assert result == ["记忆注入成功"]
    assert "参考背景" in captured["text"]
    assert "记忆标记" in captured["text"]

    # 无记忆时不应出现参考背景段落
    PlannerAgent().plan("RAG 检索增强")
    assert "参考背景" not in captured["text"]


def test_memory_service_uses_settings_defaults():
    assert settings.memory_enabled is True
    assert settings.memory_top_k >= 1
    assert settings.memory_max_chars >= 100
