"""AgentForge MCP Server：把现有工具暴露成标准 MCP 工具，供外部 Agent（Claude/Codex 等）调用。

启动方式（推荐，任意目录都能跑）：
    D:/codex使用文件夹/venv-mcp/Scripts/fastmcp.exe dev inspector app/mcp_server.py:mcp
"""
import sys
from pathlib import Path

# 关键：把 AgentForge 根目录加进 sys.path，保证 from app.tools... 在任何启动方式下都能找到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP  # noqa: E402

from app.tools.calculator import CalculatorTool  # noqa: E402
from app.tools.rag import LocalSearchTool  # noqa: E402
from app.tools.search import WebSearchTool  # noqa: E402

mcp = FastMCP("AgentForge")


@mcp.tool()
def web_search(query: str) -> list[dict]:
    """联网搜索：返回 [{title, content, url}]，用于获取最新或外部信息（优先 Tavily，无 Key 回退 DuckDuckGo）。"""
    return WebSearchTool().search(query)


@mcp.tool()
def local_search(query: str, n_results: int = 3) -> list[dict]:
    """本地知识库检索：从 AgentForge 的 ChromaDB 中检索相关文档片段，返回 [{title, content, url}]。"""
    return LocalSearchTool().search(query, n_results=n_results)


@mcp.tool()
def calculate(expression: str) -> str:
    """安全计算数学表达式（仅允许数字、四则运算与 math 函数），返回计算结果字符串。"""
    return CalculatorTool().calculate(expression)


if __name__ == "__main__":
    mcp.run()  # stdio 传输
