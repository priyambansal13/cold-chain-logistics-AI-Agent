"""Vector RAG over the corporate SOP rulebook (OpenAI embeddings + cosine similarity).

Chunks are split on SOP sections, embedded once and cached to disk; the cache is
invalidated automatically whenever an SOP file or the embedding model changes.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

import numpy as np
from openai import OpenAI

from .config import EMBEDDING_MODEL, SOP_DIR, VECTOR_INDEX_PATH


def load_chunks(sop_dir: Path = SOP_DIR) -> list[dict]:
    chunks = []
    for path in sorted(sop_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, re.M)
        title = title_match.group(1).strip() if title_match else path.stem
        doc_id = title.split(":")[0].strip()
        sections = re.split(r"^## ", text, flags=re.M)
        preamble = sections[0]
        for sec in sections[1:]:
            heading, _, body = sec.partition("\n")
            body = body.strip()
            if not body:
                continue
            chunks.append({
                "doc_id": doc_id,
                "title": title,
                "section": heading.strip(),
                "source": path.name,
                "text": f"{title}\nSection: {heading.strip()}\n\n{body}",
            })
        if len(sections) == 1 and preamble.strip():
            chunks.append({"doc_id": doc_id, "title": title, "section": "Overview",
                           "source": path.name, "text": preamble.strip()})
    return chunks


class SOPVectorStore:
    def __init__(self, embedding_model: str = EMBEDDING_MODEL):
        self.embedding_model = embedding_model
        self.chunks: list[dict] = []
        self.matrix: np.ndarray | None = None
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI()
        return self._client

    def _embed(self, texts: list[str]) -> np.ndarray:
        resp = self.client.embeddings.create(model=self.embedding_model, input=texts)
        vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    def build(self, force: bool = False) -> "SOPVectorStore":
        chunks = load_chunks()
        fingerprint = hashlib.sha256(
            (self.embedding_model + "".join(c["text"] for c in chunks)).encode()
        ).hexdigest()
        if not force and VECTOR_INDEX_PATH.exists():
            cached = json.loads(VECTOR_INDEX_PATH.read_text())
            if cached.get("fingerprint") == fingerprint:
                self.chunks = cached["chunks"]
                self.matrix = np.array(cached["vectors"], dtype=np.float32)
                return self
        self.chunks = chunks
        self.matrix = self._embed([c["text"] for c in chunks])
        VECTOR_INDEX_PATH.write_text(json.dumps({
            "fingerprint": fingerprint,
            "model": self.embedding_model,
            "chunks": chunks,
            "vectors": self.matrix.round(6).tolist(),
        }))
        return self

    def search(self, query: str, k: int = 4) -> list[dict]:
        if self.matrix is None:
            self.build()
        q = self._embed([query])[0]
        scores = self.matrix @ q
        top = np.argsort(-scores)[:k]
        return [{**self.chunks[i], "score": round(float(scores[i]), 4)} for i in top]


_store: SOPVectorStore | None = None
_lock = threading.Lock()


def get_store(force_rebuild: bool = False) -> SOPVectorStore:
    global _store
    with _lock:
        if _store is None or force_rebuild:
            _store = SOPVectorStore().build(force=force_rebuild)
        return _store


def index_ready() -> bool:
    return _store is not None and _store.matrix is not None
