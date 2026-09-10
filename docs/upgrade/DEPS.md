# AgentForge v2.0 依赖基线（G0，2026-09-10）

运行解释器：`D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe`（worktree 复用主仓库 venv）

## 已安装（关键）
| 包 | 版本 |
|---|---|
| langgraph | 1.2.11 |
| langgraph-checkpoint | 4.2.0 |
| langchain | 1.3.15 |
| langchain-core | 1.5.5 |
| langchain-openai | 1.5.1 |
| langchain-community | 0.4.2 |
| chromadb | 1.5.9 |
| sqlalchemy | 2.0.52 |
| aiosqlite | 0.22.1 |
| fastapi | 0.141.1 |
| httpx | 0.28.1 |
| pytest | 9.1.1 |
| streamlit | 1.61.1 |
| tavily-python | 0.7.27 |
| duckduckgo-search | 8.1.1 |
| numpy | 2.5.2 |

## 未安装（按计划处理）
| 包 | 计划 |
|---|---|
| langgraph-checkpoint-sqlite | B1 前安装 `==3.1.1`（dry-run：仅新增 sqlite-vec==0.1.9，不升级现有依赖） |
| ruff | A4 安装（dev 依赖） |
| torch / FlagEmbedding / sentence-transformers | **不安装进本 venv**；embedding 走独立服务 |
| alembic | 不安装；使用轻量 migration |

## 独立 embedding 环境（只读复用）
`D:\ANACONDA\envs\pytorch_env\python.exe`：torch 2.6.0+cu124、FlagEmbedding 1.4.0、sentence-transformers 5.7.0、transformers 4.52.4、numpy 1.26.4。
模型：`D:\codex使用文件夹\SmartKB2.0\models\bge-m3`（本地权重，不下载）。