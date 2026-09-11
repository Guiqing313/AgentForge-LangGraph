# B3 任务指标（metrics）

日期：2026-09-11 ｜ 状态：✅ 实现 + 测试通过 ｜ 成本：0

## 1. 目标
把单任务执行过程量化并持久化：节点耗时、LLM 调用与 token、搜索次数（Tavily/cache/DDG/local）、JSON 解析失败、估算成本。

## 2. 实现
- `UsageTracker` 新增 `record_node()` 与 `node_latencies`；`snapshot()` 输出 `tavily_calls`、`node_latencies`、`estimated_cost_cny` 等。
- `ResearchGraph.build()` 用 `_timed(name, fn)` 包装 6 个节点（planner/searcher/analyzer/writer/reviewer/finalize）；无 tracker 时零开销。
- `ResearchTask.metrics`（JSON 列，轻量迁移新增）；`_write_completed(task_id, serialized, metrics)` 落库。
- `TaskService.run_task / run_task_with_review / resume_task` 均把 `tracker.snapshot()` 写入 metrics。
- API：`GET /api/tasks/{id}/metrics`；任务详情 `GET /api/tasks/{id}` 也返回 `metrics`。
- 前端：任务详情新增「📊 指标」Tab（LLM/Tavily 调用、tokens、估算成本、节点耗时表、搜索明细）。

## 3. 测试
- `tests/test_metrics.py`：图节点耗时记录；通过 `TaskService.run_task` 后 `/metrics` 与详情返回 metrics；不存在任务 404。
- 回归：`pytest → 95 passed`；`ruff → All checks passed!`。

## 4. 边界
- `resume_task` 记录的是恢复执行段的指标（暂停前的片段不累计）；如需全链路累计，后续可把 metrics 合并。
- 本地 Ollama 的 token 由 OpenAI 兼容端点返回；若缺失则记 null，不按 0 计。
