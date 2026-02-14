"""Chunk text with overlap; attach doc_id, title, path, section, created_at, chunk_index."""
from app.rag.store.models import ChunkMeta, make_chunk_id


def chunk_text(
    text: str,
    *,
    doc_id: str,
    title: str,
    path: str = "",
    document_type: str = "",
    created_at: str = "",
    section: str = "",
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[ChunkMeta]:
    """
    Split text into overlapping chunks. Each chunk gets chunk_id, doc_id, title, path, section, created_at, chunk_index, text.
    """
    if not text or not doc_id:
        return []
    if overlap >= chunk_size:
        overlap = max(0, chunk_size - 1)
    chunks: list[ChunkMeta] = []
    start = 0
    index = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end]
        if not piece.strip():
            start = end - overlap
            continue
        chunk_id = make_chunk_id(doc_id, index)
        meta = ChunkMeta(
            chunk_id=chunk_id,
            doc_id=doc_id,
            title=title,
            path=path,
            document_type=document_type,
            created_at=created_at,
            section=section,
            chunk_index=index,
            text=piece.strip(),
        )
        chunks.append(meta)
        index += 1
        start = end - overlap
    return chunks


def chunk_document(
    doc: dict,
    *,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[ChunkMeta]:
    """
    Chunk a single document dict (from loader: doc_id, title, path, document_type, created_at, content).
    """
    content = doc.get("content") or ""
    return chunk_text(
        content,
        doc_id=doc.get("doc_id") or "",
        title=doc.get("title") or "",
        path=doc.get("path") or "",
        document_type=doc.get("document_type") or "",
        created_at=doc.get("created_at") or "",
        section="",
        chunk_size=chunk_size,
        overlap=overlap,
    )
