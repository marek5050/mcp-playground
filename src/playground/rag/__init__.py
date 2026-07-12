"""Hybrid RAG (Pinecone dense + BM25 sparse + Cohere rerank) over a public
Project Gutenberg corpus."""

from playground.rag.pipeline import HybridRAG

__all__ = ["HybridRAG"]