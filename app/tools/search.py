"""网络搜索工具。

优先使用 Tavily（需要 API Key）；未配置 Key 或调用失败时，
自动回退到 DuckDuckGo 免费搜索。两者统一返回相同结构。

注意：DuckDuckGo 后端（Bing）在国内网络环境可能不可达，失败会向上抛出，
由调用方（SearcherAgent）如实记录降级，绝不把错误信息当作有效资料。
"""

from __future__ import annotations

import logging
import warnings

from app.config import settings

logger = logging.getLogger(__name__)

# duckduckgo-search 已更名为 ddgs，触发改名警告，此处静默处理
warnings.filterwarnings("ignore", message=r".*renamed to.*ddgs.*")


def _import_ddgs():
    """兼容 ddgs / duckduckgo-search 新旧版本的导入方式。"""
    try:
        from ddgs import DDGS  # 新包名（duckduckgo-search 已更名）
    except ImportError:
        from duckduckgo_search import DDGS  # 旧版本
    return DDGS


class WebSearchTool:
    """网络搜索工具，统一输出 ``[{"title", "content", "url"}]``。"""

    def __init__(self, tavily_api_key: str | None = None, max_results: int | None = None) -> None:
        self.tavily_api_key = tavily_api_key if tavily_api_key is not None else settings.tavily_api_key
        self.max_results = max_results or settings.search_max_results

    def search(self, query: str) -> list[dict]:
        """执行一次网络搜索；搜索失败时抛出异常，由上层记录并降级。"""
        if self.tavily_api_key:
            try:
                return self._search_tavily(query)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tavily 搜索失败，回退 DuckDuckGo：%s", exc)
        return self._search_duckduckgo(query)

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
                            "content": item.get("body", ""),
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