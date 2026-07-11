"""Load and chunk the Gutenberg corpus.

Strips Project Gutenberg header/footer, splits each book into overlapping
chunks with metadata (doc id, title, author, chunk index, source URL).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"
MANIFEST = CORPUS_DIR / "manifest.json"

_START = re.compile(r"\*\*\* START OF THE PROJECT GUTENBERG EBOOK[^*]*\*\*\*", re.IGNORECASE)
_END = re.compile(r"\*\*\* END OF THE PROJECT GUTENBERG EBOOK[^*]*\*\*\*", re.IGNORECASE)


@dataclass(frozen=True)
class DocumentMeta:
    id: str
    title: str
    author: str
    filename: str
    source_url: str


_META_FIELDS = {"id", "title", "author", "filename", "source_url"}


def load_manifest() -> list[DocumentMeta]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        DocumentMeta(**{k: v for k, v in d.items() if k in _META_FIELDS})
        for d in data["documents"]
        if "id" in d
    ]


def read_body(meta: DocumentMeta) -> str:
    raw = (CORPUS_DIR / meta.filename).read_text(encoding="utf-8", errors="replace")
    start = _START.search(raw)
    end = _END.search(raw)
    body = raw[start.end():end.start()] if start and end else raw
    return body.strip()


def chunk_text(text: str, chunk_size: int = 2500, overlap: int = 250) -> list[str]:
    """Simple paragraph-aware chunker. Groups paragraphs up to chunk_size chars,
    with `overlap` chars of tail carried into the next chunk for continuity."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= chunk_size or not buf:
            buf = f"{buf}\n\n{p}".strip() if buf else p
        else:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = f"{tail}\n\n{p}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def load_chunks(chunk_size: int = 2500, overlap: int = 250) -> list[dict]:
    """Return [{text, metadata}] for every chunk in the corpus."""
    out: list[dict] = []
    for meta in load_manifest():
        body = read_body(meta)
        for i, chunk in enumerate(chunk_text(body, chunk_size, overlap)):
            out.append({
                "text": chunk,
                "metadata": {
                    "doc_id": meta.id,
                    "title": meta.title,
                    "author": meta.author,
                    "chunk_index": i,
                    "source_url": meta.source_url,
                },
            })
    return out