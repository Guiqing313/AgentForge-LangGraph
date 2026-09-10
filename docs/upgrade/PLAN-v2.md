# AgentForge v2.0 最终行动方案（已获用户批准执行）

> 批准时间：2026-09-10。执行分支：`codex/agentforge-upgrade`；执行 worktree：`D:\codex使用文件夹\AgentForge-v2`。
> 基线提交：`498e446 加入mcp服务`。
> 协作方式：**AI 全程执行，用户只在 Gate 审核**；任何依赖/破坏性变更即时询问。

---

## 0. 决策基线（用户已确认，不得擅自更改）

1. 目标岗位：主投 AI 应用工程师，同时具备 AI Agent 能力；项目定位明确偏向 Agent。
2. 执行方式：AI 全程接管，用户只在 Gate 处审核。
3. 环境：Ollama 可用（`qwen2.5:7b` + `nomic-embed-text` 已有 manifest，位于 `D:\OllamaModels`）；Docker 未装，用户愿意在 Phase A/B 后决定是否安装。
4. 交付形态：仅本地演示，不做公网部署 / 鉴权体系。
5. 测试成本：≤10 元人民币（口径 = 外部 API 现金支出；本地 Ollama 计 0）。
6. 必做功能：Memory（记忆）+ interrupt/resume（人机协同）。
7. 汇报粒度：每个 Gate 汇报一次；任何依赖/破坏性变更立即询问。
8. DeepSeek：保留且仅保留 1 次对比实验（≤2 元）；其余默认走本地 Ollama。
9. Docker：Phase A/B 完成后再由用户决定。
10. SSE：不做到断线续传。

### 本轮（2026-09-10）5 项拍板结果
| 问题 | 用户选择 | 落地方式 |
|---|---|---|
| 知识库语料 | **1A** | 只用用户自写学习笔记 + AgentForge 自身文档，共 6 篇（见 A1）；已扫描无 key/无 PII |
| embedding | **2B** | 复用本地 `SmartKB2.0/models/bge-m3` 权重；**通过本地 embedding 服务调用**，不向 AgentForge venv 安装 torch/FlagEmbedding、不重新下载模型 |
| worker 架构 | **3A** | 单进程 worker（FastAPI lifespan 内后台协程 + DB 轮询 + 原子 claim） |
| SSE 范围 | **4A** | 只做后端 SSE 接口 + 自动化测试；Streamlit 保留轮询 |
| 时间 | **5A** | 净执行 8–12 个 AI 工作日（不含用户 Gate 等待），保留 Memory + interrupt/resume |

---

## 1. 目标与非目标

### 目标（按优先级）
1. 把"空壳知识库"变成真实可检索的知识库，并给出可量化检索质量（hit_rate@3 / MRR）。
2. 接通跨任务经验记忆（Memory），并证明第二次相似任务能复用第一次的结果。
3. 实现 interrupt/resume 人机协同：planner 后暂停、用户编辑子问题、恢复执行、进程重启仍可恢复。
4. 补齐工程可靠性：provider 抽象、成本闸门、指标、CI、回归测试、一致性修复。
5. 更新 README 与主张—证据账本，使对外表述与代码一致。

### 非目标（本轮不做）
- 公网部署、鉴权、多租户；
- Docker 硬化（C1，Phase A/B 后再定）；
- YAML 配置化 / fast-standard-deep 模板（C2，账本保持"不采用"）；
- 微调（P2-2 失败案例已记录，不在本轮）；
- SSE 断线续传；
- 把项目描述成"生产级"。

---

## 2. 执行协议

- **worktree 隔离**：所有改造在 `D:\codex使用文件夹\AgentForge-v2`（分支 `codex/agentforge-upgrade`）执行；主工作区 `D:\codex使用文件夹\AgentForge` 不动（保留其 venv 与 data 供运行）。
- **一个任务 = 一个 commit**；每个任务产出 `docs/upgrade/<任务ID>.md` 证据（命令、输出摘要、测试结果、截图路径、成本记录）。
- **复用主仓库 venv**：`D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe`（不复制 venv；依赖安装会记录到 docs/upgrade/DEPS.md）。若出现 numpy/torch 级冲突，触发硬停止并请示。
- **Gate**：G0 → G1 → G2 → G3，每 Gate 停止等待用户审核；未获确认不得进入下一阶段。
- **只读外部数据**：不改 SmartKB2.0 仓库；只读复用其 `models/bge-m3`。
- **失败即记录**：任何未验证行为标 `待确认`；不得在 README/账本中提前宣称能力。

