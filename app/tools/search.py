"""网络搜索工具。

优先使用 Tavily（需要 API Key）；未配置 Key 或调用失败时，
自动回退到 DuckDuckGo 免费搜索。两者统一返回相同结构。

A5 增加：
- 进程内查询缓存（相同 query 不重复计费，也让 DeepSeek 对比能复用同一批搜索结果）；
- ``last_backend`` 记录最近一次实际使用的后端（tavily / duckduckgo / cache），供用量与成本统计。

注意：DuckDuckGo 后端（Bing）在国内网络环境可能不可达，失败会向上抛出，
由调用方（SearcherAgent）如实记录降级，绝不把错误信息当作有效资料。
"""

from __future__ import annotations

import logging
import warnings

from app.config import settings

logger = logging.getLogger(__name__)

# 进程内搜索缓存：key = query，value = 结果列表
_SEARCH_CACHE: dict[str, list[dict]] = {}

# 外部搜索硬上限（A5 复测修复）：达到上限后不再发起 Tavily 调用
MAX_TAVILY_CALLS: int | None = None
TAVILY_CALL_COUNT = 0
MAX_TAVILY_CALLS_PER_TASK: int | None = None
TAVILY_TASK_COUNT = 0


def configure_limits(max_tavily_calls: int | None) -> None:
    global MAX_TAVILY_CALLS, TAVILY_CALL_COUNT
    MAX_TAVILY_CALLS = max_tavily_calls
    TAVILY_CALL_COUNT = 0


def tavily_calls_used() -> int:
    return TAVILY_CALL_COUNT


def start_task_limits(max_per_task: int | None) -> None:
    """每个任务开始前调用：设置并重置单任务 Tavily 上限。"""
    global MAX_TAVILY_CALLS_PER_TASK, TAVILY_TASK_COUNT
    MAX_TAVILY_CALLS_PER_TASK = max_per_task
    TAVILY_TASK_COUNT = 0


def tavily_calls_used_in_task() -> int:
    return TAVILY_TASK_COUNT


def _reserve_tavily_call() -> None:
    global TAVILY_CALL_COUNT, TAVILY_TASK_COUNT
    if MAX_TAVILY_CALLS is not None and TAVILY_CALL_COUNT >= MAX_TAVILY_CALLS:
        raise RuntimeError(f"Tavily 调用达到本阶段上限 {MAX_TAVILY_CALLS}，停止外部搜索")
    if MAX_TAVILY_CALLS_PER_TASK is not None and TAVILY_TASK_COUNT >= MAX_TAVILY_CALLS_PER_TASK:
        raise RuntimeError(f"Tavily 调用达到单任务上限 {MAX_TAVILY_CALLS_PER_TASK}，停止本任务外部搜索")
    TAVILY_CALL_COUNT += 1
    TAVILY_TASK_COUNT += 1

# duckduckgo-search 已更名为 ddgs，触发改名警告，此处静默处理
warnings.filterwarnings("ignore", message=r".*renamed to.*ddgs.*")


def _import_ddgs():
    """兼容 ddgs / duckduckgo-search 新旧版本的导入方式。"""
    try:
        from ddgs import DDGS  # 新包名（duckduckgo-search 已更名）
    except ImportError:
        from duckduckgo_search import DDGS  # 旧版本
    return DDGS


def clear_cache() -> None:
    _SEARCH_CACHE.clear()


def cache_size() -> int:
    return len(_SEARCH_CACHE)


class WebSearchTool:
    """网络搜索工具，统一输出 ``[{"title", "content", "url"}]``。"""

    def __init__(self, tavily_api_key: str | None = None, max_results: int | None = None, use_cache: bool = True) -> None:
        self.tavily_api_key = tavily_api_key if tavily_api_key is not None else settings.tavily_api_key
        self.max_results = max_results or settings.search_max_results
        self.use_cache = use_cache
        self.last_backend = "unknown"

    def search(self, query: str) -> list[dict]:
        """执行一次网络搜索；失败时抛出异常，由上层记录并降级。"""
        if self.use_cache and query in _SEARCH_CACHE:
            self.last_backend = "cache"
            return _SEARCH_CACHE[query]

        if self.tavily_api_key:
            # 硬上限：超出后直接抛出（由 SearcherAgent 记录降级），不得回退到其他外部搜索
            _reserve_tavily_call()
            try:
                results = self._search_tavily(query)
                self.last_backend = "tavily"
                if self.use_cache:
                    _SEARCH_CACHE[query] = results
                return results
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tavily 搜索失败，回退 DuckDuckGo：%s", exc)

        results = self._search_duckduckgo(query)
        self.last_backend = "duckduckgo"
        if self.use_cache:
            _SEARCH_CACHE[query] = results
        return results

    def _search_tavily(self, query: str) -> list[dict]:
        from tavily import TavilyClient

        client = TavilyClient(api_key=self.tavily_api_key)
        response = client.search(query, max_results=self.max_results, search_depth="basic")
        results = []
        for item in response.get("results", [])[: self.max_results]:
            results.append(
                {
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "url": item.get("url", ""),
                }
            )
        return results

    def _search_duckduckgo(self, query: str) -> list[dict]:
        DDGS = _import_ddgs()
        results = []
        try:
            with DDGS(timeout=8) as ddgs:
                for item in ddgs.text(query, max_results=self.max_results):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "body": item.get("body", ""),
                            "url": item.get("href", ""),
                        }
                    )
        except TypeError:
            # 旧版 DDGS 不支持 timeout 参数
            with DDGS() as ddgs:
                for item in ddgs.text(query, max_results=self.max_results):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "content": item.get("body", ""),
                            "url": item.get("href", ""),
                        }
                    )
        return results
