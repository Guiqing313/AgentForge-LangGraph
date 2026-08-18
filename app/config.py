"""应用配置模块。

集中管理所有配置项，支持项目根目录 .env 文件与环境变量覆盖。
设计原则：
- 所有 secret（API Key）缺失时给出清晰错误，而非运行时突然崩溃；
- 提供安全默认值，保证 mock 模式（无 key）也能跑通流程。
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

    # ---- LLM ----
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

    # ---- 数据库 ----
    database_url: str = field(default_factory=lambda: _get("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'agentforge.db'}"))

    # ---- 工作流 ----
    max_review_rounds: int = field(default_factory=lambda: _get_int("MAX_REVIEW_ROUNDS", 2))
    review_pass_score: int = field(default_factory=lambda: _get_int("REVIEW_PASS_SCORE", 7))
    max_sub_questions: int = field(default_factory=lambda: _get_int("MAX_SUB_QUESTIONS", 5))

    # ---- 运行模式：live（真实 LLM）/ mock（离线验证编排逻辑） ----
    llm_mode: str = field(default_factory=lambda: _get("LLM_MODE", "live").strip().lower())

    @property
    def llm_configured(self) -> bool:
        """是否已配置真实 LLM 所需的 API Key。"""
        return bool(self.deepseek_api_key)

    def validate_for_live(self) -> None:
        """真实运行前校验必要配置，缺失时抛出可读错误。"""
        if not self.deepseek_api_key:
            raise RuntimeError(
                "缺少 DEEPSEEK_API_KEY。请在项目根目录 .env 中配置，"
                "或设置 LLM_MODE=mock 进行离线流程验证。"
            )


settings = Settings()