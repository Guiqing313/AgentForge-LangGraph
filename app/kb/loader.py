"""知识库文档加载：读取 md/txt，计算 sha256，产出 Document 列表。

2026-09-11 复测加固：
- 若语料目录存在 manifest.json，则 manifest 作为**白名单**：只有登记在册的文件才会进入语料；
- 登记文件的 sha256 必须与 manifest 一致，否则拒绝加载（防止悄悄替换/新增隐私文档）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    doc_id: str
    source: str
    text: str
    sha256: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_manifest(directory: Path) -> dict[str, dict] | None:
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries: dict[str, dict] = {}
    for item in data.get("documents", []) or []:
        name = item.get("file")
        if isinstance(name, str) and name:
            entries[name] = item
    return entries


def load_documents(
    docs_dir: str | Path | None = None,
    extensions: tuple[str, ...] = (".md", ".txt"),
    verify_sha256: bool = True,
) -> list[Document]:
    from app.config import settings

    directory = Path(docs_dir or settings.docs_dir)
    if not directory.exists():
        raise FileNotFoundError(f"知识库目录不存在：{directory}")

    manifest = _load_manifest(directory)
    documents: list[Document] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if path.name == "manifest.json":
            continue
        entry = manifest.get(path.name) if manifest is not None else None
        if manifest is not None and entry is None:
            # manifest 是白名单：未登记文件不进入语料
            continue
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        text = raw_text.strip()
        if not text:
            continue
        # manifest 的 sha256 基于原始文件内容；strip 仅用于分块，避免哈希口径不一致
        actual_sha = sha256_text(raw_text)
        if entry and verify_sha256:
            expected = entry.get("sha256")
            if expected and expected != actual_sha:
                raise ValueError(
                    f"语料 {path.name} 的 sha256 与 manifest 不一致：请更新 manifest 或还原文件"
                )
        documents.append(
            Document(
                doc_id=actual_sha[:16],
                source=path.name,
                text=text,
                sha256=actual_sha,
            )
        )
    return documents
