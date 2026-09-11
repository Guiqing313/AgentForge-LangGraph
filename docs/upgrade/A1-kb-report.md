# A1 真实知识库（v2：移除一份不公开的个人材料后重建）

日期：2026-09-10 ｜ 状态：✅ 通过 ｜ 外部 API 成本：0 元

## 0. v2 变更说明
用户确认其中一份个人材料不允许公开，已从语料移除、更新 manifest，并重建索引与评测。原 v1 数据保留在 git 历史中，本文件以 v2 为准。

## 1. 语料（v2，5 篇）
| 文件 | 字符数 | 分块数 | 许可/边界 |
|---|---:|---:|---|
| README.md | 3,469 | 10 | AgentForge 项目文档（MIT） |
| tutorial-AgentForge.md | 19,713 | 55 | 本项目生成的课程文档（用户自有） |
| 大模型幻觉与Prompt注入风险工程化应对.md | 22,458 | 65 | 用户自写学习笔记（确认可公开） |
| 微调与LoRA知识.md | 517 | 2 | 用户自写学习笔记（确认可公开） |
| 主流大模型与应用范式分析.md | 29,024 | 90 | 用户自写学习笔记（确认可公开） |
| **合计** | **75,181** | **222** | 隐私扫描：无 key/邮箱/手机号/姓名/GitHub 账号 |

`docs/kb/manifest.json`（corpus_version `v2-2026-09-10`）记录每篇 sha256 / size / license / added_at。
`tests/test_kb.py::test_private_interview_doc_not_in_corpus` 作为回归保护：该文件不得再次进入语料。

## 2. 索引构建证据（v2）
```json
{"documents": 5, "chunks": 222, "collection": "agentforge_kb", "collection_count": 222,
 "corpus_version": "b67a99a33425f68e", "rebuild": true}
```
embedding 服务：`http://127.0.0.1:11435`（bge-m3，dim=1024，cosine，复用 SmartKB2.0 本地权重）。

> 2026-09-11 复测修复：loader 改为按原始文件内容计算 sha256（strip 仅用于分块），真实 5 篇语料可重新构建；重建后 corpus_version = `b67a99a33425f68e`。

## 3. 检索质量（v2，10 条固定查询）
口径：相关性 = 返回结果 source 命中期望文档且文本包含任一期望关键词；top-3 计算。

**结果：hit_rate@3 = 0.90（9/10）；MRR = 0.85**

| # | 查询 | 首个相关排名 | top-3 来源 |
|---|---|---:|---|
| 1 | LangGraph 多 Agent 研究协作系统是如何设计的？ | 1 | README / tutorial / 范式分析 |
| 2 | 审核闭环如何避免死循环？ | 1 | tutorial ×3 |
| 3 | ReAct 搜索 Agent 的工作流程是什么？ | **未命中** | 范式分析 ×3 |
| 4 | RAG 的完整流程是什么？ | 1 | 范式分析 ×3 |
| 5 | 混合检索为什么要把向量和 BM25 结合？ | 1 | 范式分析 / 幻觉与注入 / 范式分析 |
| 6 | Prompt 注入的风险如何工程化防御？ | 1 | 幻觉与注入 ×3 |
| 7 | LoRA 和 QLoRA 有什么区别？ | 1 | 微调与LoRA / 范式分析 / 微调与LoRA |
| 8 | 大模型幻觉是怎么产生的？ | 1 | 幻觉与注入 ×3 |
| 9 | 多 Agent 系统如何做任务规划与工具调用？ | 1 | 范式分析 ×3 |
| 10 | 向量数据库在 RAG 中起什么作用？ | 2 | 范式分析 ×2 / README |

**已知未命中**：第 3 题"ReAct 搜索 Agent"未进 top-3（范式分析文档的 Agent 段落分数更高）。候选修复：为 tutorial 的 L4 增加关键词元数据 / 引入 BM25 混合检索（与 SmartKB2.0 的经验一致）→ 建议放入 C4。

## 4. MCP 真实调用验证
命令（venv-mcp，fastmcp 4.0.3）：`python scripts/verify_mcp.py`
```
tools=["web_search", "local_search", "calculate"]
MCP_LOCAL_SEARCH_COUNT=3
```
真实 stdio 调用；`local_search` 返回 3 条真实知识库结果（本轮仍以 222 chunk 索引为准）。
边界：MCP 运行环境是 venv-mcp；AgentForge 主 venv 未装 fastmcp（requirements 已 pin 4.0.3，CI 会安装）。

## 5. 成本
0 元（本地 embedding，无外部 API 调用）。

## 6. 下一步
A5 的 DeepSeek 对比（用户已授权按占位价执行，≤2 元）使用本 v2 索引与同一批搜索结果。

---

## 3bis. C2 工程化评测（32 题，取代上方 10 题冒烟）

> 上方第 3 节的 10 题结果为早期冒烟集；C2 已升级为 32 题分层评测集，作为对外口径。脚本：`python -m app.kb.eval_kb --k 3 --out data/eval_report.json --markdown docs/upgrade/eval_report.md`；报告：`docs/upgrade/eval_report.md`。

评测集：基础 12 + 长尾/改写 10 + 多跳/跨文档 5 + 库外拒答 5 = **32 题**（本地 222 chunks 索引，bge-m3 + Chroma + reranker）。

| 指标 | @1 | @3 | @5 |
|---|---|---|---|
| hit_rate | 0.5185 | **0.6296** | 0.7037 |
| MRR | 0.5185 | **0.5617** | 0.5784 |
| recall | 0.2963 | 0.3951 | 0.4568 |
| nDCG | 0.5185 | **0.6622** | 0.8380 |

- 库外拒答代理准确率：**1.0**（5/5，top-1 cosine distance ≥ 0.35 视为无强匹配；真正拒答由生成层负责）；
- 数字比 10 题冒烟（0.90/0.85）低，原因是评测集更大、更偏长尾/多跳，属更诚实的工程基准；
- 复现：启动本地 bge-m3 embedding 服务后运行上述命令（报告同时写入 JSON 与 Markdown）。
