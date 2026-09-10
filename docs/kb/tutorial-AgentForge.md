# 源码课程：AgentForge —— 基于 LangGraph 的多 Agent 研究协作系统

> 本文件同时承担「课程大纲」与「全部课程展开」两个角色。每个课程已标记 `大纲状态：已展开`。
> 文件内所有路径均为**相对本项目根目录**的相对路径；符号（函数/类/字段）均可直接在源码中定位。

---

## 0. 使用本课程前必读

### 项目用途与学习目标
用户输入一个研究主题，系统自动完成「任务分解 → 信息检索 → 交叉分析 → 报告撰写 → 质量审核」，最终输出一份结构化研究报告并持久化。学习本仓库，你应该能回答四类问题：

1. 一次研究任务如何从 HTTP 请求走到数据库里的 `completed` 状态（异步边界在哪）；
2. LangGraph 状态图如何把 5 个 Agent 编排成可测试、可防死循环的工作流；
3. 为什么项目可以在没有 API Key 的情况下离线验证编排逻辑（live/mock 双模式）；
4. 真实运行中如何保证"搜索失败不编造、审核不过就修订、数据可复现"。

### 源码版本与本地改动
- 阅读基准：2026-09-09。`git log --oneline`：`498e446 加入mcp服务`、`96cfcf5 docs: 移除真实运行记录中的时间信息`、`fafa0c1 docs: 添加 MIT LICENSE`、`9595bca feat: AgentForge 多Agent智能研究协作系统`。
- 本课程撰写时未修改任何项目源码；课程依据 HEAD（含 mcp 提交）的实际代码。
- 影响结论的已知差异（以实现为准）：
  1. `README.md` 的架构图与 `app/graph/research_graph.py` 模块 docstring 都画了「searcher 仍有子问题→回 searcher」的图级循环，但 `build()` 实际没有该条件边：**搜索是单个节点内对全部子问题并行执行**，子问题内部的重试/改写循环在 `SearcherAgent.search()` 内实现（上限 2 轮）。课程按代码讲，并标注此差异。
  2. `app/agents/reviewer.py` 的 system prompt 写「8 分及以上为合格」，但路由判定用的是 `settings.review_pass_score`（默认 **7**）。实现以 7 分为准，prompt 与配置不一致是遗留问题。
  3. `app/mcp_server.py` 是独立 fastmcp 模块，**未注册进 FastAPI**（`app/main.py` 只 include tasks/reports 两个 router）；`MemoryService`（长期记忆）当前**未被任何调用方使用**；`CalculatorTool` 只被 `mcp_server.py` 与测试引用，**不在主研究图里**。课程相应标注「未接入主流程」。

### 前置基础
- Python 异步基础：`async/await`、`asyncio.create_task`、事件循环不要被同步阻塞的概念；
- FastAPI 基础：路由、Pydantic 请求体、HTTPException；
- LLM/Agent 常识：system/user 消息、JSON 输出、检索失败与幻觉的关系；
- 可选：LangGraph 的 StateGraph/TypedDict/条件边概念（第 2 课会边读边补）。

### 本次覆盖范围
覆盖：HTTP 提交/查询/删除/下载、异步后台执行、数据库持久化、LangGraph 图编排、五个 Agent、live/mock LLM 抽象、搜索/本地检索/计算器工具、Streamlit 轮询前端、e2e 与批量脚本、pytest 测试体系。

**尚未覆盖**（不在此课程展开）：MCP Server 对外暴露（`app/mcp_server.py` 内部机制）、Docker 实际构建运行（本机无 Docker，仅文件就绪）、前端 Dockerfile、生产部署与鉴权。

---

## 1. 课程地图（大纲总览）

