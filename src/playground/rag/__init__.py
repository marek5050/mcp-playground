"""Hybrid RAG (Pinecone dense + BM25 sparse + Cohere rerank) over a public
Project Gutenberg corpus. Same stack as citrini_rag, generalized."""

from playground.rag.pipeline import HybridRAG

__all__ = ["HybridRAG"]