---

## 3. 关键技术决策

### 3.1 Provider 抽象（A0 提前）
- `LLM_PROVIDER=ollama|deepseek|mock`（默认 `ollama`）。
- Ollama：OpenAI 兼容端点 `http://127.0.0.1:11434/v1`，`api_key="ollama"`，模型 `qwen2.5:7b`。
- DeepSeek：沿用现有 `deepseek-chat`；仅用于 1 次对比实验。
- mock：保持现有确定性 MockLLM（CI 默认）。
- 环境预检：启动 Ollama 前显式设置 `OLLAMA_MODELS=D:\OllamaModels`（当前用户/系统环境变量未设置，模型实际在该目录）。

### 3.2 Embedding 服务（2B 的安全落地）
- 复用 `D:\codex使用文件夹\SmartKB2.0\models\bge-m3`（已在 `pytorch_env` 中验证可用：torch 2.6.0+cu124 / FlagEmbedding 1.4.0）。
- 新增 `scripts/embed_server.py`：用 `D:\ANACONDA\envs\pytorch_env\python.exe` 启动的轻量 HTTP 服务（默认 `127.0.0.1:11435`）：
  - `GET /health` → `{"status":"ok","model":"bge-m3","dim":1024}`
  - `POST /embed` `{"texts":[...]}` → `{"embeddings":[[...]],"dim":1024}`
- AgentForge 仅用 `requests` 调该服务（`EMBEDDING_BASE_URL`），**不向 AgentForge venv 安装 torch/FlagEmbedding**。
- 服务不可用时 fail-closed：`local_search` 返回明确错误并记录，不静默返回空；G0/G1 检查清单包含 `/health`。

### 3.3 知识库（A1）
- 语料目录 `docs/kb/`（6 篇，均无密钥/PII，已扫描）：AgentForge README、tutorial-AgentForge.md、SmartKB2.0 的《大模型幻觉与Prompt注入风险工程化应对》《微调与LoRA知识》《主流大模型与应用范式分析》《AI应用实习面试学习文档》。
- 新增 `docs/kb/manifest.json`：每篇记录 `source_path/sha256/license/added_at/size_chars`。
- 新增 `app/kb/loader.py`（md/txt 读取 + 清洗）、`app/kb/indexer.py`（分块 + 索引 + metadata）、`scripts/build_kb.py`（`--rebuild` / `--incremental`）。
- Chroma 集合：`agentforge_kb`（`get_or_create_collection(name, embedding_function=OllamaEmbeddingFunction())`），metadata 记录 `embedding_model=bge-m3`、`dim=1024`、`chunk_size=500`、`overlap=50`、`corpus_version`。
- chunk id 确定性：`uuid5(NAMESPACE, f"{source}:{index}:{sha256(text)[:16]}")`。
- 检索验收：10 条固定查询（含 4 条改写/近义查询），人工标注相关 chunk，输出 `hit_rate@3` 与 `MRR` 到 `docs/upgrade/A1-kb-report.md`；不达标（hit_rate@3 < 0.7）则调 chunk/查询阈值或改 embedding 选型并回报。

### 3.4 Memory（A2）
- 只做**跨任务经验记忆**（不得表述为"完整短期+长期记忆系统"）。
- `MemoryRecord`：`task_id/topic/sub_questions/key_findings/source_count/created_at`；id 用 `uuid5`，不用 `hash()`。
- 存储：Chroma 集合 `agent_memory`（同一 embedding 服务）。
- 检索：`top_k`（默认 3）、`min_similarity`（默认由 cosine 距离换算，初值 0.35，实测后写死）、`max_chars`（默认 1500）。
- 注入：`planner` 的 user prompt 增加"参考背景（来自历史任务，可能不完整）"段落，并显式提示"仅作参考，不得替代本次检索"。
- 生命周期：`task_service` 执行前 `retrieve_experience`，成功后 `save_experience`；失败任务不写入。
- 验收：第二次相似主题任务的 planner 输入包含第一条记忆；`agent_memory` 计数从 N→N+1；异常（服务不可用）降级为无记忆并记录。

