# Gate G2 阶段报告（B1–B4）

日期：2026-09-11 ｜ 分支：codex/agentforge-upgrade ｜ 当前回归：pytest 103 passed / ruff All checks passed!

## B1 interrupt/resume（人机协同）
- 图：`build(checkpointer, enable_human_review=True)` 在 planner 后插入 `human_review`（interrupt），恢复用 `Command(resume=编辑后的子问题)`；默认路径不变。
- 服务/API：paused 状态持久化；`POST /api/tasks/{id}/resume`（404/409）。
- 前端：paused 时展示可编辑子问题 + "继续执行"按钮。
- E2E（进程内 TestClient）：pending → paused → resume → completed，编辑后的子问题被采用（`docs/upgrade/B1-interrupt-spike.md`）。

## B2 单进程 worker
- lifespan 启动 worker：原子 claim（UPDATE...RETURNING）、心跳、stale 恢复、attempts、cancel_requested。
- 取消：pending/paused 直接 canceled；running best-effort（安全点收敛）；completed/failed/canceled → 409。
- 轻量迁移（PRAGMA + ALTER TABLE）新增 locked_at/heartbeat_at/attempts/cancel_requested/metrics。
- E2E（进程内）：worker 领取 → 暂停 → 恢复 → 完成，约 1.3s（`docs/upgrade/B2-worker.md`）。
- 卡顿复盘：常驻 uvicorn 放入 shell_command 导致工具等待进程树（22.8 分钟），已改为进程内 ASGI 测试；另修复脏库/状态残留/网络搜索开关/演示库隔离。

## B3 任务指标
- `UsageTracker.record_node` + 图节点统一计时；`ResearchTask.metrics` 落库；`GET /api/tasks/{id}/metrics`；任务详情包含 metrics。
- 前端任务详情新增「📊 指标」Tab（LLM/Tavily 调用、tokens、估算成本、节点耗时表、搜索明细）。
- 边界：resume 记录恢复段的指标；usage 缺失记 null。

## B4 SSE（仅后端）
- `GET /api/tasks/{id}/stream`：事件 status/log/node/done/error；0.5s 轮询数据源；不做断线续传；前端保持轮询（用户决策 4A）。

## 提交链
```
6c589b2 feat(b3): 任务指标（节点耗时/token/搜索/成本）+ /metrics API + 前端指标页
28da3e5 docs(b2): 补进程内 E2E 结果与卡顿事件复盘
3a4660a docs(b2): 进程内 E2E 结果 + 卡顿事件复盘
d20dca2 feat(b2): 单进程 worker（原子 claim/心跳/stale 恢复/取消）+ 卡顿修复 A-D
94aba06 feat(b1): paused 持久化 + /resume API + 多页面前端 + E2E 验证
9ce1c3a feat(b4): 后端 SSE 事件流 + Gate G2 阶段报告
```

## Gate G2 建议抽验项（1–2 项）
1. 运行 `python scripts/e2e_review_flow_inprocess.py` → 期望 `E2E_OK`（暂停→编辑→恢复→完成）；
2. `GET /api/tasks/{id}/metrics`（或前端「📊 指标」Tab）查看节点耗时/token/成本；
3. `GET /api/tasks/{id}/stream`（curl）查看 status/log/node/done 事件顺序；
4. `pytest -q`（97 passed）与 `ruff check .`。

## 仍需 BLOCKED/人工核验
- GitHub Actions 远端绿结果（需推送）；
- 官方价格与真实账单核验；
- Ollama 真实调用冒烟（当前 Ollama 在运行，可随时补做）。