r"""本地 bge-m3 embedding 服务（用 pytorch_env 启动，供 AgentForge 通过 HTTP 调用）。

启动（在 AgentForge-v2 目录下）：
    D:\ANACONDA\envs\pytorch_env\python.exe scripts\embed_server.py --port 11435

自检（只加载模型并编码一次，不启动服务）：
    D:\ANACONDA\envs\pytorch_env\python.exe scripts\embed_server.py --check

设计说明：
- 复用 D:\codex使用文件夹\SmartKB2.0\models\bge-m3 本地权重，不重新下载；
- 不向 AgentForge venv 安装 torch/FlagEmbedding；
- 服务不可用时 AgentForge 侧 fail-closed（local_search 抛错，由 SearcherAgent 记录降级）。
"""

from __future__ import annotations

import argparse
import threading
import time

from fastapi import FastAPI
from pydantic import BaseModel

DEFAULT_MODEL_PATH = r"D:/codex使用文件夹/SmartKB2.0/models/bge-m3"

app = FastAPI(title="AgentForge Embedding Service", version="0.1.0")

_model = None
_model_lock = threading.Lock()
_model_path = DEFAULT_MODEL_PATH


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from FlagEmbedding import BGEM3FlagModel

                _model = BGEM3FlagModel(_model_path, use_fp16=True)
    return _model


class EmbedRequest(BaseModel):
    texts: list[str]


@app.get("/health")
def health() -> dict:
    loaded = _model is not None
    return {"status": "ok", "model": "bge-m3", "dim": 1024, "loaded": loaded, "model_path": _model_path}


@app.post("/embed")
def embed(request: EmbedRequest) -> dict:
    texts = [t for t in request.texts if isinstance(t, str)]
    if not texts:
        return {"embeddings": [], "dim": 1024, "model": "bge-m3"}
    model = get_model()
    vectors = model.encode(texts, return_dense=True)["dense_vecs"]
    return {
        "embeddings": [v.tolist() for v in vectors],
        "dim": int(vectors.shape[1]),
        "model": "bge-m3",
    }


def main() -> int:
    global _model_path
    parser = argparse.ArgumentParser(description="AgentForge bge-m3 embedding 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--check", action="store_true", help="只做模型加载与编码自检")
    args = parser.parse_args()

    _model_path = args.model_path

    if args.check:
        started = time.perf_counter()
        model = get_model()
        vectors = model.encode(["RAG 是检索增强生成"], return_dense=True)["dense_vecs"]
        print(f"model_path={_model_path}")
        print(f"dim={vectors.shape}")
        print(f"load_and_encode_seconds={time.perf_counter() - started:.1f}")
        return 0

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())