"""Corpus loading + chunking tests — no external deps, fully hermetic."""

from __future__ import annotations

from playground.rag.corpus import chunk_text, load_chunks, load_manifest, read_body


EXPECTED_IDS = {
    "moby-dick",
    "sherlock-holmes",
    "study-in-scarlet",
    "hound-of-the-baskervilles",
}


def test_manifest_lists_expected_books():
    ids = {m.id for m in load_manifest()}
    assert ids == EXPECTED_IDS


def test_boilerplate_is_stripped():
    (moby,) = [m for m in load_manifest() if m.id == "moby-dick"]
    body = read_body(moby)
    # Header + license notice removed.
    assert "PROJECT GUTENBERG EBOOK" not in body.split("\n")[0]
    # But the actual text is present.
    assert "Call me Ishmael" in body
    # And the end marker is stripped too.
    assert "END OF THE PROJECT GUTENBERG" not in body


def test_chunker_paragraph_aware_with_overlap():
    text = "\n\n".join([f"Paragraph {i} " + ("word " * 40).strip() for i in range(20)])
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 + 300 for c in chunks)  # allow slack for overlap+paragraph
    # Every non-first chunk carries a tail from the previous chunk.
    for prev, curr in zip(chunks, chunks[1:]):
        assert prev[-30:] in curr or any(w in curr for w in prev.split()[-3:])


def test_load_chunks_attaches_metadata():
    chunks = load_chunks()
    assert chunks, "expected at least one chunk from the demo corpus"
    for c in chunks:
        assert set(c["metadata"]) >= {"doc_id", "title", "author", "chunk_index", "source_url"}
    doc_ids = {c["metadata"]["doc_id"] for c in chunks}
    assert doc_ids == EXPECTED_IDS
    # chunk_index is a monotonically increasing counter per document
    for doc_id in doc_ids:
        indices = [c["metadata"]["chunk_index"] for c in chunks if c["metadata"]["doc_id"] == doc_id]
        assert indices == list(range(len(indices)))
