"""Embedding 函数：调用本地 bge-m3 HTTP 服务，并提供离线确定性 fake 实现。

为什么不让 AgentForge 直接加载 bge-m3：
- AgentForge venv 没有 torch/FlagEmbedding，直接安装会带来数 GB 依赖与版本冲突风险；
- 用户的 pytorch_env 已有可用的 bge-m3，本地 HTTP 服务复用同一份权重，零下载、零重依赖。
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import requests
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.utils.embedding_functions import register_embedding_function


@register_embedding_function
class HttpBgeM3EmbeddingFunction(EmbeddingFunction[Documents]):
    """通过本地 HTTP 服务获取 bge-m3 向量（默认 1024 维，cosine）。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11435",
        model: str = "bge-m3",
        dim: int = 1024,
        timeout: int = 180,
        max_batch: int = 16,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self.timeout = timeout
        self.max_batch = max_batch

    def __call__(self, input: Documents) -> Embeddings:
        texts = [str(t) for t in input]
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.max_batch):
            batch = texts[start : start + self.max_batch]
            response = requests.post(
                f"{self.base_url}/embed",
                json={"texts": batch},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            vectors = payload.get("embeddings") or []
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"embedding 服务返回数量不匹配：期望 {len(batch)}，实际 {len(vectors)}"
                )
            embeddings.extend([list(map(float, v)) for v in vectors])
        return embeddings

    def health(self) -> dict:
        response = requests.get(f"{self.base_url}/health", timeout=10)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def name() -> str:
        return "agentforge-http-bge-m3"

    def get_config(self) -> dict:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "dim": self.dim,
            "timeout": self.timeout,
            "max_batch": self.max_batch,
        }

    @staticmethod
    def build_from_config(config: dict) -> "HttpBgeM3EmbeddingFunction":
        return HttpBgeM3EmbeddingFunction(**config)

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]


@register_embedding_function
class DeterministicHashEmbeddingFunction(EmbeddingFunction[Documents]):
    """确定性假向量（CI/离线测试用，不访问网络）。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def __call__(self, input: Documents) -> Embeddings:
        vectors: list[list[float]] = []
        for text in input:
            digest = hashlib.sha256(str(text).encode("utf-8")).digest()
            raw = (digest * ((self.dim * 4 // len(digest)) + 1))[: self.dim * 4]
            vec: list[float] = []
            for i in range(self.dim):
                chunk = raw[i * 4 : i * 4 + 4]
                value = int.from_bytes(chunk, "big") / 2**32 * 2 - 1
                vec.append(value)
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    @staticmethod
    def name() -> str:
        return "agentforge-deterministic-hash"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict) -> "DeterministicHashEmbeddingFunction":
        return DeterministicHashEmbeddingFunction(**config)

    def default_space(self) -> str:
        return "cosine"


def get_embedding_function() -> EmbeddingFunction[Documents]:
    """按配置返回 embedding 函数；EMBEDDING_PROVIDER=fake 时返回确定性假实现。"""
    from app.config import settings

    if settings.embedding_provider == "fake":
        return DeterministicHashEmbeddingFunction()
    return HttpBgeM3EmbeddingFunction(
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dim=settings.embedding_dim,
    )