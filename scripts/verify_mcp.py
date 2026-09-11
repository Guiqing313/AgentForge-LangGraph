r"""MCP 真实调用验证：用 fastmcp Client 通过 stdio 启动 app/mcp_server.py 并调用 local_search。

运行（venv-mcp）：
    <workspace>\venv-mcp\Scripts\python.exe scripts\verify_mcp.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "app" / "mcp_server.py"


async def main() -> int:
    from fastmcp import Client

    async with Client(SERVER) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        print("tools=" + json.dumps(names, ensure_ascii=False))
        result = await client.call_tool("local_search", {"query": "RAG 的完整流程是什么？", "n_results": 3})
        data = getattr(result, "data", None)
        if data is None:
            content = getattr(result, "content", None) or []
            text = " ".join(getattr(c, "text", "") for c in content)
            try:
                data = json.loads(text)
            except Exception:
                data = text
        print("result_type=" + type(data).__name__)
        print(json.dumps(data, ensure_ascii=False)[:1200])
        count = len(data) if isinstance(data, list) else 0
        print("MCP_LOCAL_SEARCH_COUNT=" + str(count))
        return 0 if count > 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
