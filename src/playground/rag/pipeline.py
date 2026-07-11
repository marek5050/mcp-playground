"""Hybrid RAG pipeline: Pinecone (dense) + BM25 (sparse) + RRF + Cohere rerank.

Ported from citrini_rag/hybrid_rag.py, generalized to a plain-text corpus
described by ``playground.data.corpus.manifest``. The pipeline has two modes:

- ``build_indexes()`` — offline, one-shot. Embeds every chunk to Pinecone and
  writes ``bm25_index.json`` next to the corpus. Run via
  ``python -m playground.rag.build``.
- ``attach()`` — runtime. Connects to the existing Pinecone index and loads
  the persisted BM25 corpus. Used by the MCP server on startup.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import numpy as np
import rank_bm25
from langchain_cohere import CohereRerank
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

from playground.rag.corpus import CORPUS_DIR, load_chunks

BM25_PATH = CORPUS_DIR / "bm25_index.json"

EMBEDDING_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
COHERE_RERANK_MODEL = "rerank-v3.5"
DEFAULT_TOP_K = 5
RRF_K = 60
UPSERT_BATCH = 20
# Delay between upsert batches to stay under Gemini embedding RPM quotas.
UPSERT_SLEEP_S = 1.5
UPSERT_MAX_RETRIES = 6


class HybridRAG:
    def __init__(
        self,
        pinecone_index: str,
        pinecone_cloud: str = "aws",
        pinecone_region: str = "us-east-1",
        top_k: int = DEFAULT_TOP_K,
    ):
        self.pinecone_index = pinecone_index
        self.pinecone_cloud = pinecone_cloud
        self.pinecone_region = pinecone_region
        self.top_k = top_k

        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=f"models/{EMBEDDING_MODEL}",
            api_key=os.environ["GOOGLE_API_KEY"],
            output_dimensionality=EMBED_DIM,
        )
        self.reranker = CohereRerank(
            cohere_api_key=os.environ["COHERE_API_KEY"],
            model=COHERE_RERANK_MODEL,
            top_n=top_k,
        )
        self.vectorstore: PineconeVectorStore | None = None
        self.bm25: rank_bm25.BM25Okapi | None = None
        self.corpus: list[str] = []
        self.metadata: list[dict[str, Any]] = []

    # ---------- indexing ----------

    def _ensure_index(self) -> None:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        existing = {i.name for i in pc.list_indexes()}
        if self.pinecone_index not in existing:
            pc.create_index(
                name=self.pinecone_index,
                dimension=EMBED_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud=self.pinecone_cloud, region=self.pinecone_region),
            )

    def build_indexes(self, chunks: list[dict] | None = None, clean: bool = True) -> None:
        """Embed the corpus into Pinecone and persist the BM25 index. When
        ``clean=True`` (default) drops all existing vectors first so removed
        or re-chunked documents don't linger as duplicates."""
        chunks = chunks if chunks is not None else load_chunks()
        docs = [Document(page_content=c["text"], metadata=c["metadata"]) for c in chunks]

        self._ensure_index()
        if clean:
            pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
            index = pc.Index(self.pinecone_index)
            try:
                index.delete(delete_all=True)
            except Exception as exc:
                # Empty index raises; ignore.
                if "Namespace not found" not in str(exc) and "404" not in str(exc):
                    raise
        self.vectorstore = PineconeVectorStore(
            index_name=self.pinecone_index,
            embedding=self.embeddings,
        )
        total_batches = (len(docs) + UPSERT_BATCH - 1) // UPSERT_BATCH
        for bnum, i in enumerate(range(0, len(docs), UPSERT_BATCH), start=1):
            batch = docs[i : i + UPSERT_BATCH]
            for attempt in range(UPSERT_MAX_RETRIES):
                try:
                    self.vectorstore.add_documents(batch)
                    break
                except Exception as exc:
                    if "RESOURCE_EXHAUSTED" not in str(exc) and "429" not in str(exc):
                        raise
                    backoff = min(60, 2 ** attempt * UPSERT_SLEEP_S)
                    print(f"  batch {bnum}/{total_batches}: rate-limited, sleeping {backoff:.1f}s")
                    time.sleep(backoff)
            else:
                raise RuntimeError(f"batch {bnum} failed after {UPSERT_MAX_RETRIES} retries")
            print(f"  batch {bnum}/{total_batches} upserted ({len(batch)} chunks)")
            time.sleep(UPSERT_SLEEP_S)

        self.corpus = [d.page_content for d in docs]
        self.metadata = [d.metadata for d in docs]
        self.bm25 = rank_bm25.BM25Okapi([c.split() for c in self.corpus])

        BM25_PATH.write_text(
            json.dumps({"corpus": self.corpus, "metadata": self.metadata}),
            encoding="utf-8",
        )

    def attach(self) -> None:
        """Connect to the existing Pinecone index and load persisted BM25."""
        self.vectorstore = PineconeVectorStore(
            index_name=self.pinecone_index,
            embedding=self.embeddings,
        )
        data = json.loads(BM25_PATH.read_text(encoding="utf-8"))
        self.corpus = data["corpus"]
        self.metadata = data["metadata"]
        self.bm25 = rank_bm25.BM25Okapi([c.split() for c in self.corpus])

    # ---------- retrieval ----------

    @staticmethod
    def _rrf(dense: list[Document], sparse: list[Document], k: int = RRF_K) -> list[Document]:
        # Key by content — Documents are re-created on each retrieval path so
        # object identity isn't stable across the two lists.
        scores: dict[str, float] = {}
        keep: dict[str, Document] = {}
        for rank, doc in enumerate(dense):
            key = doc.page_content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            keep.setdefault(key, doc)
        for rank, doc in enumerate(sparse):
            key = doc.page_content
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            keep.setdefault(key, doc)
        return [keep[k_] for k_, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]

    def retrieve(self, query: str, k: int | None = None) -> list[Document]:
        if self.vectorstore is None or self.bm25 is None:
            raise RuntimeError("HybridRAG not attached; call attach() or build_indexes() first.")
        k = k or self.top_k

        dense = [d for d, _ in self.vectorstore.similarity_search_with_score(query, k=k * 2)]

        bm25_scores = self.bm25.get_scores(query.split())
        top_idx = np.argsort(bm25_scores)[::-1][: k * 2]
        sparse = [
            Document(page_content=self.corpus[i], metadata=self.metadata[i])
            for i in top_idx
        ]

        fused = self._rrf(dense, sparse)[: k * 3]
        reranked = self.reranker.compress_documents(fused, query)
        return list(reranked)[:k]

    def query(self, query: str, k: int | None = None) -> dict[str, Any]:
        docs = self.retrieve(query, k)
        return {
            "query": query,
            "results": [
                {
                    "title": d.metadata.get("title"),
                    "author": d.metadata.get("author"),
                    "doc_id": d.metadata.get("doc_id"),
                    "chunk_index": d.metadata.get("chunk_index"),
                    "source_url": d.metadata.get("source_url"),
                    "text": d.page_content,
                }
                for d in docs
            ],
        }