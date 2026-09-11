# Gate G1 签署记录（2026-09-11）

- 分支：`codex/agentforge-upgrade`；签署时 HEAD：`ae7d523`。
- 独立验证：子代理「复测」第六轮 delta 复测 → **Gate G1 可以签署**。
- 本地证据：`pytest 81 passed`；`ruff All checks passed!`；loader 5 篇；Chroma 222 chunks（corpus_version `b67a99a33425f68e`）；eval hit_rate 0.9 / MRR 0.85；LocalSearch 3 条非空；并发/预算/价格/失败链测试通过。
- 用户签署：2026-09-11 用户确认「G1 通过」。
- 保留为 BLOCKED/人工核验（不阻塞 G1）：GitHub Actions 远端绿结果（需推送）；官方价格与真实账单核验；Ollama 真实调用冒烟（当前停止）；`pip install -r requirements-lock.txt` 完整安装验证；生产级并发压力。

## 进入 Phase B 的前置
- B1 推荐先做 interrupt/resume spike（30–60 分钟，纯图 + checkpointer，mock LLM）。
- 依赖：`langgraph-checkpoint-sqlite==3.1.1`（A4 已 pin；安装前备份 pip freeze，安装后跑全量回归）。
- 服务状态：embedding 服务由用户启动（:11435）；Ollama 保持停止（spike 不需要）。

> 后续（C2）：检索评测已从 10 题冒烟升级为 32 题分层工程评测，最新数字见 `docs/upgrade/A1-kb-report.md` 第 3bis 节与 `eval_report.md`。
