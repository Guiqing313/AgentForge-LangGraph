"""知识库文档加载：读取 md/txt，计算 sha256，产出 Document 列表。"""

from __future__ import annotations

import hashlib
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


def load_documents(docs_dir: str | Path | None = None, extensions: tuple[str, ...] = (".md", ".txt")) -> list[Document]:
    from app.config import settings

    directory = Path(docs_dir or settings.docs_dir)
    if not directory.exists():
        raise FileNotFoundError(f"知识库目录不存在：{directory}")

    documents: list[Document] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        documents.append(
            Document(
                doc_id=sha256_text(str(path.relative_to(directory)).replace("\\", "/"))[:16],
                source=path.name,
                text=text,
                sha256=sha256_text(text),
            )
        )
    return documents