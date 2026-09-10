# G0 基线报告（AgentForge v2.0）

日期：2026-09-10
worktree：`D:\codex使用文件夹\AgentForge-v2`
分支：`codex/agentforge-upgrade`
基线提交：`498e446 加入mcp服务`

## 1. 已通过项

| 检查 | 命令 | 结果 |
|---|---|---|
| 测试基线 | `pytest -q` | **22 passed in 0.89s** |
| 测试收集 | `pytest --collect-only -q` | 22 tests collected |
| embedding 选型 2B 预检 | `pytorch_env` 加载本地 bge-m3 并 encode | **dim (1,1024)，load+encode 79.1s** ✅ |
| 语料隐私扫描 | 6 篇候选文档正则扫描 | 无 sk-/tvly-/ghp_、无邮箱/手机号/姓名/GitHub 账号 ✅ |
| 依赖版本记录 | `pip list` 关键包 | 见 `docs/upgrade/DEPS.md` |
| worktree | `git worktree add` | 已建立，HEAD 498e446 ✅ |

## 2. 现状（不是失败，是待改造项）

| 项 | 证据 | 影响 |
|---|---|---|
| 知识库为空壳 | `data/chroma/chroma.sqlite3`：collections=0 / embeddings=0 / segments=0；`app/tools/rag.py` 只有 `get_collection` | A1 必须实现 loader/indexer |
| Chroma 默认 EF 不可用 | 用默认 EF 建集合时尝试下载 ONNX MiniLM 到 `C:\Users\度量\.cache\chroma` → PermissionError | A1 必须自定义 EF；CI 必须注入 fake EF |
| Memory 未接入 | `app/services/memory_service.py` 无调用方 | A2 接通 |
| mock e2e 当前失败 | `LLM_MODE=mock python scripts/run_e2e.py "冒烟主题"` → `RuntimeError: 缺少 DEEPSEEK_API_KEY`（`settings.validate_for_live()` 无条件调用） | A3 修复：mock 模式跳过 live 校验 |
| reviewer 分数不一致 | prompt 写 8 分合格，配置默认 7 分 | A3 统一 |
| 图文档与实现不一致 | docstring/README 画图级搜索循环，`build()` 无该边 | A3 按实现修正文档 |
| Ollama 已运行 | `http://127.0.0.1:11434/api/version` → `{"version":"0.32.9"}`；`/api/tags` → `nomic-embed-text:latest`(274MB)、`qwen2.5:7b`(4.68GB) | ✅ 已通过（2026-09-10 用户启动） |
| OLLAMA_MODELS 未设置 | 用户/系统环境变量为空；模型 manifest 实际在 `D:\OllamaModels` | G0/A0：启动前显式设置 |
| 模型存在 | `D:\OllamaModels\manifests\...\qwen2.5\7b`、`...\nomic-embed-text\latest` | 启动后 `ollama list` 复核 |

## 3. G0 结论

- 可执行部分：**通过**（worktree、依赖基线、22 测试、bge-m3 预检、语料扫描）。
- Ollama 已由用户启动并通过 HTTP API 验证（v0.32.9；两个模型可见）。沙箱内 ollama.exe 仍被拒绝执行，但项目代码走 HTTP API，不受影响。
- G0 结论：**通过**（2026-09-10）。可进入 Phase A0/A1。

## 4. 复现命令

```powershell
# 测试基线
D:\codex使用文件夹\AgentForge\venv\Scripts\python.exe -m pytest -q

# Ollama（正常终端）
$env:OLLAMA_MODELS="D:\OllamaModels"
ollama serve
ollama list

# embedding 预检（pytorch_env）
D:\ANACONDA\envs\pytorch_env\python.exe -c "from FlagEmbedding import BGEM3FlagModel; m=BGEM3FlagModel(r'D:/codex使用文件夹/SmartKB2.0/models/bge-m3', use_fp16=True); print(m.encode(['RAG'], return_dense=True)['dense_vecs'].shape)"
```