### 3.5 interrupt/resume（B4）
- 依赖：`langgraph-checkpoint-sqlite==3.1.1`（+ `sqlite-vec==0.1.9`；dry-run 确认不升级现有 langgraph 1.2.11 / checkpoint 4.2.0）。
- 图调整：`planner → human_review → searcher → analyzer → writer → reviewer → …`；`human_review` 节点调用 `interrupt({...})`，恢复用 `Command(resume=edited_sub_questions)`。
- Checkpointer：`AsyncSqliteSaver` 指向独立 `data/checkpoints.sqlite`（不与 `agentforge.db` 混用）；`thread_id = f"task-{task_id}"`；开启 WAL。
- 序列化：显式允许 `("app.agents.searcher","SearchOutcome")`，或把 state 中的 `SearchOutcome` 改为纯 dict；不得忽略 unregistered type 警告。
- 状态机：`pending→running→paused→running→completed`（或 failed/canceled）；resume 用 DB 条件更新防双恢复。
- API：`POST /api/tasks/{id}/resume` body `{"sub_questions":[...]}`；前端展示可编辑子问题（先做最小实现：文本域逐行编辑）。
- Spike 先行：30–60 分钟纯图 spike，通过标准=进程重启后可恢复、编辑后的子问题被采用、planner 不重复调用；不通过则退化为自实现暂停/恢复，并回报用户。

### 3.6 单进程 worker 与恢复（B1）
- FastAPI lifespan 启动后台 worker 协程；DB 轮询 pending，原子 claim：`UPDATE research_tasks SET status='running', locked_at=... WHERE id=:id AND status='pending'`（检查 rowcount）。
- 新字段：`locked_at`、`heartbeat_at`、`attempts`、`cancel_requested`；新状态 `canceled`。
- 恢复：启动时把 `locked_at` 超时（默认 10 分钟）的任务置回 pending（attempts 超限则 failed）。
- 轻量迁移：启动时 `PRAGMA table_info(research_tasks)` 检查并 `ALTER TABLE ADD COLUMN`；**不引入 Alembic**。
- 取消：`DELETE` 运行中任务返回 409；`POST /api/tasks/{id}/cancel`（如需）设置 `cancel_requested` 并由 worker 收敛为 canceled（本轮最小实现即可）。

### 3.7 SSE（4A：仅后端）
- `GET /api/tasks/{id}/stream`（`StreamingResponse`），事件：`status`、`log`、`node`、`interrupt`、`done`、`error`。
- 数据源：单进程 worker 的进程内事件总线（按 task_id 订阅）+ DB 日志兜底；不做断线续传。
- 测试：`tests/test_stream.py` 用 TestClient 验证事件顺序与 done/error 收口；前端继续轮询。
- 首事件目标 ≤2s（记录 p50，作为参考指标而非硬门槛）。

### 3.8 指标与成本（B3/A5）
- `ResearchTask.metrics`（JSON）：`node_latencies`、`llm_tokens{prompt,completion}`、`tavily_calls`、`estimated_cost_cny`、`usage_source`（`deepseek_api|ollama_api|none`）、`json_parse_failures`。
- UsageTracker 用 `contextvars` 按 task_id 传播；`BaseAgent._chat` 包装调用，记录每次 LLM 调用的 provider/耗时/token（可得时）。
- Ollama token：优先解析原生 `/api/chat` 的 `prompt_eval_count/eval_count`；OpenAI 兼容端点若不返回 usage 则记 `null`（不阻塞，不静默记 0）。
- DeepSeek：usage 缺失或无法估算时**直接中止付费调用**（fail-closed）。
- 成本口径：`config/prices.json`（含 `verified_at`）+ `scripts/run_live_local.py --max-tasks --max-tavily-calls --max-cost-cny`；超限立即中止并记录。
- API：`GET /api/tasks/{id}/metrics`；前端展示耗时/token/估算成本，标注"估算"。

---

## 4. 依赖与版本锁定（A4）

在 `requirements.txt`/`requirements-lock.txt` 中锁定（当前环境已核验）：

