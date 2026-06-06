from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import scipy.sparse as sp


RAG_DIR = Path(__file__).resolve().parents[3] / "rag_ready_教材"
CHUNKS_PATH = RAG_DIR / "chunks.jsonl"
VECTORS_PATH = RAG_DIR / "vectors_tfidf_sparse.npz"
VECTORIZER_PATH = RAG_DIR / "tfidf_vectorizer.joblib"


@lru_cache(maxsize=1)
def _load_index() -> tuple[list[dict[str, Any]], Any, Any]:
    with CHUNKS_PATH.open("r", encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    vectorizer = joblib.load(VECTORIZER_PATH)
    vectors = sp.load_npz(VECTORS_PATH)
    return chunks, vectorizer, vectors


def retrieve_rag_context(query: str, top_k: int = 3) -> dict[str, Any]:
    chunks, vectorizer, vectors = _load_index()
    normalized_query = query.strip() or "Transformer LLM 学習"
    q_vec = vectorizer.transform([normalized_query])
    scores = (vectors @ q_vec.T).toarray().ravel()
    ranked = scores.argsort()[::-1][:top_k]

    results: list[dict[str, Any]] = []
    for idx in ranked:
        chunk = chunks[int(idx)]
        results.append(
            {
                "chunk_id": chunk["chunk_id"],
                "source_file": chunk["source_file"],
                "section": chunk["section"],
                "score": float(scores[int(idx)]),
                "text": chunk["text"],
            }
        )
    return {
        "source": "rag_ready_教材",
        "retrieval_method": "local_sparse_tfidf",
        "query": normalized_query,
        "top_k": top_k,
        "chunks": results,
    }