| 编号 | 课程 | 读完能回答的问题 | 大纲状态 |
|---|---|---|---|
| L1 | 任务的一生：HTTP 提交 → 异步执行 → 落库 | 一次 POST /api/tasks 如何触发后台工作流并最终变成 completed/failed？ | 已展开 |
| L2 | LangGraph 状态图：五个节点如何被编排 | 图里有哪些节点、条件边在哪、searcher 的"循环"到底在哪一层？ | 已展开 |
| L3 | LLM 抽象层：live/mock 双模式与 JSON 稳健解析 | 为什么没有 API Key 也能跑通全流程？Agent 如何稳定拿到结构化 JSON？ | 已展开 |
| L4 | 搜索 Agent 与真实降级：受控 ReAct 与"禁编造" | 一个子问题如何被搜索，失败/结果不足时会发生什么？ | 已展开 |
| L5 | 分析与撰写：从检索结果到结构化报告 | 检索结果如何被提炼成分析，再拼成带来源的报告/修订稿？ | 已展开 |
| L6 | 审核闭环：评分、修订与防死循环 | 报告不合格时如何回到 writer，如何保证不会无限循环？ | 已展开 |
| L7 | 持久化与状态流转：pending → completed/failed | 工作流中间态与终态如何落库，查询/删除/下载如何读库？ | 已展开 |
| L8 | 前端轮询：从"提交"到"看报告" | Streamlit 如何轮询后端、展示日志与报告，超时保护在哪？ | 已展开 |
| L9 | 运行与测试体系：脚本、mock 测试与真实数据 | 如何离线跑、如何真实跑、如何批量记录可复现数据，测试覆盖了什么？ | 已展开 |

---

## L1 任务的一生：HTTP 提交 → 异步执行 → 落库

### 场景与目标
在「发起研究」页输入主题并点击后，前端调 `POST /api/tasks`。本课追踪这次请求：入口路由 → 建库记录 → 后台任务调度 → 状态置 running → 图执行 → 结果写回。

### 主链
`POST /api/tasks {topic}` → `app/routes/tasks.py::create_task` → `TaskService.create_task`（落库 pending）→ `asyncio.create_task(TaskService.run_task(id))`（后台）→ `run_task` 置 running → `ResearchGraph().build()` + `initial_state(topic)` → `asyncio.to_thread(graph.invoke, state)` → `_serialize_state` → 写回 completed/failed。

### 编号阅读步骤
1. `app/routes/tasks.py`：`TaskCreate` 定义请求体（topic 1–500 字符）；`create_task` 返回 `201` 与 `_task_to_dict(task)`（不含长字段）。
2. 同文件顶部 `_background_tasks: set[asyncio.Task]`：**为什么必须保存引用**？防止 asyncio 后台任务被 GC 中断；`bg.add_done_callback(_background_tasks.discard)` 在结束时移除。
3. `app/services/task_service.py::create_task`：strip 校验 → `ResearchTask(topic, status="pending")` → commit/refresh → 返回带 id 的对象。
4. `task_service.run_task`：新会话取任务 → `status="running"` 并 commit → 构建 `ResearchGraph().build()`、`initial_state(topic)`。
5. `await asyncio.to_thread(graph.invoke, state)`：LangGraph 的 `invoke` 是**同步阻塞**调用，放到独立线程执行以免卡住事件循环（关键异步边界）。
6. `_serialize_state(final_state)`：把 `SearchOutcome` 对象列表转成纯 JSON（`documents/rounds/log`）。
7. 成功后新开会话：写 `sub_questions/search_results/analysis_results/draft_report/final_report/review_history/review_rounds/logs/completed_at` → commit。
8. `except` 分支：`status="failed"`、`error=str(exc)` 落库后 `raise`。

### 重要分支
- **失败分支**：`run_task` 内任何异常（图执行、序列化、DB 写回）都会进入 except → 状态 failed + error 字段 → 重新抛出（后台任务日志可见）。这是源码里唯一的失败路径，没有重试机制。
- **资源生命周期**：每个 DB 操作都用独立 `async with SessionLocal()`，避免跨协程共享会话；后台任务在**新的会话**里再次 `session.get(task_id)` 拿最新对象。
- 重复提交：没有幂等设计；同主题可创建多条任务（对象身份不同），代码不阻止。

### 完整流程串联
输入 `{"topic": "2025年大模型行业趋势"}`：`create_task` 落库得到 `id=1/pending` → 路由立刻返回 201（用户马上看到 ID）→ 后台 `run_task(1)` 置 running → 图执行（详见 L2–L6）→ 全部字段写回、`completed_at` 打点、状态 completed。前端靠轮询看到状态变化（L8）。

### 回顾与复述任务
不运行项目，用自己的话讲：`asyncio.create_task`、`asyncio.to_thread`、两次独立 DB 会话（running 与 completed 各一次）分别解决了什么问题？如果 `graph.invoke` 直接 await 会怎样？

### 大纲状态：已展开
---