```
langgraph==1.2.11
langgraph-checkpoint==4.2.0
langgraph-checkpoint-sqlite==3.1.1
sqlite-vec==0.1.9
langchain==1.3.15
langchain-core==1.5.5
langchain-openai==1.5.1
langchain-community==0.4.2
chromadb==1.5.9
sqlalchemy==2.0.52
aiosqlite==0.22.1
fastapi==0.141.1
httpx==0.28.1
pytest==9.1.1
tavily-python==0.7.27
duckduckgo-search==8.1.1
```

开发依赖：`ruff`（新增，A4）、`pytest-asyncio`（如需）。**不向 AgentForge venv 安装 torch/FlagEmbedding/sentence-transformers**（embedding 走独立服务）。
---

## 5. 任务清单（可端到端执行）

### P0 / G0 —— 预检与基线（0.5 天）
**目标**：确认环境、版本、测试基线、Ollama 与模型，建立 worktree 与证据文件。

**步骤/命令**
1. `git worktree add -b codex/agentforge-upgrade D:\codex使用文件夹\AgentForge-v2`（已执行，基线 498e446）。
2. 依赖记录：主 venv `python -m pip list`（写入 `docs/upgrade/DEPS.md`）。
3. ollama 预检（需用户正常终端启动，或 AI 获批启动）：
   - `set OLLAMA_MODELS=D:\OllamaModels`
   - `ollama list`（期望 `qwen2.5:7b`、`nomic-embed-text`）
   - `curl http://127.0.0.1:11434/api/version`
4. embedding 服务预检：`D:\ANACONDA\envs\pytorch_env\python.exe scripts/embed_server.py --check`（仅加载模型并打印维度 1024）。
5. 测试基线：`pytest -q`（期望 22 passed）。
6. mock e2e：`$env:LLM_MODE="mock"; python scripts/run_e2e.py "冒烟主题"`（当前会因 `validate_for_live()` 失败——A3 修复，G0 记录该已知问题）。
7. 记录 Chroma 现状：collections=0、embeddings=0。

**验收**：`docs/upgrade/G0-baseline.md` 存在并含以上命令与结果；pytest 22 通过；模型/依赖版本已记录。
**Gate G0**：停下等用户审核（重点确认 Ollama 可启动、语料 6 篇无隐私）。

### A0 —— Provider 与 UsageTracker 骨架（0.5–1 天）
**文件**：`app/config.py`、`app/llm/factory.py`、`app/observability.py`、`tests/test_provider.py`
**接口/行为**
- `LLM_PROVIDER=ollama|deepseek|mock`；Ollama base_url `http://127.0.0.1:11434/v1`，model `qwen2.5:7b`。
- `UsageTracker`（contextvars）：`record_llm(provider, prompt_tokens, completion_tokens, latency_ms)`、`record_search(backend)`、`snapshot()`。
- `get_llm()` 返回对象需携带 provider 信息；mock 模式完全离线。
**验收**：mock 单测通过；Ollama 一个主题 JSON smoke（真实、成本 0）；DeepSeek 调用路径 dry-run 单测。
**证据**：`docs/upgrade/A0-provider.md`

### A1 —— 真实知识库（1.5–2 天）
**文件**：`docs/kb/`（6 篇 + manifest.json）、`app/kb/loader.py`、`app/kb/indexer.py`、`app/kb/embedding.py`、`app/kb/eval_kb.py`、`scripts/build_kb.py`、`scripts/embed_server.py`、`tests/test_kb.py`；改 `app/config.py`、`app/tools/rag.py`。
**接口/行为**
- `loader.load_documents(dir) -> list[Document]`；`indexer.build(rebuild: bool)`；`rag.search(query, n_results)`。
- 集合 `agentforge_kb`；metadata 记录 embedding_model/dim/chunk/corpus_version。
- 自定义 `OllamaEmbeddingFunction`：实现 `__call__`、`name()`、`get_config()`、`build_from_config()`，`default_space()` 返回 cosine；测试注入 `FakeEmbeddingFunction`（确定性、离线）。
**测试/验收**
- `python scripts/build_kb.py --rebuild` → 打印文档数/chunk 数；`local_search("RAG")` 非空。
- 10 条固定查询 → hit_rate@3 ≥ 0.7、MRR 记录；报告 `docs/upgrade/A1-kb-report.md`。
- MCP `local_search` 真实非空一次（记录调用命令与输出）。
**成本**：0。

