# 复测修复记录（2026-09-11）

来源：子代理「复测」对 Phase A 的独立复测报告（基线 HEAD bbb5fa4）。用户选择方案 1：修 P1 + 关键 P2，然后由「复测」复跑。

| 复测发现 | 等级 | 修复 | 证据/测试 |
|---|---|---|---|
| 部分 usage 缺失时成本闸门 fail-open | P1 | `require_paid_usage`：prompt/completion 任一缺失即拒绝 | `test_require_paid_usage_partial_fails_closed` |
| 预算"先超支再中止" | P1 | 新增任务前保守预检 `estimate_task_upper_bound_cny` + `enforce_pre_task_budget`；Tavily 硬上限（`_reserve_tavily_call` 达上限直接抛出、不回退） | `test_pre_task_budget_rejects_before_running`、`test_search_call_limit_blocks_further_tavily` |
| `verified_at` 只校验非空字符串 | P1 | 拆分 `verified_at`（官方核验）与 `authorized_at`（用户授权占位价），均须合法 `YYYY-MM-DD`；`price_status` 三态 | `test_invalid_date_is_unauthorized`、`test_placeholder_authorization_allows_paid`、`test_default_prices_are_authorized_but_not_officially_verified` |
| `requirements-lock.txt` 名不副实 | P1 | 注释改为"直接依赖精确锁"；CI 增加 `pip freeze` + `upload-artifact` | `.github/workflows/ci.yml` |
| A5 文档自相矛盾 / RISKS HEAD 过期 | P1 | A5 顶部状态更正、第 3 节标注"已被第 8 节最终 run 取代"；RISKS 状态改为以 git log 为准 | `A5-live-cost.md`、`RISKS.md` |
| README Mermaid 仍有图级自环 | P2 | 删除 `C --> C`，重试说明移到节点标签 | `test_docs_match_real_graph_structure`（`"C --> C" not in readme`） |
| conftest 用 setdefault 可绕过 | P2 | 强制覆盖 `LLM_MODE=mock`、`DATABASE_URL=<temp>` | `test_tests_use_isolated_database` |
| loader 不校验 manifest | P2 | manifest 作为白名单；登记文件 sha256 不匹配则拒绝加载 | `test_loader_uses_manifest_whitelist`、`test_loader_rejects_manifest_sha_mismatch` |
| Memory 阈值未做敏感度实验 / eval 外推有限 | P2 | 不改代码，保留文档披露（阈值 0.35 为初值、10 题为小型冒烟指标） | A1/A2 报告 |

## 回归

```
pytest → 74 passed
ruff check . → All checks passed!
```

- 本次未调用 DeepSeek/Tavily，无新增外部支出。
- `config/prices.json`：`verified_at=null`（官方未核验）、`authorized_at=2026-09-10`（用户授权占位价执行过一次对比）。
- 上述修复需由「复测」复跑确认；结论以子代理报告为准。

## 第三轮修复（2026-09-11，全局收口）

针对「复测」第三轮发现的并发/完整性/路径覆盖问题，改为"单一收口点 + 原子预留"：

| 第三轮发现 | 修复 |
|---|---|
| 并发下 LLM 上限可被突破 | `UsageTracker` 内部加锁；`reserve_llm()`/`reserve_search()` 在锁内同时检查**累计启动数**（上限）与在途预留；并发测试 `test_concurrent_llm_reservation_is_atomic`（5 线程、上限 1 → 恰好 1 次通过） |
| 价格完整性漏 Tavily 费率 | `_rates_valid` 对 DeepSeek 同时要求 `input/output` 与 `tavily.per_credit_cny`；`test_missing_tavily_rate_blocks_deepseek` |
| TaskService/API 未接入限制 | `TaskService.run_task` 用同一个 `observability.track(...)` 包裹 `graph.invoke`，并走付费 gate；`test_task_service_attaches_budget_guard` |
| A5 旧测试数/旧语义 | 已更新为 77 项；旧"待授权/verified_at"段落已清理 |

修复后回归：`pytest → 81 passed`、`ruff All checks passed!`。
