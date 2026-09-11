# A5 本地 live + 成本闸门（已完成：本地 live + DeepSeek 对比）

日期：2026-09-10 ｜ 状态：✅ 本地 live + DeepSeek 对比均已完成 ｜ 外部 API 现金支出：约 ¥0.25（DeepSeek tokens；Tavily 免费额度内为 0）

## 1. 目标
- 用真实 Ollama（qwen2.5:7b）+ 真实 Tavily 跑 ≥2 个主题，记录真实耗时/调用/用量/估算成本；
- 建立成本闸门：Tavily 调用上限、成本上限、付费 provider fail-closed；
- DeepSeek 对比：✅ 已于 2026-09-10 经用户授权执行（结果见第 8 节）。

## 2. 新增/改动
| 文件 | 说明 |
|---|---|
| pp/cost.py | 成本模型 + 预算闸门（stimate_cost_cny / nsure_paid_provider_allowed / 
equire_paid_usage / nforce_budget） |
| config/prices.json | 价格表；erified_at 为空时付费 provider 被拒绝（fail-closed） |
| pp/tools/search.py | 进程内查询缓存 + last_backend（tavily/duckduckgo/cache） |
| pp/agents/searcher.py | 把本地/网络检索调用记入 UsageTracker |
| pp/graph/research_graph.py | 修复 contextvars 未传入搜索线程（copy_context）；搜索调用现可被统计 |
| pp/agents/base.py | JSON 解析失败后追加一次严格重试（本地 7B 偶发输出 Markdown） |
| scripts/run_live_local.py | 本地 live 运行 + 成本闸门；--compare-deepseek --allow-paid 为付费入口 |
| `tests/test_cost_gate.py` | 成本/闸门测试（随复测修复扩充；当前全量 81 项通过） |
| data/live_results.json | 本次本地 live 的真实记录 |

## 3. 第一轮本地 run（已被第 8 节最终 run 取代，仅作过程记录）
| 主题 | 状态 | 耗时(s) | 子问题 | 审核轮次 | Tavily 调用 | LLM 调用 | prompt/completion tokens | 估算成本(¥) |
|---|---|---:|---:|---:|---:|---:|---|---:|
| RAG 与 Agent 的区别 | completed | 49.77 | 3 | 1 | 6 | 9 | 13309 / 1696 | 0.348 |
| 大模型应用工程师需要哪些能力 | completed | 61.38 | 3 | 1 | 4 | 10 | 12275 / 2428 | 0.232 |
| **合计** | **2/2** | — | 6 | 2 | **10** | 19 | 25584 / 4124 | **0.58** |

- 成本口径：Ollama 本地推理 = 0 元；Tavily 按 config/prices.json 占位单价 ¥0.058/credit 估算，10 次调用 ≈ ¥0.58。
- 若 10 次调用在 Tavily 免费额度（1000 credits/月）内，**实际现金支出为 0**；付费单价需用户核对官方价格页。
- 重要实测发现：Ollama 的 OpenAI 兼容端点在本次运行中**返回了 usage**（prompt/completion tokens 均被记录），token 统计可用。

## 4. 运行中发现并修复的两个真实问题
1. **搜索调用未被统计**：UsageTracker 用 contextvars，但搜索在 ThreadPoolExecutor 子线程执行，current_tracker() 为 None。修复：提交任务前 contextvars.copy_context()，子线程继承 tracker。修复后统计到 6+4=10 次 Tavily 调用。
2. **本地 7B 偶发非 JSON 输出**：第一次运行时第二个主题的 analyzer 返回 Markdown 而非 JSON，导致图失败。修复：_chat_json 解析失败后追加一次"只输出 JSON"的严格重试；重跑后 2/2 完成。

## 5. 成本闸门当前状态
- config/prices.json 的 erified_at = null → **付费 provider 被 fail-closed 拒绝**；
- scripts/run_live_local.py 的 --compare-deepseek 需同时满足：--allow-paid + 价格表 erified_at 非空；
- 付费 provider 若拿不到 usage，
equire_paid_usage 直接拒绝继续；
- 每次任务后 nforce_budget 检查 Tavily 调用数与累计估算成本，超限立即中止。

## 6. 验证
`
pytest → 81 passed
ruff check . → All checks passed!
`

## 7. 授权状态（均已完成）
- DeepSeek 对比：✅ 已于 2026-09-10 经用户授权执行（占位价，授权已消费）；再次付费运行需重新授权或提供官方价格核验。
- 语料公开：✅ 用户选择不公开；该文档已从语料移除并重建索引（A1 v2）。

## 8. DeepSeek 对比（已执行，用户授权 A）

日期：2026-09-10 ｜ 授权：用户确认按占位价执行（DeepSeek 阶段 ≤2 元）

| provider | 主题 | 状态 | 耗时(s) | 子问题 | 审核 | Tavily | LLM 调用 | prompt/completion tokens | 估算成本(¥) |
|---|---|---|---:|---:|---:|---:|---:|---|---:|
| ollama | RAG 与 Agent 的区别 | completed | 48.84 | 3 | 1 | 5 | 9 | 12677 / 1816 | 0.2900 |
| ollama | 大模型应用工程师需要哪些能力 | completed | 90.85 | 3 | 1 | 5 | 11 | 13437 / 3800 | 0.2900 |
| deepseek | RAG 与 Agent 的区别 | completed | 48.77 | 5 | 1 | 15 | 13 | 37759 / 6625 | 0.9985 |
| deepseek | 大模型应用工程师需要哪些能力 | completed | 46.31 | 5 | 1 | 15 | 13 | 37022 / 6497 | 0.9960 |

- Ollama 阶段合计：Tavily 10、tokens 26114/5616、估算 ¥0.58。
- DeepSeek 阶段合计：Tavily 30、tokens 74781/13122、估算 **¥1.9945**（其中 Tavily 30 credits ≈ ¥1.74、DeepSeek tokens ≈ ¥0.25），在用户授权的 ≤2 元范围内。
- 合计估算 ¥2.5745；若 Tavily 调用在免费额度（1000 credits/月）内，**实际现金支出约 ¥0.25（DeepSeek tokens）**。

### 诚实边界（必须保留）
1. **不是控制变量实验**：Ollama 的 planner 产出 3 个子问题，DeepSeek 产出 5 个，检索次数与上下文规模不同；因此只能说"两者均 2/2 完成、耗时相近"，**不能声称"某模型更好"**。
2. DeepSeek 阶段产生了 30 次 Tavily 调用（因为 planner 查询词不同，进程内缓存未命中），并非"复用同一批搜索结果"。
3. 运行脚本在合并预算检查时报 `BudgetExceeded` 并中止，**未写出 JSON**；本文件的数字来自该次运行的真实 stdout，并已重建到 `data/live_results.json`。
4. 预算语义已修复：`--max-cost-cny` 为外部 API 总上限（默认 10 元），`--max-paid-cost-cny` 为付费阶段上限（默认 2 元，对应用户授权）；并改为每个 provider 阶段后增量落盘，避免中止丢数据。

## 9. 复测修复（2026-09-11）
- partial usage fail-closed、预算前置、价格语义、Tavily 硬上限、文档一致性、README 自环、conftest 强隔离、loader manifest 白名单均已修复；详见 `docs/upgrade/REMEDIATION-retest.md`。
- 修复后回归：pytest 81 passed、ruff All checks passed。