## L2 LangGraph 状态图：五个节点如何被编排

### 场景与目标
L1 停在 `graph.invoke(state)`。本课进入图内部：状态长什么样、节点是谁、什么时候走条件边、searcher 的"循环"到底在哪。

### 主链
`app/graph/state.py::initial_state(topic)` → `StateGraph(ResearchState)` → `START → planner → searcher → analyzer → writer → reviewer` → `reviewer` 条件边 → `writer`（revise）或 `finalize` → `END`。

### 编号阅读步骤
1. `app/graph/state.py`：`ResearchState`（TypedDict）列出全部共享字段；注意两个 `Annotated[list, operator.add]` 字段：`review_history` 与 `log` —— 节点每次只返回**增量**，LangGraph 按 `operator.add` 追加而不是覆盖（这是"日志不重复累加"的关键机制）。
2. `initial_state()`：给每个字段默认值，`status="planning"`。
3. `app/graph/research_graph.py::build()`：注册 6 个节点 `planner/searcher/analyzer/writer/reviewer/finalize`；`add_edge` 串联；`add_conditional_edges("reviewer", _route_after_review, {"revise": "writer", "finalize": "finalize"})`。
4. `_plan_node`：调 `planner.plan(topic)` → 写 `sub_questions`、`current_question_index=0`、`status="searching"`。
5. `_search_node`：从 `state["sub_questions"]` 取全部问题 → `ThreadPoolExecutor(max_workers=min(len, 4))` 并行调 `self.searcher.search(q)`；每个问题独立 try/except，失败也产出空的 `SearchOutcome`（不让单点失败拖垮整批）。
6. `_analyze_node`：遍历 `search_outcomes` → `analyzer.analyze(question, [outcome.as_text()])` → 附上 `sources`。
7. `_write_node`：**关键分支**——若 `review_feedback and draft_report` 非空则 `writer.revise(...)`，否则 `writer.write(...)`；状态置 `reviewing`。
8. `_review_node`：`reviewer.review` → `review_rounds += 1` → 生成 `review_entry{round,score,suggestions,issues}` → 把 `review_feedback`（suggestions 拼接）与 `review_history=[review_entry]`（增量）写回。
9. `_route_after_review`（条件边函数）：`last_score >= settings.review_pass_score` 或 `rounds >= settings.max_review_rounds` → `"finalize"`；否则 `"revise"`。
10. `_finalize_node`：`final_report = draft_report`、`status="completed"`。

### 文档与实现差异（务必记）
- `research_graph.py` 顶部 docstring 画了「searcher -(仍有子问题)-> searcher」图级回路，**实际代码没有这条边**；`build()` 中 searcher 只执行一次，全部子问题并行处理。子问题内部的"结果不足→改写查询→再搜"循环在 `SearcherAgent.search()`（L4），上限 2 轮。
- `README.md` 架构 mermaid 同理，阅读时以实现为准。

### 重要分支
- reviewer 后只有两条出路：`revise`（回 writer 修订）或 `finalize`。达到 `REVIEW_PASS_SCORE`（默认 7）**或**达到 `MAX_REVIEW_ROUNDS`（默认 2）都会结束——后者是防死循环的硬闸门。
- `Annotated[list, operator.add]` 只对 `review_history`/`log` 生效；普通字段（如 `draft_report`）是**覆盖**语义。

### 完整流程串联
以"多智能体系统架构设计"为例：planner 产出 N 个子问题 → searcher 一次性并行检索全部子问题（内部各最多 2 轮）→ analyzer 逐题分析 → writer 写初稿（无 feedback）→ reviewer 打分 5（<7）且轮次 1<2 → 条件边回 writer 修订（此时 draft+feedback 非空，走 `revise`）→ reviewer 再评 9 → finalize。

### 回顾与复述任务
画出这张图的 6 个节点与两类边（普通边/条件边），并指出：如果 searcher 要在**图级**按子问题逐个循环，需要改 `build()` 的哪些行？现在为什么不用改？

### 大纲状态：已展开

---

## L3 LLM 抽象层：live/mock 双模式与 JSON 稳健解析

### 场景与目标
测试和"无 Key 演示"都要能跑。理解为什么所有 Agent 不直接依赖 DeepSeek SDK，而是依赖一个统一 `invoke(messages)` 接口。

