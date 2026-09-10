r"""构建 AgentForge 本地知识库索引。

用法（AgentForge venv；需先启动 embedding 服务）：
    D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe scripts\build_kb.py --rebuild
    ... --incremental          # 增量 upsert（默认）
    ... --fake                 # 用确定性假向量（离线/测试，不调用服务）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.kb.embedding import DeterministicHashEmbeddingFunction, get_embedding_function  # noqa: E402
from app.kb.indexer import build_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 AgentForge 本地知识库")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rebuild", action="store_true", help="删除并重建集合")
    group.add_argument("--incremental", action="store_true", help="增量 upsert（默认）")
    parser.add_argument("--docs-dir", default=None)
    parser.add_argument("--fake", action="store_true", help="使用确定性假向量（离线）")
    args = parser.parse_args()

    if args.fake:
        embedding_function = DeterministicHashEmbeddingFunction()
    else:
        embedding_function = get_embedding_function()
        health = getattr(embedding_function, "health", None)
        if callable(health):
            try:
                info = health()
                print(f"embedding 服务就绪：{json.dumps(info, ensure_ascii=False)}")
            except Exception as exc:  # noqa: BLE001
                print(f"embedding 服务不可用：{exc}")
                print("请先启动：D:\\ANACONDA\\envs\\pytorch_env\\python.exe scripts\\embed_server.py --port 11435")
                return 2

    stats = build_index(
        rebuild=args.rebuild,
        docs_dir=args.docs_dir,
        embedding_function=embedding_function,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())