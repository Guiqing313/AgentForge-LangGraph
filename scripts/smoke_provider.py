r"""Provider 冒烟脚本：验证当前 provider 能真实返回可用 JSON。

用法：
    D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe scripts\smoke_provider.py
    # 需要本地 Ollama 已启动；如要测 DeepSeek，设置 LLM_PROVIDER=deepseek

说明：本脚本会产生真实调用（Ollama 本地成本 0；DeepSeek 付费，谨慎使用）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agents.base import _make_message, extract_json  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm.factory import get_llm, get_provider_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider JSON 冒烟测试")
    parser.add_argument("--topic", default="RAG 与 Agent 的区别", help="用于生成 JSON 的主题")
    args = parser.parse_args()

    provider = get_provider_name()
    llm = get_llm()
    prompt = (
        "请只输出 JSON，不要任何解释文字。格式：\n"
        '{"sub_questions": ["子问题1", "子问题2"]}\n'
        f"研究主题：{args.topic}"
    )

    print(f"provider={provider} model={settings.ollama_model if provider == 'ollama' else settings.deepseek_model if provider == 'deepseek' else 'mock'}")
    start = time.perf_counter()
    response = llm.invoke([_make_message("human", prompt)])
    elapsed = time.perf_counter() - start
    raw = response.content
    print(f"latency_seconds={elapsed:.2f}")
    print(f"raw_prefix={raw[:200]!r}")
    try:
        parsed = extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"JSON_PARSE_FAILED: {exc}")
        return 1
    print("parsed=" + json.dumps(parsed, ensure_ascii=False)[:400])
    ok = isinstance(parsed, dict) and isinstance(parsed.get("sub_questions"), list)
    print("SMOKE_OK" if ok else "SMOKE_BAD_SHAPE")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())