# A1 真实知识库（已完成）

日期：2026-09-10 ｜ 状态：✅ 通过 ｜ 外部 API 成本：0 元

## 1. 目标
把"空壳知识库"变成真实可检索的知识库：
- 6 篇已确认语料入库；
- 自定义 embedding 函数（复用本地 bge-m3，不向 AgentForge venv 安装 torch/FlagEmbedding）；
- 10 条固定查询量化检索质量（hit_rate@3 / MRR）；
- MCP `local_search` 真实非空。

## 2. 语料（用户决策 1A）
| 文件 | 字符数 | 分块数 | 许可/边界 |
|---|---:|---:|---|
| README.md | 3,469 | 10 | AgentForge 项目文档（MIT） |
| tutorial-AgentForge.md | 19,713 | 55 | 本项目生成的课程文档（用户自有） |
| 大模型幻觉与Prompt注入风险工程化应对.md | 22,458 | 65 | 用户自写学习笔记（确认可公开） |
| 微调与LoRA知识.md | 517 | 2 | 用户自写学习笔记（确认可公开） |
| 主流大模型与应用范式分析.md | 29,024 | 90 | 用户自写学习笔记（确认可公开） |
| AI应用实习面试学习文档.md | 21,775 | 57 | 用户自写学习笔记（确认可公开） |
| **合计** | **76,956** | **279** | 隐私扫描：无 key/邮箱/手机号/姓名/GitHub 账号 |

`docs/kb/manifest.json` 记录每篇 sha256 / size / license / added_at。

## 3. 索引构建证据
命令（AgentForge venv）：
```powershell
D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe scripts\build_kb.py --rebuild
```
输出摘要：
```json
{"documents": 6, "chunks": 279, "collection": "agentforge_kb", "collection_count": 279,
 "corpus_version": "fefc5b1c3ce84330", "rebuild": true}
```
耗时：20.4 秒（含首次 bge-m3 加载 + 编码）；embedding 服务：`http://127.0.0.1:11435`（bge-m3，dim=1024，cosine）。

## 4. 检索质量（10 条固定查询）
口径：相关性 = 返回结果的 source 命中期望文档且文本包含任一期望关键词；命中率按 top-3 计算。这是小语料库的简化标注，非人工双盲标注。

**结果：hit_rate@3 = 0.90（9/10）；MRR = 0.90**

| # | 查询 | 首个相关排名 | top-3 来源 |
|---|---|---:|---|
| 1 | LangGraph 多 Agent 研究协作系统是如何设计的？ | 1 | README / tutorial / 面试文档 |
| 2 | 审核闭环如何避免死循环？ | 1 | tutorial ×3 |
| 3 | ReAct 搜索 Agent 的工作流程是什么？ | **未命中** | 面试文档 ×2 / 范式分析 |
| 4 | RAG 的完整流程是什么？ | 1 | 面试文档 / 范式分析 / 面试文档 |
| 5 | 混合检索为什么要把向量和 BM25 结合？ | 1 | 面试文档 / 范式分析 / 面试文档 |
| 6 | Prompt 注入的风险如何工程化防御？ | 1 | 幻觉与注入文档 ×2 / 面试文档 |
| 7 | LoRA 和 QLoRA 有什么区别？ | 1 | 微调与LoRA / 范式分析 / 微调与LoRA |
| 8 | 大模型幻觉是怎么产生的？ | 1 | 幻觉与注入文档 ×3 |
| 9 | AI 应用岗位面试通常考察哪些能力？ | 1 | 面试文档 ×3 |
| 10 | 向量数据库在 RAG 中起什么作用？ | 1 | 面试文档 ×2 / 范式分析 |

**已知未命中**：第 3 题"ReAct 搜索 Agent"未进入 top-3（面试文档的 Agent 段落分数更高）。候选修复：为 tutorial 的 L4 增加关键词元数据 / 引入 BM25 混合检索（与 SmartKB2.0 的经验一致）→ 建议放入 C4，不在 A1 扩大范围。

## 5. MCP 真实调用验证
命令（venv-mcp，fastmcp 4.0.3）：
```powershell
D:\codex使用文件夹\venv-mcp\Scripts\python.exe scripts\verify_mcp.py
```
结果：
```
tools=["web_search", "local_search", "calculate"]
result_type=list
MCP_LOCAL_SEARCH_COUNT=3
```
说明：这是通过 stdio 启动 `app/mcp_server.py` 的真实 MCP 客户端调用；`local_search` 返回 3 条真实知识库结果。
边界：MCP 运行环境是 `venv-mcp`；AgentForge 主 venv 未安装 fastmcp（requirements.txt 已声明 `fastmcp>=2.0.0`）。A4 统一依赖时再决定是否并入主 venv。

## 6. 改动文件
| 文件 | 说明 |
|---|---|
| `app/kb/embedding.py` | `HttpBgeM3EmbeddingFunction`（HTTP 调本地 bge-m3，cosine）+ `DeterministicHashEmbeddingFunction`（CI 离线） |
| `app/kb/loader.py` | md/txt 加载、sha256、Document |
| `app/kb/indexer.py` | 分块 + 确定性 chunk id + Chroma upsert + query |
| `app/kb/eval_kb.py` | 10 条固定查询的 hit_rate@k / MRR |
| `scripts/embed_server.py` | 用 pytorch_env 启动的 bge-m3 HTTP 服务（复用 SmartKB2.0 权重） |
| `scripts/build_kb.py` | 构建/重建索引（含服务健康检查） |
| `scripts/verify_mcp.py` | MCP stdio 真实调用验证 |
| `app/config.py` | 新增 embedding / docs_dir / chunk 配置 |
| `app/tools/rag.py` | 使用配置集合 + 自定义 EF；空库返回 []，服务故障 fail-closed 抛错 |
| `tests/test_kb.py` | 3 项离线测试（fake EF） |
| `docs/kb/` | 6 篇语料 + manifest.json |
| `.gitignore` | 忽略 `data/embed_server*.log` |

## 7. 成本与遗留
- 成本：0 元（本地 embedding，无外部 API 调用）。
- 遗留：① ReAct 查询未命中（见第 4 节）；② embedding 服务需常驻（fail-closed 已实现，服务停则检索报错而非静默空）；③ 语料为 6 篇小规模，评测为自标注口径。
- 下一步：A2 Memory 接通（同一 embedding 服务 + `agent_memory` 集合）。