"""CLI to build the RAG indexes. Run once after `uv sync` and after any change
to the corpus.

    uv run python -m playground.rag.build
"""

from __future__ import annotations

import os
import sys

# Loads .env into os.environ as a side-effect of importing the settings module.
from playground import config  # noqa: F401
from playground.rag.corpus import load_chunks
from playground.rag.pipeline import HybridRAG


def main() -> int:
    required = ("GOOGLE_API_KEY", "COHERE_API_KEY", "PINECONE_API_KEY")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks from corpus.")

    rag = HybridRAG(
        pinecone_index=os.environ.get("PINECONE_INDEX", "playground-rag"),
        pinecone_cloud=os.environ.get("PINECONE_CLOUD", "aws"),
        pinecone_region=os.environ.get("PINECONE_REGION", "us-east-1"),
    )
    rag.build_indexes(chunks)
    print(f"Indexed to Pinecone ({rag.pinecone_index}) and wrote bm25_index.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())