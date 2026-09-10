"""应用配置模块。

集中管理所有配置项，支持项目根目录 .env 文件与环境变量覆盖。
设计原则：
- 所有 secret（API Key）缺失时给出清晰错误，而非运行时突然崩溃；
- 提供安全默认值，保证 mock 模式（无 key）也能跑通流程；
- 通过 LLM_PROVIDER 选择 ollama（默认，本地）/ deepseek（付费对比）/ mock（离线测试）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:  # 未安装 python-dotenv 时静默跳过，仅依赖真实环境变量
    pass


def _get(key: str, default: str = "") -> str:
    """读取环境变量，空字符串视同未设置。"""
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def _get_float(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """全局配置对象（frozen，避免运行期被意外修改）。"""

    # ---- LLM provider 选择：ollama | deepseek | mock ----
    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "ollama").strip().lower())

    # ---- Ollama（本地，默认 provider；无 API 成本） ----
    ollama_base_url: str = field(default_factory=lambda: _get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"))
    ollama_model: str = field(default_factory=lambda: _get("OLLAMA_MODEL", "qwen2.5:7b"))

    # ---- DeepSeek（付费对比，仅 1 次实验） ----
    deepseek_api_key: str = field(default_factory=lambda: _get("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    # 官方兼容模型名（DeepSeek 官方推荐 deepseek-chat / deepseek-reasoner）
    deepseek_model: str = field(default_factory=lambda: _get("DEEPSEEK_MODEL", "deepseek-chat"))

    llm_temperature: float = field(default_factory=lambda: _get_float("LLM_TEMPERATURE", 0.3))
    llm_max_tokens: int = field(default_factory=lambda: _get_int("LLM_MAX_TOKENS", 4096))

    # ---- 网络搜索 ----
    tavily_api_key: str = field(default_factory=lambda: _get("TAVILY_API_KEY", ""))
    search_max_results: int = field(default_factory=lambda: _get_int("SEARCH_MAX_RESULTS", 3))

    # ---- 向量库（RAG 工具与长期记忆共用） ----
    chroma_persist_dir: str = field(default_factory=lambda: _get("CHROMA_PERSIST_DIR", str(BASE_DIR / "data" / "chroma")))
    chroma_collection: str = field(default_factory=lambda: _get("CHROMA_COLLECTION", "agentforge_kb"))
    memory_collection: str = field(default_factory=lambda: _get("MEMORY_COLLECTION", "agent_memory"))

    # ---- Embedding（A1：本地 bge-m3 HTTP 服务，复用 SmartKB2.0 权重） ----
    embedding_provider: str = field(default_factory=lambda: _get("EMBEDDING_PROVIDER", "http").strip().lower())
    embedding_base_url: str = field(default_factory=lambda: _get("EMBEDDING_BASE_URL", "http://127.0.0.1:11435"))
    embedding_model: str = field(default_factory=lambda: _get("EMBEDDING_MODEL", "bge-m3"))
    embedding_dim: int = field(default_factory=lambda: _get_int("EMBEDDING_DIM", 1024))

    # ---- 知识库文档与分块 ----
    docs_dir: str = field(default_factory=lambda: _get("DOCS_DIR", str(BASE_DIR / "docs" / "kb")))
    chunk_size: int = field(default_factory=lambda: _get_int("CHUNK_SIZE", 500))
    chunk_overlap: int = field(default_factory=lambda: _get_int("CHUNK_OVERLAP", 50))
    # ---- 数据库 ----
    database_url: str = field(default_factory=lambda: _get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'agentforge.db'}"))

    # ---- 工作流 ----
    max_review_rounds: int = field(default_factory=lambda: _get_int("MAX_REVIEW_ROUNDS", 2))
    review_pass_score: int = field(default_factory=lambda: _get_int("REVIEW_PASS_SCORE", 7))
    max_sub_questions: int = field(default_factory=lambda: _get_int("MAX_SUB_QUESTIONS", 5))

    # ---- 运行模式（向后兼容）：mock 时强制离线；live 时按 llm_provider 选择 ----
    llm_mode: str = field(default_factory=lambda: _get("LLM_MODE", "live").strip().lower())

    @property
    def effective_provider(self) -> str:
        """真实生效的 provider（考虑 mock 模式与 DeepSeek 缺 key 的降级）。"""
        if self.llm_mode == "mock":
            return "mock"
        provider = self.llm_provider if self.llm_provider in ("ollama", "deepseek", "mock") else "ollama"
        if provider == "deepseek" and not self.deepseek_api_key:
            return "mock"
        return provider

    @property
    def llm_configured(self) -> bool:
        """当前是否具备真实调用条件（Ollama 本地视为已配置）。"""
        return self.effective_provider != "mock"

    def validate_for_live(self) -> None:
        """真实运行前校验必要配置，缺失时抛出可读错误。"""
        provider = self.effective_provider
        if provider == "mock":
            raise RuntimeError(
                "当前为 mock 模式（LLM_MODE=mock，或 LLM_PROVIDER=deepseek 但缺少 DEEPSEEK_API_KEY）。"
                "请在 .env 配置 LLM_PROVIDER=ollama 使用本地模型，或配置 DeepSeek key。"
            )
        if provider == "deepseek" and not self.deepseek_api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY。请在项目根目录 .env 中配置。")


settings = Settings()