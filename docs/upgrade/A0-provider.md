# A0 Provider 抽象 + UsageTracker（已完成）

日期：2026-09-10 ｜ 状态：✅ 通过 ｜ 成本：0 元（本地 Ollama）

## 1. 目标
- 引入 `LLM_PROVIDER=ollama|deepseek|mock`，默认本地 Ollama（无 API 成本）；
- 提供按任务维度的用量/耗时追踪骨架（`UsageTracker`），为 B3 指标打基础；
- 不破坏现有 22 项测试与 mock 离线能力。

## 2. 改动文件
| 文件 | 说明 |
|---|---|
| `app/config.py` | 新增 `llm_provider` / `ollama_base_url` / `ollama_model` / `effective_provider`；DeepSeek 缺 key 自动降级 mock；Ollama 视为已配置 |
| `app/llm/factory.py` | `get_llm()` 支持 ollama / deepseek / mock；新增 `get_provider_name()` |
| `app/observability.py` | 新增 `UsageTracker` + `track()`（contextvars），记录 LLM 调用/搜索/json 解析失败 |
| `app/agents/base.py` | `_chat` 记录 provider/model/latency/token（缺失记 None）、失败记录；`_chat_json` 记录解析失败 |
| `scripts/smoke_provider.py` | 新增 provider 冒烟脚本（真实调用，Ollama 成本 0） |
| `tests/test_provider.py` | 新增 6 项离线测试（provider 选择、降级、tracker、agent 记录） |

## 3. 选择规则（effective_provider）
| 配置 | 结果 |
|---|---|
| `LLM_MODE=mock` | 强制 mock（CI/离线） |
| `LLM_PROVIDER=ollama`（默认） | 本地 Ollama，`LLM_MODE=live` 时生效 |
| `LLM_PROVIDER=deepseek` 且有 key | DeepSeek（仅 1 次对比实验使用） |
| `LLM_PROVIDER=deepseek` 无 key | 自动降级 mock |

## 4. 验证证据

### 4.1 单元/集成测试
```
<repo>\venv\Scripts\python.exe -m pytest -q
28 passed in 2.82s
```
（22 项基线 + 6 项新增；离线，无外部调用）

### 4.2 真实 Ollama JSON 冒烟
命令：
```powershell
$env:LLM_PROVIDER="ollama"; $env:LLM_MODE="live"
<repo>\venv\Scripts\python.exe scripts\smoke_provider.py --topic "RAG 与 Agent 的区别"
```
输出（UTF-8）：
```
provider=ollama model=qwen2.5:7b
latency_seconds=1.33
raw_prefix='{"sub_questions": ["RAG和Agent的概念分别是什么？", "RAG和Agent在功能上的主要差异有哪些？"]}'
parsed={"sub_questions": ["RAG和Agent的概念分别是什么？", "RAG和Agent在功能上的主要差异有哪些？"]}
SMOKE_OK
```
结论：本地 Qwen2.5-7B 能稳定按提示返回可解析 JSON；provider 抽象打通。

## 5. 成本
- Ollama 本地调用：0 元外部支出。
- 本任务未调用 DeepSeek / Tavily。

## 6. 遗留（由后续任务处理）
- `scripts/run_e2e.py` 在 mock 模式下仍无条件 `validate_for_live()` → A3 修复。
- token 统计：Ollama OpenAI 兼容端点是否返回 usage 未实测；缺失时记 `null`（B3 会补原生 `/api/chat` 方案）。
- `UsageTracker` 尚未接入任务生命周期与 metrics API → B3。