### A2 —— Memory 接通（1–1.5 天）
**文件**：`app/services/memory_service.py`、`app/graph/state.py`、`app/agents/planner.py`、`app/services/task_service.py`、`app/config.py`、`tests/test_memory.py`
**配置**：`MEMORY_ENABLED=true`、`MEMORY_TOP_K=3`、`MEMORY_MAX_CHARS=1500`、`MEMORY_MIN_SIMILARITY=0.35`
**验收**
- 第二次相似任务 planner 输入包含"参考背景"且 ≤1500 字；
- `agent_memory` 计数 N→N+1；
- 服务不可用/空记忆/低相似度 → 降级为无记忆并记录；
- 单测覆盖 UUID 稳定性、污染过滤、异常降级。
**边界**：仅宣称"跨任务经验记忆"；不得写"完整短期+长期记忆系统"。
**证据**：`docs/upgrade/A2-memory.md`

### A3 —— 一致性与安全修复（0.5–1 天）
**修改**
- `app/agents/reviewer.py`：合格分渲染自 `settings.review_pass_score`（默认 7）。
- `app/graph/research_graph.py` docstring 与 `README.md`：改为"单节点并行 + 子问题内部最多 2 轮"。
- `app/routes/tasks.py`：DELETE 运行中任务 → 409。
- `app/services/task_service.py`：except 分支补 task None 保护。
- 超时：`TASK_SOFT_TIMEOUT_SECONDS`（API 层软超时）+ 节点入口 deadline 检查 + HTTP timeout；README 如实说明"软超时不能强制终止线程"。
- `scripts/run_e2e.py`：mock 模式不再强制 `validate_for_live()`。
**测试**：`tests/test_consistency.py`（reviewer 分数、DELETE 409、None 保护、mock e2e 可通过）。
**证据**：`docs/upgrade/A3-consistency.md`

### A4 —— CI / API / 失败路径 / 锁版本（1 天）
**文件**：`.github/workflows/ci.yml`、`pyproject.toml`（ruff 配置）、`requirements.txt`、`requirements-lock.txt`、`tests/conftest.py`、`tests/test_api.py`、`tests/test_failure_paths.py`、`docs/upgrade/DEPS.md`
**验收**
- CI：Python 3.12 → pip install → `ruff check .` → `pytest -q` 全绿；
- API 测试覆盖：create/list/get/report（409/200）/delete（404）；
- 失败路径测试：搜索全失败 → analyzer 空 findings → 报告不编造来源；
- conftest 使用临时 `DATABASE_URL`；后台任务用 monkeypatch 或直接调用 `run_task` 避免 TestClient 不稳定。
**证据**：`docs/upgrade/A4-ci.md`

### A5 —— 本地 live + 成本闸门（1–1.5 天）
**文件**：`app/observability.py`、`scripts/run_live_local.py`、`config/prices.json`、`data/live_results.json`、`tests/test_cost_gate.py`
**行为**
- 本地 Ollama 跑 2 个主题；记录耗时、审核轮次、JSON 成功率、Tavily 调用数、token（可得时）、估算成本。
- 付费 provider usage 缺失 → 中止（fail-closed）。
- DeepSeek 对比：恰好 1 次；**复用同一批搜索结果**；记录输入/输出 token 与真实估算成本；≤2 元；超限即停并回报。
- 成本闸门以外部 API 现金支出为准；本地 Ollama = 0；总预算 ≤10 元。
**验收**：`data/live_results.json` 含 2 条本地记录 + 1 条 DeepSeek 对比；成本脚本能中止超限。
**Gate G1 前检查**：pytest 全绿、KB 报告达标、Memory 演示成功、本地 live ≥2 主题、DeepSeek 对比完成且 ≤2 元。

### B1 —— interrupt/resume spike + 实现（1.5–2 天）
**Spike（先做，30–60 分钟）**：纯图验证 `interrupt` → `Command(resume=...)` → 进程重启后恢复 → 编辑后子问题被采用 → planner 不重复调用。
**实现文件**：`app/graph/research_graph.py`、`app/graph/state.py`、`app/services/task_service.py`、`app/routes/tasks.py`、`frontend/app.py`、`tests/test_interrupt.py`
**接口**：`POST /api/tasks/{id}/resume {"sub_questions":[...]}`；状态 `paused`；checkpoint 独立 `data/checkpoints.sqlite`。
**验收**：spike 通过；API/前端最小可用；测试覆盖暂停→编辑→恢复→完成。
**失败回退**：spike 不通过 → 自实现暂停/恢复（DB 状态 + 手动重跑），并回报用户。

