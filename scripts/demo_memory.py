r"""A2 记忆演示：真实 embedding 服务 + 真实 Chroma。

用法（AgentForge venv，需 embedding 服务运行）：
    <repo>\venv\Scripts\python.exe scripts\demo_memory.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agents.planner import PlannerAgent  # noqa: E402
from app.services.memory_service import MemoryRecord, MemoryService  # noqa: E402


class CapturingLLM:
    def __init__(self) -> None:
        self.text = ""

    def invoke(self, messages, **kwargs):
        from app.llm.factory import _FakeMessage

        self.text = "\n".join(getattr(m, "content", "") for m in messages)
        return _FakeMessage('{"sub_questions": ["记忆注入成功"]}')


def main() -> int:
    service = MemoryService()
    before = service.count()

    record = MemoryRecord(
        topic="RAG 检索增强生成",
        sub_questions=["什么是 RAG", "混合检索怎么做"],
        key_findings=[
            "RAG 通过检索外部文档辅助大模型生成，可降低幻觉",
            "混合检索 = 向量检索 + BM25 关键词检索 + 融合 + 重排",
        ],
        source_count=6,
        task_id=900001,
        created_at="2026-09-10T12:00:00",
    )
    memory_id = service.save(record)
    after = service.count()
    hits = service.retrieve("RAG 检索增强", top_k=3)

    print(f"memory_id={memory_id}")
    print(f"count_before={before} count_after={after}")
    print("retrieved=" + json.dumps([{ "similarity": h["similarity"], "preview": h["document"][:80]} for h in hits], ensure_ascii=False))

    import app.agents.base as base_module

    fake = CapturingLLM()
    original = base_module.get_llm
    base_module.get_llm = lambda: fake
    try:
        memory_texts = [h["document"] for h in hits]
        result = PlannerAgent().plan("RAG 检索增强", memories=memory_texts)
    finally:
        base_module.get_llm = original

    injected = "参考背景" in fake.text and "RAG 检索增强" in fake.text
    print(f"planner_result={result}")
    print(f"planner_prompt_has_memory={injected}")
    print("DEMO_OK" if after > before and hits and injected else "DEMO_BAD")
    return 0 if after > before and hits and injected else 2


if __name__ == "__main__":
    raise SystemExit(main())
