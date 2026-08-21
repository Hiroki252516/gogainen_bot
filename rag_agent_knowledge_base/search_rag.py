#!/usr/bin/env python3
import json, sys, joblib, numpy as np
from pathlib import Path
from scipy import sparse
from sklearn.feature_extraction.text import HashingVectorizer
ROOT=Path(__file__).resolve().parent
pack=joblib.load(ROOT/'retrieval_model.joblib')
p=dict(pack['hashing_params']); p['ngram_range']=tuple(p['ngram_range'])
hv=HashingVectorizer(**p); tf=pack['tfidf_transformer']
X=sparse.load_npz(ROOT/'embeddings_sparse.npz')
chunks=[json.loads(x) for x in (ROOT/'chunks.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
def search(query,k=5):
    q=tf.transform(hv.transform([query]))
    scores=(X @ q.T).toarray().ravel()  # L2 normalized => cosine similarity
    for i in np.argsort(-scores)[:k]: yield float(scores[i]),chunks[i]
if __name__=='__main__':
    q=' '.join(sys.argv[1:]).strip() or input('query> ').strip()
    for rank,(score,c) in enumerate(search(q),1):
        pg=f"p.{c['page_start']}" if c['page_start'] else '-'
        print(f"\n[{rank}] score={score:.4f} {c['chunk_id']} {c['source_file']} {pg} | {c['heading']}")
        print(c['text'])
