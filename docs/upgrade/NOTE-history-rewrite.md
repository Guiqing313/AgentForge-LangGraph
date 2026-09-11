# 发布仓库历史重写说明

日期：2026-09-11

## 背景
公开发布前发现：`docs/kb/AI应用实习面试学习文档.md` 虽然已从最新版本移除，但其完整内容仍存在于 git 历史（提交 `637c602` 加入、`8e3e1d0` 删除）。用户决定该文档不公开，因此发布前使用 `git-filter-repo` 从**全部历史**中移除了该路径。

## 影响
- 公开仓库的所有 commit hash 与开发期本地历史不同；
- `docs/upgrade/` 各阶段文档中出现的短 hash（如 `9ce1c3a`、`d20dca2`、`a83cde9` 等）指重写前的本地历史，**仅作为过程记录**，不对应公开仓库的提交；
- 代码、测试与证据文档的内容未受重写影响（当前回归：pytest 全部通过、ruff 全绿）；
- 被移除的仅是那份不公开的面试笔记；其余 5 篇语料与 manifest 保留。

## 复现重写（如需再次发布）
```powershell
git clone --branch codex/agentforge-upgrade <本地仓库> <干净目录>
python -m git_filter_repo --path "docs/kb/AI应用实习面试学习文档.md" --invert-paths --force
git log --all --oneline -- "docs/kb/AI*"   # 应为空
```
