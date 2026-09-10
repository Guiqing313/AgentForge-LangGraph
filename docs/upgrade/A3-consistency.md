# A3 一致性与安全修复（已完成）

日期：2026-09-10 ｜ 状态：✅ 通过 ｜ 外部 API 成本：0 元

## 1. 目标
修复文档与实现的已知不一致、补 NOne 保护与删除语义、给超时加"如实说明"的软超时，并让 mock e2e 真正可跑。

## 2. 改动
| # | 问题 | 修复 |
|---|---|---|
| A3-1 | reviewer prompt 写"8 分合格"，配置默认 7 分 | 新增 `reviewer.system_prompt()`，合格分从 `settings.review_pass_score` 渲染（模板占位符替换，不用 `.format` 以免与 JSON 示例冲突） |
| A3-2 | graph docstring/README 画了"searcher 图级循环"，实现没有该条件边 | docstring 改为"searcher 单节点并行 + 每个子问题内部最多 2 轮（无图级回路）"；README mermaid 边改为"每个子问题内部最多 2 轮 / 全部子问题处理完" |
| A3-3 | DELETE 可直接删除 running 任务 | `DELETE /api/tasks/{id}`：running/paused → **409**；404 语义保持不变 |
| A3-4 | `run_task` except 分支无 None 保护 | 任务记录不存在时记录警告并跳过失败写回，不再 `AttributeError` |
| A3-5 | 无超时控制 | 新增 `TASK_SOFT_TIMEOUT_SECONDS`（默认 900），用 `asyncio.wait_for` 包裹 `to_thread(graph.invoke)`；超时抛 RuntimeError 并标记 failed |
| A3-6 | mock 模式 e2e 仍强制 `validate_for_live()` | 新增 `needs_live_validation()`；mock 跳过校验；mock 默认输出改为 `data/run_result.mock.json`，**保护已跟踪的 `data/run_result.json` 真实记录** |
| A3-7 | 无回归测试 | 新增 `tests/test_consistency.py`（7 项） |

## 3. 超时的诚实语义（重要）
- `asyncio.wait_for` 只取消 `await`；`graph.invoke` 已在 `asyncio.to_thread` 的线程池里执行，**线程不会被强制终止**。
- 超时后：任务标记 failed、错误信息写明"后台线程可能仍在收尾，本次结果不写回"；不会声称"立即停止所有模型/搜索调用"。
- 若外部取消 run_task（CancelledError 属于 BaseException，不被 `except Exception` 捕获），任务可能停留在 running，直到 B1 的 stale recovery 接管。
- 硬中止需要独立进程，不在本轮范围。

## 4. 验证证据

### 4.1 测试
```
D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe -m pytest -q
44 passed in 3.08s
```
（22 基线 + 6 provider + 3 KB + 6 Memory + 7 Consistency）

### 4.2 mock e2e（此前失败，现已通过）
```powershell
$env:LLM_MODE="mock"
python scripts/run_e2e.py "冒烟主题" --out <evidence>/A3-mock-e2e.json
```
结果：正常生成 mock 报告并写出 JSON（1205 字节）；未覆盖 `data/run_result.json`。

### 4.3 新增测试清单
`tests/test_consistency.py`：
1. reviewer prompt 使用配置合格分（9 分场景）；
2. DELETE running → 409；
3. DELETE completed → 200；
4. mock 模式 `needs_live_validation() == False`；
5. 软超时配置存在且合法；
6. README/docstring 与真实图结构一致（防止再次漂移）；
7. MockLLM 仍可用。

## 5. 成本
0 元（全部离线/mock 或本地）。

## 6. 下一步
A4：CI + API/失败路径测试 + 依赖锁定（pyproject/ruff、TestClient、临时 DATABASE_URL、requirements pin）。