"""Anonymous hybrid RAG tools over the Gutenberg demo corpus.

The pipeline requires Pinecone + Cohere + Google API keys (set in .env). If
the RAG index isn't available at startup the tools stay registered but return
a clear error explaining how to build it — so `AUTH_MODE=off` local demos of
the MarTech tools still work without RAG credentials.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from playground.config import Settings
from playground.rag.corpus import load_manifest, read_body
from playground.rag.pipeline import HybridRAG


def _build_rag(settings: Settings) -> HybridRAG | str:
    """Return an attached HybridRAG, or an error string if unavailable."""
    missing = [
        k for k, v in {
            "GOOGLE_API_KEY": settings.google_api_key,
            "COHERE_API_KEY": settings.cohere_api_key,
            "PINECONE_API_KEY": settings.pinecone_api_key,
        }.items() if not v
    ]
    if missing:
        return f"RAG unavailable: missing env vars {', '.join(missing)}."
    try:
        rag = HybridRAG(
            pinecone_index=settings.pinecone_index,
            pinecone_cloud=settings.pinecone_cloud,
            pinecone_region=settings.pinecone_region,
        )
        rag.attach()
        return rag
    except FileNotFoundError:
        return (
            "RAG unavailable: bm25_index.json not found. Build the index once "
            "with `uv run python -m playground.rag.build`."
        )
    except Exception as exc:  # pinecone / auth / network
        return f"RAG unavailable: {exc.__class__.__name__}: {exc}"


def register(mcp: FastMCP, settings: Settings) -> None:
    # Resolve lazily on first call — starting Pinecone/Cohere clients is slow
    # and we don't want to block server startup if the caller never uses RAG.
    _cache: dict[str, HybridRAG | str] = {}

    def _rag() -> HybridRAG:
        if "rag" not in _cache:
            _cache["rag"] = _build_rag(settings)
        val = _cache["rag"]
        if isinstance(val, str):
            raise ToolError(val)
        return val

    @mcp.tool
    def rag_query(query: str, k: int = 5) -> dict[str, Any]:
        """Hybrid RAG search over a small public-domain Project Gutenberg
        corpus (Moby Dick + Sherlock Holmes). Dense retrieval via Google
        embeddings on Pinecone, sparse via BM25, fused with RRF, reranked by
        Cohere. Returns the top-k passages with book title, author, and source
        URL.

        Open demo — no sign-in needed.
        """
        return _rag().query(query, k=k)

    @mcp.tool
    def list_documents() -> dict[str, Any]:
        """List the documents in the RAG corpus with their metadata and
        Project Gutenberg source URLs.

        Open demo — no sign-in needed.
        """
        return {
            "documents": [
                {
                    "id": m.id,
                    "title": m.title,
                    "author": m.author,
                    "source_url": m.source_url,
                }
                for m in load_manifest()
            ]
        }

    @mcp.tool
    def get_document(id: str, max_chars: int = 20000) -> dict[str, Any]:
        """Return the full text (up to `max_chars`) of one corpus document
        by id. Use `list_documents` to see the available ids.

        Open demo — no sign-in needed.
        """
        for m in load_manifest():
            if m.id == id:
                body = read_body(m)
                truncated = len(body) > max_chars
                return {
                    "id": m.id,
                    "title": m.title,
                    "author": m.author,
                    "source_url": m.source_url,
                    "text": body[:max_chars],
                    "truncated": truncated,
                    "total_chars": len(body),
                }
        raise ToolError(f"Unknown document id {id!r}. Call list_documents to see options.")
