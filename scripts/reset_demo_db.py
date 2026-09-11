r"""重置演示数据库（只允许操作项目 data/ 目录下的文件）。

用法：
    python scripts/reset_demo_db.py --db data/demo.db --checkpoint data/demo_checkpoints.sqlite
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = (ROOT / "data").resolve()


def _safe(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    if DATA_DIR not in resolved.parents and resolved != DATA_DIR:
        raise SystemExit(f"拒绝操作 data/ 之外的文件：{resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="重置 AgentForge 演示数据库")
    parser.add_argument("--db", default=str(ROOT / "data" / "demo.db"))
    parser.add_argument("--checkpoint", default=str(ROOT / "data" / "demo_checkpoints.sqlite"))
    args = parser.parse_args()

    for target in (_safe(args.db), _safe(args.checkpoint)):
        if target.exists():
            target.unlink()
            print(f"removed {target}")
        else:
            print(f"absent  {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
