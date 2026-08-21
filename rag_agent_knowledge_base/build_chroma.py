#!/usr/bin/env python3
# Optional: create a local ChromaDB collection using the precomputed embeddings.
import json, numpy as np
from pathlib import Path
import chromadb
ROOT=Path(__file__).resolve().parent
chunks=[json.loads(x) for x in (ROOT/'chunks.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
E=np.load(ROOT/'embeddings.npy')
client=chromadb.PersistentClient(path=str(ROOT/'chroma_db'))
col=client.get_or_create_collection('agent_knowledge',metadata={'hnsw:space':'cosine'})
metas=[]
for c in chunks:
    metas.append({'source_file':c['source_file'],'page_start':c['page_start'] or -1,'page_end':c['page_end'] or -1,'line_start':c['line_start'] or -1,'line_end':c['line_end'] or -1,'heading':c['heading'] or ''})
col.upsert(ids=[c['chunk_id'] for c in chunks],documents=[c['text'] for c in chunks],metadatas=metas,embeddings=E.tolist())
print(f'created/updated {col.count()} chunks at {ROOT/"chroma_db"}')
