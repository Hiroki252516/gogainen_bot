#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local RAG retriever demo for 教材(1).txt.

Usage:
  python retrieve_demo.py "Transformerの利点は？" --top-k 3

This retrieves relevant chunks. Pass the returned chunks into your LLM prompt
as context for RAG.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import scipy.sparse as sp


BASE_DIR = Path(__file__).resolve().parent
CHUNKS_PATH = BASE_DIR / "chunks.jsonl"
VECTORS_PATH = BASE_DIR / "vectors_tfidf_sparse.npz"
VECTORIZER_PATH = BASE_DIR / "tfidf_vectorizer.joblib"


def load_chunks():
    with CHUNKS_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def retrieve(query: str, top_k: int = 3):
    chunks = load_chunks()
    vectorizer = joblib.load(VECTORIZER_PATH)
    vectors = sp.load_npz(VECTORS_PATH)

    q_vec = vectorizer.transform([query])
    # Vectors are L2-normalized, so dot product is cosine similarity.
    scores = (vectors @ q_vec.T).toarray().ravel()
    ranked = scores.argsort()[::-1][:top_k]

    results = []
    for idx in ranked:
        item = dict(chunks[int(idx)])
        item["score"] = float(scores[int(idx)])
        results.append(item)
    return results


def build_rag_context(results):
    blocks = []
    for r in results:
        blocks.append(
            f"[{r['chunk_id']} | {r['section']} | score={r['score']:.4f}]\n{r['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="User question / retrieval query")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    results = retrieve(args.query, args.top_k)
    print(build_rag_context(results))


if __name__ == "__main__":
    main()
