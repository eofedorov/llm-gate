"""FAISS index load/save and search. Metadata stored as JSON alongside index."""
import json
from pathlib import Path
from typing import Any

from app.rag.store.models import ChunkMeta
from app.settings import Settings

_settings = Settings()

# Project root: src/app/rag/store/faiss_store.py -> 5 parents
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_INDEX_DIR = _PROJECT_ROOT / "data" / "faiss_index"
INDEX_FILE = "index.faiss"
METADATA_FILE = "metadata.json"


def _index_dir() -> Path:
    if _settings.rag_index_dir:
        return Path(_settings.rag_index_dir)
    return DEFAULT_INDEX_DIR


class FaissStore:
    """Load/save FAISS index and metadata; search returns (chunk_id, score, meta)."""

    def __init__(self, index_dir: Path | str | None = None):
        self._dir = Path(index_dir) if index_dir is not None else _index_dir()
        self._index: Any = None
        self._metadata: list[dict[str, Any]] = []
        self._dim: int | None = None

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, vectors: list[list[float]], metadata: list[dict[str, Any]]) -> None:
        """Save vectors to FAISS and metadata to JSON."""
        import faiss
        import numpy as np

        self._ensure_dir()
        if not vectors:
            return
        arr = np.array(vectors, dtype=np.float32)
        dim = arr.shape[1]
        index = faiss.IndexFlatIP(dim)  # inner product for normalized vectors
        faiss.normalize_L2(arr)
        index.add(arr)
        path = self._dir / INDEX_FILE
        faiss.write_index(index, str(path))
        meta_path = self._dir / METADATA_FILE
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=0), encoding="utf-8")
        self._index = index
        self._metadata = metadata
        self._dim = dim

    def load(self) -> bool:
        """Load index and metadata from disk. Returns True if loaded."""
        import faiss

        path = self._dir / INDEX_FILE
        meta_path = self._dir / METADATA_FILE
        if not path.exists() or not meta_path.exists():
            return False
        self._index = faiss.read_index(str(path))
        self._metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        self._dim = self._index.d
        return True

    def _get_index_and_metadata(self):
        if self._index is None and not self.load():
            return None, []
        return self._index, self._metadata

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """
        Search by query vector. Returns list of (chunk_id, score, meta_dict).
        filters: optional { "document_type": "...", "doc_id": "..." } for post-filter.
        FAISS IndexFlatIP returns inner product; we use it as similarity (assume normalized).
        """
        import faiss
        import numpy as np

        index, metadata = self._get_index_and_metadata()
        if index is None or not metadata:
            return []
        q = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(q)
        scores, indices = index.search(q, min(k * 3, index.ntotal))  # fetch extra for filtering
        results: list[tuple[str, float, dict[str, Any]]] = []
        for i, idx in enumerate(indices[0]):
            if idx < 0:
                continue
            meta = metadata[idx] if idx < len(metadata) else {}
            if filters:
                if "document_type" in filters and meta.get("document_type") != filters["document_type"]:
                    continue
                if "doc_id" in filters and meta.get("doc_id") != filters["doc_id"]:
                    continue
            chunk_id = meta.get("chunk_id") or ""
            score = float(scores[0][i])
            results.append((chunk_id, score, meta))
            if len(results) >= k:
                break
        return results

    def is_loaded(self) -> bool:
        return self._index is not None


def metadata_from_chunk(chunk: ChunkMeta) -> dict[str, Any]:
    """Serialize ChunkMeta for JSON storage (no Pydantic)."""
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "title": chunk.title,
        "path": chunk.path,
        "document_type": chunk.document_type,
        "created_at": chunk.created_at,
        "section": chunk.section,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
    }
