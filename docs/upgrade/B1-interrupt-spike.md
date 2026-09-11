# B1 interrupt/resume（图级）证据

日期：2026-09-11 ｜ 状态：图级完成 ✅ ｜ API/前端 ⏳ 待做 ｜ 成本：0（mock LLM）

## 1. Spike（纯图，SQLite checkpointer）
命令：`python scripts/spike_interrupt.py`
```
phase1_interrupted=True planner_calls=1 proposed=['原始A', '原始B']
phase2_received=['编辑后的A', '编辑后的B', '编辑后的C'] planner_calls=1
SPIKE_OK
```
结论：interrupt → `Command(resume=...)` → **关闭并重开 SqliteSaver（模拟进程重启）** 后仍可恢复；编辑后的子问题被采用；planner 不重复执行。

## 2. 依赖
- 安装 `langgraph-checkpoint-sqlite==3.1.1` + `sqlite-vec==0.1.9`（A4 已 pin；安装前已备份 pip freeze，安装后 81 项回归通过）。
- `SqliteSaver` / `AsyncSqliteSaver` 均可导入。

## 3. 真实图集成
- `ResearchGraph.build(checkpointer=None, enable_human_review=False)`：
  - 默认行为不变（planner → searcher）；
  - `enable_human_review=True` 时插入 `human_review` 节点（planner → human_review → searcher），要求提供 checkpointer，否则抛 ValueError。
- `human_review` 节点：`interrupt({sub_questions, message})`；恢复时清洗用户编辑（去空/去重/保持顺序）；空编辑回退原提案；日志记录"人工确认：N 个子问题"。

## 4. 测试与演示
- `tests/test_interrupt.py`（3 项）：编辑后采用 + planner 只跑一次；缺 checkpointer 报错；空编辑回退原提案。
- 回归：`pytest → 84 passed`；`ruff → All checks passed!`。
- 真实图演示：`python scripts/demo_interrupt.py`（AsyncSqliteSaver + mock LLM）
```
paused=True proposed=['背景与现状', '核心技术', '应用与落地', '挑战与趋势']
status=completed sub_questions=['编辑：RAG 的核心流程', '编辑：Agent 的工具调用']
report_chars=59
DEMO_OK
```

## 5. 待做（B1 剩余）
- `TaskService` 的 `paused` 状态持久化 + `POST /api/tasks/{id}/resume` 接口；
- Streamlit 展示 paused 并提供子问题编辑/恢复按钮；
- `HUMAN_REVIEW_ENABLED` 开关与 API 测试（404/409/正常 resume）。

## 6. 边界
- 本阶段全部使用 mock LLM（不调用 Ollama/DeepSeek）；真实生成路径的 interrupt/resume 演示待 Ollama 启动后可选补做。
- checkpoint 数据库：`data/checkpoints.sqlite`（已加入 .gitignore：`*.sqlite`）。

## 7. 端到端 API 验证（2026-09-11）
启动：`LLM_MODE=mock HUMAN_REVIEW_ENABLED=true uvicorn app.main:app --port 8000`（mock 避免外部依赖）。

流程与结果（任务 #3「B1 端到端测试：RAG 与 Agent」）：
```
status=completed
sub_questions=编辑后的子问题A | 编辑后的子问题B
review_rounds=1
logs=规划完成：分解为 4 个子问题（注入 3 条历史记忆）
   || 人工确认：2 个子问题
   || 搜索完成「编辑后的子问题A」：1 条资料，1 轮
   || 搜索完成「编辑后的子问题B」：1 条资料，1 轮
   || 分析完成「编辑后的子问题A」：2 条关键发现
   || 分析完成「编辑后的子问题B」：2 条关键发现
   || 报告初稿完成
   || 第1轮审核：7 分
```
结论：API 路径（`POST /api/tasks` → 轮询 paused → `POST /api/tasks/{id}/resume` → completed）真实工作；用户编辑的子问题被采用；记忆注入与任务守卫同样生效。

## 8. 前端（v2.0）
- 多页面：发起研究 / 任务历史 / 知识库 / 实验对比 / 系统信息；支持 URL 深链接（`?page=kb` 等）。
- paused 任务：前端展示可编辑子问题 + "继续执行"按钮（调用 resume API）。
- 知识库页：语料/分块统计 + 检索预览；实验对比页：Ollama vs DeepSeek 真实数据；系统页：provider/上限/价格授权/MCP 工具。
- 截图：`ui_01_new_research.png` ~ `ui_05_history.png`（证据目录）。
