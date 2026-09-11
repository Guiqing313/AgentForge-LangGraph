# B4 后端 SSE 事件流

日期：2026-09-11 ｜ 状态：✅ 实现 + 测试通过 ｜ 成本：0

## 1. 目标
提供 `GET /api/tasks/{id}/stream`，按事件流推送任务进展：`status` / `log` / `node` / `done` / `error`。
按用户决策 4A：**只做后端接口 + 自动化测试，不做断线续传**；Streamlit 保持轮询。

## 2. 实现
- 路由 `app/routes/tasks.py::stream_task`：`StreamingResponse(media_type="text/event-stream")`，轮询数据库状态（0.5s）并增量推送：
  - `status`：状态变化；
  - `log`：新增执行日志；
  - `node`：新增节点耗时（来自 B3 的 metrics.node_latencies）；
  - `done` / `error`：终态收口后关闭。
- 头部 `Cache-Control: no-cache`、`X-Accel-Buffering: no`；不实现 Last-Event-ID 续传。
- 前端保持轮询（4A），未改流式渲染。

## 3. 测试
- `tests/test_stream.py`：不存在任务 404；已完成任务能收到 status/log/node/done 事件。
- 回归：`pytest → 97 passed`；`ruff → All checks passed!`。

## 4. 边界
- 事件源为数据库轮询（跨进程/worker 安全），不依赖进程内事件总线；代价是最小 0.5s 延迟。
- 不做断线续传：断线后需重新请求（符合用户决策）。
