# A2 Memory 接通（已完成）

日期：2026-09-10 ｜ 状态：✅ 通过 ｜ 外部 API 成本：0 元

## 1. 目标与边界
- 目标：接通**跨任务经验记忆**——任务完成后把主题/子问题/关键发现写入向量库；后续相似主题在规划前检索参考，并注入 planner。
- 明确边界（重要）：这**不是**完整的短期/长期记忆系统；短期图状态由 B1 的 checkpoint 负责。对外表述只能写"跨任务经验记忆"。
- 主张—证据账本 `claim-af-002`（记忆系统）：实现+测试+演示已齐，但仍需用户在 Gate G1/G3 最终点头后才允许从"不采用"改为"已确认"。

## 2. 改动文件
| 文件 | 说明 |
|---|---|
| `app/config.py` | 新增 `MEMORY_ENABLED/TOP_K/MAX_CHARS/MIN_SIMILARITY` 与 `_get_bool` |
| `app/services/memory_service.py` | `MemoryRecord`（uuid5 确定性 id）+ `MemoryService`（save/retrieve/count，cosine 相似度阈值、top_k、1500 字截断）；保留旧接口 |
| `app/graph/state.py` | 新增 `relevant_memories` 字段；`initial_state(topic, relevant_memories=...)` |
| `app/agents/planner.py` | `plan(topic, memories)` 注入"参考背景（来自历史任务，仅作参考，不得替代本次检索）" |
| `app/graph/research_graph.py` | `_plan_node` 传入记忆；日志记录"注入 N 条历史记忆"（可核验） |
| `app/services/task_service.py` | 执行前 retrieve → 注入 state；成功后 save；失败降级为无记忆/不阻塞任务 |
| `tests/test_memory.py` | 6 项离线测试（确定性 id、保存/检索、阈值过滤、空集合、planner 注入、配置默认） |
| `scripts/demo_memory.py` | 记忆服务直接演示（真实 embedding 服务） |
| `scripts/demo_memory_task.py` | 端到端演示（两个任务经 task_service 跑通记忆生命周期） |

## 3. 机制
- id：`uuid5(NAMESPACE, topic + task_id + created_at)`，跨进程稳定，不用 `hash()`。
- 存储：Chroma 集合 `agent_memory`（同一 bge-m3 HTTP embedding 服务，cosine）。
- 检索：`top_k`（默认 3）、`min_similarity`（默认 0.35，cosine 距离换算）、`max_chars`（默认 1500），按相似度降序。
- 注入：planner user prompt 增加"参考背景"段落，性格是"仅供参考，不得替代本次检索"。
- 生命周期：`task_service.run_task` 执行前 `retrieve`；任务 completed 后 `save`；检索/保存异常都只记录日志，不阻塞任务。
- 降级：空记忆返回 []；embedding 服务不可用 → 记忆检索失败被捕获，任务继续（无记忆）。

## 4. 验证证据

### 4.1 测试
```
D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe -m pytest -q
37 passed in 2.60s
```
（22 基线 + 6 provider + 3 KB + 6 Memory；全部离线确定性）

### 4.2 记忆服务直接演示（真实 embedding）
命令：`python scripts/demo_memory.py`
```
memory_id=37bc1c16-9312-5fdc-8455-a3509356b19e
count_before=0 count_after=1
retrieved=[{"similarity": 0.7054, "preview": "主题：RAG 检索增强生成 ..."}]
planner_result=['记忆注入成功']
planner_prompt_has_memory=True
DEMO_OK
```

### 4.3 端到端演示（task_service，真实 embedding + mock LLM）
命令：`python scripts/demo_memory_task.py`
```
task1_id=1 memory_count_before=1 after_first=2
task2_id=2 status=completed review_rounds=1
task2_logs=['规划完成：分解为 4 个子问题（注入 2 条历史记忆）', '搜索完成「背景与现状」：1 条资料，1 轮', ...]
memory_injection_log=['规划完成：分解为 4 个子问题（注入 2 条历史记忆）']
DEMO_OK
```
结论：任务1 完成后 `agent_memory` 计数增长；任务2（相似主题）执行时 planner 实际收到 2 条历史记忆，并在任务日志中留痕，可直接在 Gate G1 抽验。

## 5. 已知限制
1. `min_similarity=0.35` 为初值，尚未做阈值敏感度实验（可用 C4 评测扩展）。
2. 记忆库无淘汰/上限策略，长期运行会持续增长（本地演示规模可控）。
3. 记忆内容是模型生成的关键发现，可能携带错误；当前只作"参考背景"，不是权威事实，且 prompt 明确要求不得替代本次检索。
4. 未做记忆污染注入的对抗测试（已在 `tests/test_memory.py` 覆盖空/低相似度/异常降级，注入对抗建议放 C4）。
5. 演示数据库为 `data/demo_memory_task.db`（`*.db` 已被 .gitignore 忽略，不会提交）。

## 6. 下一步
A3 一致性修复（reviewer 合格分统一、docstring/README 与真实图结构对齐、DELETE 运行中 409、None 保护、软超时语义、mock e2e 跳过 live 校验）。