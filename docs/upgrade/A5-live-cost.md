# A5 本地 live + 成本闸门（本地部分完成；DeepSeek 对比待用户授权）

日期：2026-09-10 ｜ 状态：本地 live ✅ / DeepSeek 对比 ⏸ 待授权 ｜ 外部 API 现金支出：0 元（Ollama 本地）

## 1. 目标
- 用真实 Ollama（qwen2.5:7b）+ 真实 Tavily 跑 ≥2 个主题，记录真实耗时/调用/用量/估算成本；
- 建立成本闸门：Tavily 调用上限、成本上限、付费 provider fail-closed；
- DeepSeek 对比（恰 1 次、≤2 元）需用户确认后执行。

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
| 	ests/test_cost_gate.py | 7 项成本/闸门测试 |
| data/live_results.json | 本次本地 live 的真实记录 |

## 3. 真实运行结果（Ollama + Tavily）
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
pytest → 60 passed
ruff check . → All checks passed!
`

## 7. 待用户授权（下一步）
- DeepSeek 对比：恰 1 次、≤2 元。需要用户确认 DeepSeek 官方价格（或授权按当前占位价 ¥2/M 输入、¥8/M 输出估算，实跑通常 <1 元），并把 config/prices.json 的 erified_at 置为确认日期后再执行。
- 语料公开：docs/kb/AI应用实习面试学习文档.md 是否允许随仓库公开到 GitHub（当前仅本地 commit，未推送）。

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
