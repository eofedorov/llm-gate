"""Чанкинг текста с перекрытием; к каждому чанку привязываются doc_id, title, path, section, created_at, chunk_index."""
from app.rag.store.models import ChunkMeta, make_chunk_id
from app.settings import Settings

_settings = Settings()


def chunk_text(
    text: str,
    *,
    doc_id: str,
    title: str,
    path: str = "",
    document_type: str = "",
    created_at: str = "",
    section: str = "",
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[ChunkMeta]:
    """
    Разбить текст на чанки с перекрытием. У каждого чанка: chunk_id, doc_id, title, path, section, created_at, chunk_index, text.
    """
    if not text or not doc_id:
        return []
    cs = chunk_size if chunk_size is not None else _settings.rag_chunk_size
    ov = overlap if overlap is not None else _settings.rag_chunk_overlap
    if ov >= cs:
        ov = max(0, cs - 1)
    chunks: list[ChunkMeta] = []
    start = 0
    index = 0
    while start < len(text):
        end = start + cs
        piece = text[start:end]
        if not piece.strip():
            start = end - ov
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
        start = end - ov
    return chunks


def chunk_document(
    doc: dict,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[ChunkMeta]:
    """
    Разбить один документ (dict из loader: doc_id, title, path, document_type, created_at, content) на чанки.
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