### B2 —— 单进程 worker / 恢复 / 取消（1.5–2 天）
**文件**：`app/worker.py`、`app/main.py`、`app/db/models.py`、`app/services/task_service.py`、`app/migrations.py`、`tests/test_recovery.py`、`tests/test_claim_race.py`
**行为**：lifespan 启动 worker；原子 claim；locked_at/heartbeat_at/attempts/cancel_requested；启动 recover_stale_tasks；轻量迁移（PRAGMA + ALTER TABLE）。
**验收**：双 worker 只有一个 claim 成功；stale 任务恢复；DELETE running → 409；attempts 超限 → failed。

### B3 —— 指标与成本展示（1 天）
**文件**：`app/observability.py`、`app/routes/tasks.py`、`app/db/models.py`、`frontend/app.py`、`tests/test_metrics.py`
**接口**：`GET /api/tasks/{id}/metrics`；`metrics` JSON 字段见 3.8；前端展示耗时/token/估算成本并标注"估算"。
**验收**：一次真实任务后 metrics 有节点耗时；usage 缺失记 null。

### B4 —— 后端 SSE（1 天）
**文件**：`app/routes/tasks.py`、`app/worker.py`（事件总线）、`tests/test_stream.py`
**接口**：`GET /api/tasks/{id}/stream`；事件 `status/log/node/interrupt/done/error`；不做断线续传。
**验收**：事件顺序正确、done/error 收口；首事件 ≤2s（记录 p50）；Streamlit 继续轮询。
**Gate G2**：B1–B4 全部通过 + 演示（interrupt/resume、指标、SSE curl）+ 回归测试全绿，停下等用户审核。

### C —— 可选增强（Phase A/B 后按用户决定）
- C1 Docker 硬化：`.dockerignore`、healthcheck、`host.docker.internal` 指向宿主机 Ollama；用户安装 Docker 后执行。
- C2 YAML 配置 + fast/standard/deep profile（完成后才能改账本 claim-af-004）。
- C3 原生 tool calling / structured output（先做本地 Qwen JSON 可靠性 spike）。
- C4 引用校验 + hit_rate@k/MRR 扩展 + 更多评测维度。

---

## 6. Gate 检查单

| Gate | 必须满足 | 用户动作 |
|---|---|---|
| G0 | worktree 建立；依赖版本记录；pytest 22 通过；Ollama 可启动且模型可见；语料 6 篇确认无隐私 | 审核 `G0-baseline.md` |
| G1 | A0–A5 完成；pytest+ruff 全绿；KB hit_rate@3 ≥0.7；Memory 演示；本地 live ≥2 主题；DeepSeek 1 次对比 ≤2 元 | 审核 `A1/A2/A3/A4/A5` 证据 |
| G2 | B1–B4 完成；interrupt/resume 演示；worker 恢复；metrics；SSE 测试；回归全绿 | 审核 B 阶段证据 + 演示 |
| G3 | README 与真实能力一致；账本更新；未落地项标注"规划中"；DoD 全项核对 | 最终验收 |

---

## 7. 成本闸门

- 计费口径：仅外部 API 现金支出；Ollama 本地推理 = 0；电费/显卡折旧不计入。
- 预算：总硬上限 10 元；DeepSeek 对比单次硬上限 2 元。
- 控制手段：Tavily 结果缓存 + 调用上限；`scripts/run_live_local.py --max-tavily-calls/--max-cost-cny`；付费 provider usage 缺失即中止（fail-closed）。
- 价格表 `config/prices.json` 必须含 `verified_at` 与来源；实施当天重新核对官方价格（子代理引用的 Tavily 免费额度/单价属易变信息）。
- 超限处理：立即停止、写 `docs/upgrade/COST-ALERT.md`、请示用户，不再发起付费调用。

---

## 8. 硬停止条件（触发即停并请示）

