# AgentForge v2.0 风险登记与用户介入清单

> 来源：2026-09-10 侧边对话风险交接 + 主线程核验。执行中命中"必须用户介入/硬停止"条目时立即停下询问。
> 当前状态快照：分支 `codex/agentforge-upgrade`（HEAD 以 `git log -1` 为准）；Phase A 已完成并经「复测」复测，修复记录见 `docs/upgrade/REMEDIATION-retest.md`；Ollama 当前停止；embedding 服务由用户启动时运行于 127.0.0.1:11435。

---

## 一、必须用户介入（AI 做不到 / 硬阻塞）

| # | 事项 | 触发时机 | 用户动作 |
|---|---|---|---|
| U1 | 进程与续跑 | AI turn 被中断后 | 回复"继续"；AI 不会自续 |
| U2 | Git 推送/凭据 | 需要推送远端时 | 用户执行 `git push` 或授权（沙箱读不到 Windows Git 凭据） |
| U3 | Docker | Phase A/B 完成后 | 用户决定是否安装（需管理员权限 + GUI） |
| U4 | 付费授权与账单 | 调用 DeepSeek / Tavily 超额前 | 用户确认（DeepSeek 恰 1 次、≤2 元；AI 看不到真实账单） |
| U5 | 环境持久化 | 重启电脑/服务后 | 显式设置 `OLLAMA_MODELS=D:\OllamaModels` |
| U6 | 残留进程收尾 | turn 中断后 | 用户按下方 stop 命令收尾（AI 无法跨 turn 保证清理） |

### 后台进程与停止命令（U6）
```powershell
# embedding 服务（当前 PID 24040）
Stop-Process -Id 24040 -Force

# Ollama（用户自行启动的，按需停止）
Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force

# 查看端口占用
netstat -ano | findstr ":11435 :11434"
```

---

## 二、Gate 用户抽验项（不能只凭 AI 总结）

| Gate | 用户抽验项（选 1–2 项现场/复核） |
|---|---|
| G0 | ✅ 已通过：`python -m pytest -q` 22 项；`ollama list` 两个模型 |
| G1 | ① `LocalSearchTool().search("RAG 的完整流程是什么？")` 返回非空；② `docs/upgrade/A1-kb-report.md` 的 hit_rate@3/MRR 与实际脚本输出一致；③ 记忆演示：第二次相似任务 planner 输入包含第一条记忆、`agent_memory` 计数增长；④ `data/live_results.json` 的本地 2 主题记录与成本（≤2 元 DeepSeek 对比需先前确认） |
| G2 | ① interrupt→编辑子问题→resume 现场演示（含进程重启恢复）；② `pytest -q` 与 CI 全绿；③ `GET /api/tasks/{id}/metrics` 数字与一次真实任务一致；④ SSE 事件顺序（status/log/node/done） |
| G3 | ① README 与真实能力逐条对照；② 账本 claim-af-002/003 措辞由用户最终点头；③ 未落地项（YAML/Docker/微调）保持"规划中"；④ 语料公开范围确认 |

---

## 三、技术风险与缓解

| # | 风险 | 影响 | 缓解 | 触发硬停止 |
|---|---|---|---|---|
| T1 | 8GB 显存紧张（qwen2.5:7b≈4.7GB + bge-m3≈2.3GB ≈7GB） | OOM / 推理变慢 | embedding 服务可改 CPU；严格串行；`OLLAMA_MAX_LOADED_MODELS=1`；跑 KB/评测时避免其他显存占用 | 连续 OOM 无法恢复 |
| T2 | 共享 venv（worktree 复用主仓库 venv） | 安装 checkpoint-sqlite/ruff 影响主环境 | 安装前后 `pip freeze` 备份；每次回归 31 项测试；必要时改用独立 venv | 回归 30 分钟无法修复 |
| T3 | B4 checkpoint 序列化（SearchOutcome unregistered type） | interrupt/resume 失败 | 先 30–60 分钟 spike；显式 serde 白名单或改纯 dict | spike >90 分钟 |
| T4 | worker 竞态（SQLite 无 SKIP LOCKED） | 任务重复执行 | 单进程 worker + 原子 UPDATE claim；`tests/test_claim_race.py` 必须真实通过 | 竞态测试不稳定 |
| T5 | worktree 无 .env | A2/A5 缺 key | 需要时用环境变量显式注入；**禁止复制主仓库 .env 进 worktree** | 误把 key 写入文件 |
| T6 | 时间偏乐观（8–12 净工作日） | 日历 2–3 周 | A 阶段超 ~4 净工作日未到 G1、或 B4 spike 超 90 分钟 → 砍 B2/B4 范围，不压缩测试 | 触发即请示 |
| T7 | 密钥安全（DeepSeek/Tavily key 曾在对话明文出现） | 泄露风险 | 建议轮换；新 key 不进 worktree/提交；`.env` 在 .gitignore | 发现 key 进入 git |
| T8 | 语料公开范围 | 隐私/合规 | 6 篇已扫描无 key/PII；但《AI应用实习面试学习文档.md》为求职笔记，**推送前需用户最终确认** | 用户未确认前不推送 |

---

## 四、待用户授权事项（尚未发生，发生前停下询问）

1. **公开语料**：✅ 已确认不公开（2026-09-10 用户选 B）；文档已移出语料并重建索引。
2. **付费调用**：✅ DeepSeek 1 次对比已授权并执行（2026-09-10，DeepSeek 阶段估算 ¥1.9945 ≤ ¥2）；Tavily 仍按调用上限控制。
3. **远端推送**：任何 `git push` 由用户执行或授权。
4. **Docker**：Phase A/B 完成后由用户决定是否安装。
5. **最终措辞**：README/账本中 Memory、人机协同的表述需用户点头后才从"不采用"改为"已确认"。

---

## 五、硬停止条件（与 PLAN-v2.md 第 8 节一致）

1. 核心依赖冲突或单点修复 >30 分钟；
2. 成本预估/实际将超 10 元（付费对比 >2 元）；
3. Ollama 或 embedding 服务不可用且无法恢复；
4. interrupt/resume spike >90 分钟未通过；
5. 需要管理员权限或写入工作区外目录；
6. 语料出现隐私/PII/密钥或许可证疑问；
7. embedding 服务与 pytorch_env 不兼容；
8. 既有测试回归且 30 分钟内无法定位。

命中任一条 → 立即停止、记录到 `docs/upgrade/`、向用户请示，不擅自绕过。