### 主链
`app/config.py::settings`（读 .env）→ `app/llm/factory.py::get_llm()` → 返回 `MockLLM` 或 `ChatOpenAI` → `app/agents/base.py::BaseAgent._chat/_chat_json` → `extract_json` 提取结构化结果。

### 编号阅读步骤
1. `app/config.py`：`Settings` 是 `frozen=True` dataclass；`_get/_get_int/_get_float` 包装环境变量；`llm_mode` 默认 `"live"`，但 `llm_configured` 只看有没有 `DEEPSEEK_API_KEY`；`validate_for_live()` 在缺 key 时抛可读错误（run_e2e 会调用它）。
2. `app/llm/factory.py::get_llm()`：判定 `mode == "mock" or (mode == "live" and not settings.llm_configured)` → `MockLLM()`；否则构造 `ChatOpenAI`（DeepSeek 的 OpenAI 兼容端点：base_url/model/temperature/max_tokens/timeout=60/max_retries=2）。
3. `MockLLM.invoke`：把消息列表拼成纯文本（`_messages_to_text`），按关键字命中返回对应 JSON/报告。默认响应与提示词关键字绑定：`sub_questions`/`search_queries`/`key_findings`/`score+suggestions`/`报告`。`responses` 参数可注入自定义映射，测试特定分支。
4. `app/agents/base.py`：`_make_message` 优先用 LangChain 的 System/Human/AIMessage，装不上时退回 `SimpleMessage`（鸭子类型）；`_chat` 拼 system+human 后 `llm.invoke`；`_chat_json` 调 `_chat` 再 `extract_json`。
5. `extract_json` 三级策略：整体 `json.loads` → 抓 ```json 代码块 → 从第一个 `{` 做花括号深度扫描截取。模型输出带解释文字/代码围栏也能解析。

### 重要分支
- **live 缺 key 自动降级为 mock**：`LLM_MODE=live` 但没有 key 时不会崩，而是静默返回 mock——这是"默认能跑"的设计取舍；想强制真实运行要先配 key（`.env` 或环境变量）。
- `extract_json` 解析失败会抛 `ValueError`，由各 Agent 上层决定是否兜底（如 planner 抛错、searcher._reformulate 捕获后返回空列表）。

### 完整流程串联
`tests/conftest.py` 在 import app 之前 `os.environ.setdefault("LLM_MODE","mock")` → 所有 Agent 构造时 `get_llm()` 返回 `MockLLM` → `test_planner_mock` 里 `PlannerAgent().plan("测试主题")` 命中 `sub_questions` 关键字返回固定 4 个子问题。真实运行则改 `.env` 的 `LLM_MODE=live` 与 key。

### 回顾与复述任务
解释：为什么 mock 的 `_default_response` 按**关键字**而非按"第几条消息"匹配？这种设计对测试单 Agent 和整图分别意味着什么（提示：提示词里必须出现对应关键字）。

### 大纲状态：已展开

---

## L4 搜索 Agent 与真实降级：受控 ReAct 与"禁编造"

### 场景与目标
一个子问题如何变成若干条可信资料？重点不是"搜得多"，而是**结果不足怎么办、失败怎么如实记录、空结果如何不污染下游**。

### 主链
`SearcherAgent.search(question)` → `plan_queries`（LLM 出查询词+prefer_local）→ 轮次循环（≤2）：`_try_local` / `_try_web` → `_dedupe` → `_is_sufficient` → 不足则 `_reformulate` 换词再搜 → 返回 `SearchOutcome`。

### 编号阅读步骤
1. `app/agents/searcher.py`：`SearchOutcome`（dataclass）字段 `question/documents/rounds/log`；`as_text()` 把文档拼成带标题/来源/内容文本（空文档返回「（未检索到有效结果）」——下游 analyzer 会据此识别）；`sources()` 去重来源标签。
2. `plan_queries`：`_chat_json(PLAN_PROMPT, ...)` → 取 `search_queries`（最多 3）、`prefer_local`；LLM 没给查询词时兜底用问题本身。
3. `search()`：**mock 短路**——`settings.llm_mode == "mock"` 直接返回一条模拟资料（跳过网络）。
4. 轮次循环：每轮对 queries 依次先本地后网络（`prefer_local` 只决定先搜本地，**网络仍然会搜**）；`_try_*` 用 try/except 把异常转成 `(空列表, 错误串)`，错误串进入 `outcome.log` 而不进入 `documents`。
5. `_dedupe`：按 url/title/content 前 200 字符去重；`_is_sufficient`：**至少 2 条非空内容**才算充分（避免单条弱结果过早结束——这是 README 记录的优化点）。
6. 不充分且未到 max_rounds：`_reformulate` 让 LLM 换 1-3 个新词再搜；`_reformulate` 自身 try/except，失败返回空列表 → 外层 break。
7. `app/tools/search.py::WebSearchTool`：有 `tavily_api_key` 先走 Tavily，异常记录 warning 后**自动回退 DuckDuckGo**；DDG 兼容新旧包名（ddgs / duckduckgo-search）。工具只负责抛错，**由 SearcherAgent 记录并降级**。
8. `app/tools/rag.py::LocalSearchTool`：ChromaDB `PersistentClient`；未安装/集合不存在/查询失败都返回 `[]`（不抛）。

### 重要分支（真实性核心）
- **失败与错误信息隔离**：`_try_web/_try_local` 返回 `(docs, err)`；err 只进 log，绝不进 documents。这样 analyzer/writer 永远不会把"连接超时"当成有效资料。
- **充分性不达标**：最多重试 1 次换词（round 2），仍不足就带着已有结果结束——流程不会无限搜。
- **空结果语义**：`SearchOutcome.documents=[]` 时 `as_text()` 明确输出「未检索到有效结果」，是 analyzer 判定"信息不足"的输入信号（L5）。

### 完整流程串联
子问题"2025 年大模型行业主要玩家"：plan_queries 给出 ["大模型 2025 格局","大模型厂商 2025"]、prefer_local=false → 第 1 轮网络搜索 Tavily 成功 2 条 → 本地也搜（可能 0 条）→ 合并去重后 `_is_sufficient`=True → 提前结束，返回 outcome。若 Tavily/DDG 全部超时：documents=[]，log 记两轮失败，下游 analyzer 会产出"无法可靠分析"而不是编造。

### 回顾与复述任务
讲清"错误信息不得进入 documents"在代码里由哪两处保证（`_try_*` 的返回结构 + log/doc 分流）；如果让 `_try_web` 失败时抛异常而不是返回空，graph 的 `_search_node` 里哪个 try/except 会兜住？

### 大纲状态：已展开

---

## L5 分析与撰写：从检索结果到结构化报告

### 场景与目标
检索产物（SearchOutcome）如何变成逐题分析，再拼成一份带来源、可修订的 Markdown 报告。

### 主链
`graph._analyze_node` → `AnalyzerAgent.analyze(question, [outcome.as_text()])` → 附 `sources` → `graph._write_node` → `WriterAgent.write / revise`。

### 编号阅读步骤
1. `app/agents/analyzer.py`：system prompt 要求 `key_findings/credibility/contradictions/summary`；**真实性约束**：空结果/错误信息/「未检索到有效结果」→ `key_findings=[]`、`credibility="低"`、summary 明确写"未检索到有效信息"。`analyze()` 把返回规范成固定四键。
2. `app/graph/research_graph.py::_analyze_node`：按问题遍历，`analysis["sources"] = outcome.sources()` —— 来源来自真实文档 URL/标题，供 writer 引用，不给模型自由发挥来源。
3. `app/agents/writer.py::write`：`_build_user_prompt` 把每题的关键发现/可信度/总结/来源排版进 user prompt；`REPORT_SYSTEM_PROMPT` 强制 Markdown 三部分（研究摘要/正文/结论）、正文按子问题分章、章末标来源；**禁止编造数据/论文/机构/来源**；全部无信息时必须声明"未检索到有效信息"。
4. `WriterAgent.revise`：`REVISE_SYSTEM_PROMPT` 只按审核意见定向修订、保留其他内容、禁止为满足意见而编造。
5. `_write_node` 的判定（L2 已见）：有 `feedback and draft` 走 revise，否则 write。

### 重要分支
- **检索为空的子问题**：analyzer 产出空 findings + 低可信度；writer 的 user prompt 对应章节是"（无）"，模型被要求如实写"信息不足"。这是与 L4 呼应的防幻觉第二道闸。
- **来源边界**：writer 只能引用 `analysis["sources"]`（来自 outcome.sources()），不能自己加来源。

### 完整流程串联
analyzer 对 4 个子问题各产出 2 条 findings + summary → `_build_user_prompt` 形成"### 子问题：... 关键发现：- ... 可信度：中 ... 来源：- 标题(url)" → writer 输出初稿：摘要 + 按子问题的正文（每章末列出来源）+ 结论。若某题检索为空，正文该章写"信息不足/未检索到有效数据"。

### 回顾与复述任务
指出"来源列表"从哪个对象（字段）来、经过哪几个函数，最后出现在报告哪一节；如果 analyzer 想偷偷补充模型自己的知识，prompt 的哪句约束会阻止它？

### 大纲状态：已展开

---

## L6 审核闭环：评分、修订与防死循环

### 场景与目标
报告质量如何被量化把关？不合格如何回流修订？如何保证一定终止？

### 主链
`writer` → `ReviewerAgent.review(topic, draft)` → 返回 {score,suggestions,issues} → `graph._review_node` 记轮次/历史 → `_route_after_review` 条件路由 → `writer`（修订）或 `finalize`。

### 编号阅读步骤
1. `app/agents/reviewer.py`：四维审核（完整性/准确性/逻辑性/可读性）；`review()` 把 score 强转 int 并 `clamp(1, 10)`；返回 `suggestions/issues`。注意 system prompt 说"8 分及以上合格"，但路由按 `settings.review_pass_score`（默认 7）判定——**实现为准**。
2. `app/graph/research_graph.py::_review_node`：`review_rounds + 1`；`review_entry` 写入 `review_history`（增量字段，靠 Annotated add 追加，不覆盖历史）；`review_feedback = "\n".join(suggestions)`。
3. `_route_after_review`：两个结束条件任一满足即 `finalize`：`last_score >= pass_score(7)` **或** `rounds >= max_review_rounds(2)`；否则 `revise`。
4. `app/config.py`：`MAX_REVIEW_ROUNDS=2`、`REVIEW_PASS_SCORE=7` 可被环境变量覆盖——防死循环上限可调。

### 重要分支
- **通过即停**：第一轮 ≥7 分直接 finalize（批量实测里多数任务 1 轮通过，评分 7-8）。
- **不通过且有轮次**：回 writer `revise`，下一轮以"修订稿"再审。
- **永不通过**：轮次到 2 后强制 finalize，接受"带缺陷但已尽力"的稿子，绝不无限循环（tests/test_graph.py::test_review_loop_hits_max_rounds 专门验证）。

### 完整流程串联
初稿 → reviewer 打 5 分 + suggestions（"缺数据支撑"）→ rounds=1 <2 且 5<7 → revise → writer 出修订稿 → reviewer 打 9 → finalize。历史里有两条 review_entry（5 分与 9 分），最终报告与审核历史一起落库（L7）。

### 回顾与复述任务
解释条件边函数返回的 `"revise"/"finalize"` 如何与 `add_conditional_edges(..., {"revise": "writer", "finalize": "finalize"})` 的映射对应；如果把 max_review_rounds 改成 0，行为会怎样（结合路由条件推导）。

### 大纲状态：已展开

---

## L7 持久化与状态流转：pending → completed/failed

### 场景与目标
工作流产生的中间/终态数据存放在哪、查询与删除如何读库、为什么状态在多个 DB 会话间流转。

### 主链
`app/db/models.py::ResearchTask` → `app/db/database.py`（engine/SessionLocal/init_db）→ `TaskService`（create/get/list/delete/run）→ routes 的查询/报告/删除接口。

### 编号阅读步骤
1. `app/db/models.py`：`ResearchTask` 单表 `research_tasks`：`topic/status`；JSON 字段 `sub_questions/search_results/analysis_results/review_history/logs`；Text 字段 `draft_report/final_report/error`；时间戳 `created_at/updated_at/completed_at`（completed_at 初始 nullable）。
2. `app/db/database.py`：`create_async_engine(settings.database_url)`（默认 `sqlite+aiosqlite:///.../data/agentforge.db`）；`SessionLocal` 用 `expire_on_commit=False`（commit 后对象字段仍可读）；`init_db` 建表（FastAPI lifespan 启动时调用）；`get_session` 是 FastAPI 依赖。
3. `app/services/task_service.py`：`create_task`（pending）、`get_task`（`session.get`）、`list_tasks`（按 created_at 倒序 + limit/offset）、`delete_task`、`run_task`（L1 已读）。
4. `_serialize_state`：把图最终 state 的 `SearchOutcome` 对象转成 JSON 安全结构（每个 question 一条 `{question, documents, rounds, log}`），其余字段平铺。
5. `app/routes/tasks.py`：`_task_to_dict`（列表视图，轻量）与 `_task_detail`（详情视图，含 analysis/draft/final/review_history）；`GET /api/tasks/{id}/report` 在非 completed 时返回 **409**；`DELETE` 返回 200/404。
6. `app/routes/reports.py`：`GET /api/reports/{id}/download` 以 `PlainTextResponse` 返回 final_report；未完成或为空 → 409。

### 重要分支
- **状态语义**：`pending`（已建库未执行）→ `running`（后台开始）→ `completed`（有 final_report + completed_at）或 `failed`（error 非空）。`GET /report` 只允许 completed，其余 409——前端/调用方要处理该语义。
- **跨会话一致性**：run_task 在"置 running"、"写完成"、"写失败"各用独立 SessionLocal，避免长事务；每次重新 `session.get(task_id)` 拿最新行。
- 没有任何清理/重试机制：failed 任务不会自动重跑，删除需显式 DELETE。

### 完整流程串联
POST 创建 id=1 pending → GET /api/tasks/1 立刻能看到 pending（logs 为空）→ 后台完成写回后，GET /api/tasks/1 返回 status=completed + final_report + review_history；此时 GET /api/reports/1/download 返回纯文本报告；DELETE /api/tasks/1 删除该行。若中途异常，GET 会看到 failed + error 字段。

### 回顾与复述任务
说出 ResearchTask 里哪些字段是"过程留痕"（logs/review_history/draft_report），哪些是"终态结果"（final_report/status/completed_at）；如果前端列表要显示 50 条任务但不想要大字段，应使用哪个序列化函数、为什么。

### 大纲状态：已展开

---

## L8 前端轮询：从"提交"到"看报告"

### 场景与目标
Streamlit 如何与 FastAPI 交互：提交任务、轮询进度、超时保护、完成后渲染报告与过程详情。

### 主链
`frontend/app.py` → `create_task()`（POST /api/tasks）→ 循环 `fetch_task()`（GET /api/tasks/{id}）→ 状态 completed 后渲染 final_report。

### 编号阅读步骤
1. `frontend/app.py`：`API_URL = os.getenv("API_URL", "http://localhost:8000")`——前端可用环境变量指向后端（docker-compose 里指 `http://api:8000`）。
2. `create_task(topic)`：POST JSON，`raise_for_status`，返回 `resp.json()["data"]["id"]`；异常时 `st.error` 并返回 None。
3. `fetch_task(task_id)`：GET 详情，返回 `data`。
4. 主循环：`max_polls = 150`（约 5 分钟：150 × 2s），`while task and task["status"] in ("pending","running") and polls < max_polls`：每 2 秒展示最近 6 条 logs 再拉一次。
5. 结束处理：仍 pending/running → warning（后台继续，可去历史看）；completed → success + `st.markdown(final_report)` + expander 展示子问题/审核轮次/审核历史；failed → error。
6. `tab_history`：刷新按钮 `st.rerun()`；GET /api/tasks 列表，每条 expander 显示 id/topic/status/时间/logs。

### 重要分支
- **轮询上限**：超过 150 次不再阻塞页面，提示"仍在后台运行"——避免长任务让前端无限转圈。
- **错误分支**：请求异常显示错误，不 crash；任务 failed 时展示 `task["error"]`。

### 完整流程串联
用户输入"Python 异步编程最佳实践"→ create_task 得到 id → 页面每 2 秒刷新状态与最近日志（"规划完成…"→"搜索完成…"→"报告初稿完成"→"第1轮审核：8 分"）→ completed 后整份 Markdown 报告渲染在页面，过程详情折叠展示。

### 回顾与复述任务
指出轮询的退出条件（三个）；如果后端任务 6 分钟才完成，前端会显示什么提示，用户该去哪里看结果？

### 大纲状态：已展开

---

## L9 运行与测试体系：脚本、mock 测试与真实数据

### 场景与目标
项目如何保证"能离线验证、能真实跑、能批量留痕"，以及测试到底覆盖了哪些行为、没有覆盖什么。

### 主链
离线：`pytest`（conftest 强制 LLM_MODE=mock）→ `tests/test_graph.py` 注入 Fake Agent 验证编排。
真实：`python scripts/run_e2e.py "主题"`（要求真实 key）→ 记录 `data/run_result.json`；`python scripts/run_batch.py` → 汇总 `data/batch_results.json`。

### 编号阅读步骤
1. `tests/conftest.py`：在 import app 前 `os.environ.setdefault("LLM_MODE","mock")`，并把项目根加进 sys.path——保证测试离线、可重复。
2. `tests/test_graph.py`：FakePlanner/FakeSearcher/FakeAnalyzer/FakeWriter/FakeReviewer；三个用例分别验证：一轮通过（write 1 次、无 revise）、先 5 分后 9 分（revise 1 次）、永远 5 分（到 max_review_rounds 强制结束、不 dead loop）。**这是"编排逻辑"而非"模型质量"的测试**。
3. `tests/test_agents.py`：mock 模式下 Planner/Analyzer/Reviewer 能返回结构合法结果（依赖 L3 的关键字 mock）。
4. `tests/test_base.py`：`extract_json` 的四种情况（纯 JSON/代码围栏/带杂讯/非法）。
5. `tests/test_calculator.py`：`safe_eval` 合法表达式（四则/括号/sqrt/幂）与危险表达式（`__import__`/`open`/`[1,2]`/`1;2`/`import sys`/`().__class__`）——白名单的证明。
6. `scripts/run_e2e.py`：`settings.validate_for_live()`（缺 key 直接报错）→ `graph.invoke` → 记录 topic/status/elapsed/sub_questions/review_rounds/review_history/search_log/final_report → 写 `data/run_result.json`。
7. `scripts/run_batch.py`：内置 5 个主题；`run_one` 每个主题单独 try/except（失败记 failed+error，不影响后续）；汇总写 `data/batch_results.json`。
8. 真实数据佐证：`data/batch_results.json`（5 条，完成率 5/5、平均约 82s、评分 7-8）与 `data/run_result.json` 已在仓库（后者是 08-16 真实端到端记录）。

### 重要分支与诚实边界
- mock 只验证"流程对不对"，**不验证"模型输出质量"**；真实质量必须靠 live 模式跑。
- 测试**没有**覆盖：HTTP 路由层（无 httpx/TestClient 用例）、数据库持久化、前端逻辑、失败任务恢复、并发任务。
- 计算器/长期记忆：`CalculatorTool` 仅在 `app/mcp_server.py` 与测试中使用；`MemoryService` 定义了但主流程未调用——面试/简历不要声称"系统内置长期记忆已接入主链路"。

### 完整流程串联
开发者无 key：`pytest -v` → 22 项通过（conftest 强制 mock）→ 证明图/Agent/工具逻辑正确。要真数据：`.env` 配 key → `python scripts/run_e2e.py "2025年大模型行业趋势分析"` 得到真实耗时与报告 → 再 `python scripts/run_batch.py` 得到 5 主题汇总，均落 JSON 可复现。

### 回顾与复述任务
如果面试官问"你的测试怎么证明审核不会死循环"，请引用 `tests/test_graph.py` 的哪个用例、FakeReviewer 如何设置分数序列；再说明为什么这不能替代一次真实模型的长跑测试。

### 大纲状态：已展开

---

## 附：课程之外的源码地图（供自习）
- 配置入口：`app/config.py`；环境变量样例见 `.env.example`（DEEPSEEK_API_KEY/TAVILY_API_KEY/LLM_MODE/MAX_REVIEW_ROUNDS/REVIEW_PASS_SCORE/MAX_SUB_QUESTIONS 等）。
- MCP 对外暴露（未接入主流程）：`app/mcp_server.py`（fastmcp，暴露 rag 检索与安全计算器工具）。
- 部署文件（本机未验证）：`Dockerfile`、`docker-compose.yml`、`frontend/Dockerfile`。
- 记录数据：`data/run_result.json`、`data/batch_results.json`、`data/agentforge.db`、`data/chroma/`。
- 与本课程结论冲突的文档位置：`README.md`（searcher 图级循环示意）、`app/graph/research_graph.py` docstring、`app/agents/reviewer.py` 的"8 分合格"提示。
