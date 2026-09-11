# A4 CI + API/失败路径测试 + 依赖锁定（已完成）

日期：2026-09-10 ｜ 状态：✅ 通过 ｜ 外部 API 成本：0 元

## 1. 目标
- 建立可复现的 CI（Python 3.12：install → ruff → pytest）；
- 补 API 层与失败路径测试（此前只有单元/图测试）；
- 锁定依赖版本，防止环境漂移；
- 测试使用临时 SQLite，不污染真实数据。

## 2. 交付文件
| 文件 | 说明 |
|---|---|
| `.github/workflows/ci.yml` | Python 3.12；`pip install -r requirements-lock.txt`；`ruff check .`；`pytest -q` |
| `pyproject.toml` | ruff（line-length 120、E/F/W/I）与 pytest 配置；排除 venv/data/docs |
| `requirements.txt` / `requirements-lock.txt` | 直接依赖精确锁定（见下表） |
| `tests/conftest.py` | 在 import app 前设置临时 `DATABASE_URL`（tempfile）+ `LLM_MODE=mock` |
| `tests/test_api.py` | TestClient：create/list/get/report 409→200/delete 404→200/running 409（后台执行用 monkeypatch 屏蔽） |
| `tests/test_failure_paths.py` | 搜索失败降级、空结果标记、analyzer 无证据不编造、writer 空发现标记、JSON 解析失败计数 |

## 3. 依赖锁定（关键）
```
fastapi==0.141.1        uvicorn[standard]==0.52.3   python-dotenv==1.2.2
pydantic==2.13.4        openai==3.1.0
langchain==1.3.15       langchain-core==1.5.5        langchain-openai==1.5.1
langchain-community==0.4.2  langchain-text-splitters==1.1.2
langgraph==1.2.11       langgraph-checkpoint==4.2.0  langgraph-checkpoint-sqlite==3.1.1
chromadb==1.5.9         tavily-python==0.7.27        duckduckgo-search==8.1.1
sqlalchemy==2.0.52      aiosqlite==0.22.1            streamlit==1.61.1
pytest==9.1.1           httpx==0.28.1                ruff==0.16.6
fastmcp==4.0.3
```
说明：`langgraph-checkpoint-sqlite==3.1.1` 为 B1 预留（dry-run 已确认只新增 sqlite-vec，不升级 langgraph）；`fastmcp` 的本地运行环境仍是 `venv-mcp`。

## 4. 验证证据
```
<repo>\venv\Scripts\python.exe -m pytest
51 passed in 3.07s

... -m ruff check .
All checks passed!
```
- ruff 首次检查 54 项（导入排序/行尾换行/未用导入），`ruff check --fix` 全部修复；修复后 pytest 仍 51 passed。
- 本地已安装 `ruff==0.16.6`（standalone，无传递依赖）；安装前已保存 `pip-freeze-before-ruff.txt`，符合风险登记 T2 的"安装前后备份 + 回归"要求。

## 5. 诚实边界
- GitHub Actions **尚未实际运行**（需要用户推送后触发）；本地等价命令（pytest + ruff）已全绿。
- `tests/test_api.py` 通过 monkeypatch 屏蔽后台执行来避免 TestClient 事件循环不稳定；后台 worker 的真实并发测试由 B1/B2 补充。
- 失败路径测试验证的是"代码层不把错误当资料 + prompt 明确空结果语义"，模型是否遵守仍由真实运行验证（A5）。
- CI 安装 `fastmcp==4.0.3`，但当前没有测试导入它；MCP 的真实 stdio 验证由 `scripts/verify_mcp.py`（venv-mcp）完成。

## 6. 下一步
A5：本地 live（Ollama 2 主题）+ 成本闸门（DeepSeek 1 次对比 ≤2 元，需用户确认后执行）。