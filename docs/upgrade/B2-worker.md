# B2 单进程 worker（claim / 心跳 / 恢复 / 取消）

日期：2026-09-11 ｜ 状态：✅ 实现 + 测试通过 ｜ 成本：0

## 1. 设计（用户选择单进程方案）
- FastAPI lifespan 内启动一个后台 worker 协程：轮询 `pending` → 原子 claim → 执行 → 心跳 → 收敛。
- claim：单条 `UPDATE ... WHERE id=(SELECT id ... WHERE status='pending') AND status='pending' RETURNING id`，保证同一任务只被领取一次；SQLite 写冲突时短暂退避重试。
- 心跳：运行期间每 `WORKER_HEARTBEAT_INTERVAL`（默认 5s）更新 `heartbeat_at`。
- stale 恢复：启动时把 `running` 且心跳早于 `WORKER_STALE_SECONDS`（默认 600s）的任务恢复为 `pending`；超过 `WORKER_MAX_ATTEMPTS`（默认 2）则 `failed`。
- 取消（best-effort）：`pending/paused` → 直接 `canceled`；`running` → 置 `cancel_requested`，worker 在安全点（任务结束后）收敛为 `canceled`；`completed/failed/canceled` → 409。
- 迁移：轻量 `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`（不引入 Alembic），新增 `locked_at/heartbeat_at/attempts/cancel_requested`。
- API：`POST /api/tasks` 只入库（不再在 API 进程内起协程）；`POST /api/tasks/{id}/cancel`；DELETE running/paused → 409（A3 已有）。

## 2. 卡顿问题修复（A–D）
针对"连续两次运行像卡死"的排查结论（后端未卡死：任务 #4 在 1.07s 内完成；主因是脏开发库遗留的真实模型任务 + 我的长 shell 命令 + 输出缓冲）：

| 项 | 修复 |
|---|---|
| A 状态卫生 | `completed/failed/paused/canceled(pending/paused)` 时清空 `locked_at/heartbeat_at`（此前任务完成后仍残留） |
| B 演示库隔离 | 新增 `scripts/reset_demo_db.py`（只允许操作 `data/` 下文件）；演示/E2E 使用独立 `DATABASE_URL`，不再复用开发库 |
| C 网络搜索开关 | 新增 `WEB_SEARCH_ENABLED`（默认 true）；演示设 false 时只走本地知识库，避免无 Tavily key 时 DuckDuckGo 8s 超时拖慢 |
| D E2E 脚本化 | 新增 `scripts/e2e_review_flow.py`（短轮询、增量打印、`--max-wait`），替代"重启+固定 sleep+长轮询"的 shell 链 |

演示推荐配置：
```powershell
python scripts/reset_demo_db.py
$env:DATABASE_URL="sqlite+aiosqlite:///<repo>/data/demo.db"
$env:CHECKPOINT_DB="<repo>/data/demo_checkpoints.sqlite"
$env:LLM_MODE="mock"; $env:HUMAN_REVIEW_ENABLED="true"; $env:WEB_SEARCH_ENABLED="false"
uvicorn app.main:app --port 8001
python scripts/e2e_review_flow.py --api-url http://127.0.0.1:8001
```

## 3. 测试
- `tests/test_worker.py`：claim 唯一性、stale 恢复/超次数失败、取消语义、完成后清锁。
- `tests/test_claim_race.py`：3 个并发 claim 只有 1 个成功。
- `tests/test_failure_paths.py`：`WEB_SEARCH_ENABLED=false` 时不发起网络搜索。
- 回归：`pytest → 93 passed`；`ruff → All checks passed!`。

## 4. 端到端验证
见第 5 节（使用演示库 + mock + human review + 禁网）。

## 5. E2E 结果（待补）

## 5. E2E 结果（进程内 ASGI TestClient，无端口）

脚本：`scripts/e2e_review_flow_inprocess.py`（demo DB + mock + HUMAN_REVIEW_ENABLED=true + WORKER_ENABLED=true + WEB_SEARCH_ENABLED=false；TestClient 在进程内跑完 ASGI 生命周期，退出即释放 worker）。

```
[create] task_id=1 status=pending
[poll] status=pending
[poll] status=paused
[paused] proposed=['背景与现状', '核心技术', '应用与落地', '挑战与趋势']
[resume] status=completed
[poll] status=completed
[final] status=completed sub_questions=['E2E 编辑问题一', 'E2E 编辑问题二']
E2E_OK
```
结论：worker 领取 pending → human_review 暂停 → /resume 采用编辑后的子问题 → completed，全链路通过；耗时约 1.3 秒。

## 6. 卡顿事件复盘（重要）
- 原因：把 `Start-Process ... uvicorn ...` 常驻服务与 health check 放在同一条 shell_command 中，工具等待进程树结束 → 调用不返回（约 22.8 分钟）；与后端逻辑无关（health 200、任务早已完成）。
- 规避：常驻服务不放进会返回的 shell command；优先用 `TestClient`/ASGI 进程内测试；如必须起真实 uvicorn，用独立持久 session 启动、另一条命令跑 E2E、跑完显式停止并确认端口释放。
- 本文件后续 E2E 一律使用进程内脚本。