1. 核心依赖冲突（numpy/torch/langgraph/chromadb 任一破坏现有 22 测试）；或单点修复超过 30 分钟。
2. 成本预估或实际将超 10 元（付费对比 >2 元）。
3. Ollama 不可用或模型缺失（`qwen2.5:7b` / embedding 服务不可用）。
4. interrupt/resume spike 超过 90 分钟仍未通过（转回退方案）。
5. 需要管理员权限或写入工作区外目录。
6. 语料出现隐私/PII/密钥或有许可证疑问。
7. embedding 服务与 pytorch_env 不兼容（如 CUDA/驱动异常）。
8. 既有测试回归且 30 分钟内无法定位。

---

## 9. Definition of Done

- [ ] G0/G1/G2/G3 全部通过并留有 `docs/upgrade/*.md` 证据；
- [ ] `pytest -q` 与 CI（ruff + pytest）全绿；
- [ ] `local_search` 对真实语料返回非空，KB 报告含 hit_rate@3 / MRR；
- [ ] Memory 可复现演示（相似任务复用历史经验，计数增长）；
- [ ] interrupt/resume 可复现演示（暂停→编辑子问题→恢复→完成；进程重启可恢复）；
- [ ] 单进程 worker + 恢复 + 409 取消语义 + 轻量迁移可用；
- [ ] metrics API 与前端展示（估算标注）；
- [ ] SSE 后端接口测试通过（不做断线续传）；
- [ ] 本地 live ≥2 主题，total 外部 API 成本 ≤10 元，DeepSeek 对比 ≤2 元；
- [ ] README 与真实能力一致；未落地项（YAML/Docker/微调）明确标"规划中"；
- [ ] 主张—证据账本同步：`claim-af-002`（Memory）与 `claim-af-003`（人机协同）只有在实现+测试+演示齐全后才从"不采用"改为"已确认"；`claim-af-004`（YAML）保持"不采用"直到 C2 完成；22 项测试数字更新为最终实际值。

---

## 10. 风险登记与回滚

| 风险 | 影响 | 缓解 | 回滚 |
|---|---|---|---|
| FlagEmbedding/embedding 服务不可用 | 检索/记忆全阻塞 | 独立服务 + /health + fail-closed | 停用 memory，保留关键词检索；或临时用 Ollama embedding |
| checkpoint 序列化不兼容 | interrupt/resume 失败 | spike 先行 + 显式 serde 白名单/改纯 dict | 退化为 DB 状态手工恢复 |
| worker 竞态 | 任务重复执行 | 原子 UPDATE + 单进程 + 测试 | 回到 lifespan 内 create_task 模式 |
| 成本超支 | 预算违规 | usage fail-closed + 上限参数 | 立即停用付费 provider，仅本地 |
| 依赖升级破坏 22 测试 | 回归 | 版本锁定 + 不做范围外升级 | 恢复 requirements-lock 并重装 |
| 语料含隐私 | 公开发布风险 | 已扫描 6 篇（无 key/PII） | 移除相关文档并重建索引 |

---

## 11. 本轮已核实的基线事实（2026-09-10）

- worktree：`D:\codex使用文件夹\AgentForge-v2`，分支 `codex/agentforge-upgrade`，HEAD `498e446`。
- `pytest --collect-only -q` → 22 tests collected。
- AgentForge venv 关键版本见第 4 节；**未安装** torch/FlagEmbedding/langgraph-checkpoint-sqlite/ruff/alembic。
- `langgraph-checkpoint-sqlite==3.1.1` dry-run 通过（仅新增 sqlite-vec==0.1.9）。
- Chroma：collections=0、embeddings=0、segments=0；`app/tools/rag.py` 仅 `get_collection`，无入库代码。
- Chroma 默认 EF 会尝试下载 ONNX MiniLM 并 PermissionError → 必须自定义 EF + CI fake EF。
- Ollama：服务器未运行；`D:\OllamaModels` 已有 `qwen2.5:7b`、`nomic-embed-text` manifest；`OLLAMA_MODELS` 用户/系统环境变量未设置。
- `pytorch_env`：torch 2.6.0+cu124、FlagEmbedding 1.4.0、sentence-transformers 5.7.0、本地 bge-m3 权重就绪。
- 语料扫描：6 篇候选文档中未发现 `sk-`/`tvly-`/`ghp_`、邮箱、手机号、姓名或 GitHub 账号。
