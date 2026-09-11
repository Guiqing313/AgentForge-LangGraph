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
$env:DATABASE_URL="sqlite+aiosqlite:///D:/codex使用文件夹/AgentForge-v2/data/demo.db"
$env:CHECKPOINT_DB="D:/codex使用文件夹/AgentForge-v2/data/demo_checkpoints.sqlite"
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