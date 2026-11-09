from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import HashingVectorizer

from app.core.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAG_DIR = PROJECT_ROOT / "rag_agent_knowledge_base"
LEGACY_RAG_DIR = PROJECT_ROOT / "rag_ready_教材"


def _configured_rag_dir() -> Path:
    configured = os.environ.get("RAG_BASE_DIR") or get_settings().rag_base_dir
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if (path / "chunks.jsonl").exists():
        return path
    if (LEGACY_RAG_DIR / "chunks.jsonl").exists():
        return LEGACY_RAG_DIR
    return path


def _first_existing(directory: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        candidate = directory / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"RAG index file not found in {directory}: {names}")


class _QueryEncoder:
    def __init__(self, model: Any) -> None:
        if isinstance(model, dict) and "hashing_params" in model:
            params = dict(model["hashing_params"])
            params["ngram_range"] = tuple(params.get("ngram_range", (1, 1)))
            self._hashing = HashingVectorizer(**params)
            self._tfidf = model["tfidf_transformer"]
            self._vectorizer = None
        else:
            self._hashing = None
            self._tfidf = None
            self._vectorizer = model

    def transform(self, queries: list[str]) -> Any:
        if self._hashing is not None and self._tfidf is not None:
            return self._tfidf.transform(self._hashing.transform(queries))
        return self._vectorizer.transform(queries)


@lru_cache(maxsize=4)
def _load_index(directory: str) -> tuple[list[dict[str, Any]], Any, _QueryEncoder]:
    rag_dir = Path(directory)
    chunks_path = rag_dir / "chunks.jsonl"
    vector_path = _first_existing(
        rag_dir,
        ("embeddings_sparse.npz", "vectors_tfidf_sparse.npz", "embeddings.npy"),
    )
    model_path = _first_existing(
        rag_dir,
        ("retrieval_model.joblib", "tfidf_vectorizer.joblib"),
    )

    chunks: list[dict[str, Any]] = []
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                chunks.append(json.loads(line))

    if vector_path.suffix == ".npz":
        vectors = sparse.load_npz(vector_path)
    else:
        vectors = np.load(vector_path)
    vectorizer = _QueryEncoder(joblib.load(model_path))
    return chunks, vectors, vectorizer


def _chunk_search_text(chunk: dict[str, Any]) -> str:
    section_path = chunk.get("section_path") or []
    if isinstance(section_path, str):
        section_path = [section_path]
    return " ".join(
        str(value)
        for value in [
            chunk.get("heading"),
            chunk.get("section"),
            *section_path,
            chunk.get("text"),
        ]
        if value
    )


def _is_allowed_chunk(
    chunk: dict[str, Any],
    allowed_sections: list[str] | tuple[str, ...] | None,
) -> bool:
    search_text = _chunk_search_text(chunk)
    if "langgraph" in search_text.lower():
        return False
    if not allowed_sections:
        return True
    section_path = chunk.get("section_path") or []
    if isinstance(section_path, str):
        section_path = [section_path]
    section_values = [
        str(chunk.get("heading") or ""),
        str(chunk.get("section") or ""),
        *(str(value) for value in section_path),
    ]
    return any(
        _section_matches_marker(value, marker)
        for marker in allowed_sections
        for value in section_values
    )


def _section_matches_marker(value: str, marker: str) -> bool:
    normalized_value = value.strip()
    normalized_marker = str(marker).strip()
    if not normalized_value or not normalized_marker:
        return False

    if re.fullmatch(r"\d+(?:\.\d+)*", normalized_marker):
        section_match = re.match(r"^(\d+(?:\.\d+)*)", normalized_value)
        if not section_match:
            return False
        section_id = section_match.group(1)
        return section_id == normalized_marker or section_id.startswith(f"{normalized_marker}.")

    return normalized_marker.casefold() in normalized_value.casefold()


def retrieve_rag_context(
    query: str,
    top_k: int = 3,
    *,
    allowed_sections: list[str] | tuple[str, ...] | None = None,
    topic_slug: str | None = None,
    rag_dir: str | None = None,
) -> dict[str, Any]:
    selected_rag_dir = (PROJECT_ROOT / rag_dir).resolve() if rag_dir else _configured_rag_dir()
    try:
        chunks, vectors, vectorizer = _load_index(str(selected_rag_dir))
    except (FileNotFoundError, OSError, ValueError):
        return {
            "source": selected_rag_dir.name,
            "topic_slug": topic_slug,
            "allowed_sections": list(allowed_sections or []),
            "query": query,
            "chunks": [],
        }

    if not query.strip() or not chunks:
        return {
            "source": selected_rag_dir.name,
            "topic_slug": topic_slug,
            "allowed_sections": list(allowed_sections or []),
            "query": query,
            "chunks": [],
        }

    query_vector = vectorizer.transform([query])
    scores = vectors @ query_vector.T
    scores = np.asarray(scores.toarray() if sparse.issparse(scores) else scores).reshape(-1)

    eligible: list[tuple[float, dict[str, Any]]] = []
    for index, chunk in enumerate(chunks):
        if not _is_allowed_chunk(chunk, allowed_sections):
            continue
        row = int(chunk.get("embedding_row", index))
        if row < 0 or row >= len(scores):
            continue
        eligible.append((float(scores[row]), chunk))

    eligible.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for score, chunk in eligible[: max(top_k, 0)]:
        selected.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "source_file": chunk.get("source_file"),
                "heading": chunk.get("heading"),
                "section_path": chunk.get("section_path") or chunk.get("section"),
                "text": chunk.get("text", ""),
                "score": score,
            }
        )

    return {
        "source": selected_rag_dir.name,
        "topic_slug": topic_slug,
        "allowed_sections": list(allowed_sections or []),
        "query": query,
        "chunks": selected,
    }
