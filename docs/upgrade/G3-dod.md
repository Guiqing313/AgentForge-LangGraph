# G3 DoD 收口清单（对照 PLAN-v2.md 第 9 节）

日期：2026-09-11 ｜ 分支 codex/agentforge-upgrade ｜ 回归：pytest 98 passed / ruff All checks passed!

| DoD 项 | 状态 | 证据 |
|---|---|---|
| G0/G1/G2/G3 通过并留证据 | G0 ✅ / G1 ✅（用户签署）/ G2 ✅（独立复验）/ G3 ⏳ 待用户签署 | G0-baseline.md、A0-A5、B1-B4、G1-signoff.md、G2-report.md、本文件 |
| pytest + CI 全绿 | pytest ✅ 98 passed；ruff ✅；远端 CI ⏸（未推送，BLOCKED） | tests/、.github/workflows/ci.yml |
| local_search 真实非空 + KB 报告 | ✅ | docs/upgrade/A1-kb-report.md（hit_rate@3 0.90 / MRR 0.85）、MCP stdio 验证 |
| Memory 可复现演示 | ✅ 实现+测试+演示完成；**对外措辞待用户确认**（账本 claim-af-002 = 待确认） | tests/test_memory.py、scripts/demo_memory_task.py、A2-memory.md |
| interrupt/resume 可复现演示 | ✅ | tests/test_interrupt.py、scripts/e2e_review_flow_inprocess.py（E2E_OK）、B1-interrupt-spike.md |
| worker + 恢复 + 取消 + 轻量迁移 | ✅（running 取消为 best-effort） | app/worker.py、tests/test_worker.py、tests/test_claim_race.py、B2-worker.md |
| metrics API + 前端展示 | ✅ | /api/tasks/{id}/metrics、tests/test_metrics.py、前端「📊 指标」Tab、B3-metrics.md |
| SSE 后端接口（不做断线续传） | ✅（paused 发 interrupt 后关闭该次流；p50 3.5ms） | tests/test_stream.py、scripts/measure_sse_latency.py、B4-sse.md |
| 本地 live ≥2 主题且成本 ≤10 元 | ✅ Ollama 2/2；DeepSeek 对比 1 次（阶段估算 ¥1.9945） | data/live_results.json、A5-live-cost.md |
| README 与真实能力一致 | ✅ | README.md（含能力边界与"规划中"标注） |
| 账本同步 | Memory/人机协同 = 待确认（等用户措辞确认）；YAML/多工作流模板 = 不采用；新增 worker/metrics/SSE/本地知识库 = 已确认 | 黄展亮-AI应用工程师-主张证据账本.json（16 条，validator 通过） |
| 未落地项标注"规划中" | ✅ | README「能力边界」；账本 claim-af-004 |

## G2 五项收口（已完成）
1. G2-report.md 提交链补 `9ce1c3a`、移除"待补"；
2. B1-interrupt-spike.md 头部与第 5 节改为"已完成"；
3. SSE 增加 `interrupt` 事件（paused 时发送一次后关闭该次流），PLAN/B4 文档已同步；
4. SSE 首事件 p50 已测量：`samples=[16.6,4.1,3.5,3.5,3.5] ms`，p50=3.5ms（≤2s）；
5. tests/test_stream.py 增加事件顺序断言与 interrupt 测试。

## 仍需用户/外部处理（BLOCKED）
- GitHub Actions 远端绿结果：需要推送后触发；
- 官方价格与真实账单核验；
- Memory / 人机协同的最终对外措辞确认（G3 需用户点头）；
- 真实 Ollama 生成路径的完整演示（可选，当前 Ollama 运行中）。
