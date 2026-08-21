# RAG Agent Knowledge Base

アップロードされた2つのTXTを、AI/RAG参照用に構造を保ちながらチャンク化し、検索ベクトルを付与したZIPです。

## 収録物
- `chunks.jsonl` — 32チャンク。本文、節階層、ページ、元行番号、embedding行を保持
- `embeddings.npy` — 8192次元・L2正規化済みのdense embedding
- `embeddings_sparse.npz` — 同じベクトルの省メモリ版（検索推奨）
- `retrieval_model.joblib` — 質問文を同じベクトル空間に変換するモデル
- `search_rag.py` — cosine類似度でTop-K検索する実行例
- `build_chroma.py` — 事前計算済みembeddingをChromaDBへ投入する任意スクリプト
- `metadata.csv` — embedding行と出典の対応表
- `manifest.json` — ベクトル方式、次元数、元ファイルSHA-256
- `sources/` — 元TXTコピー

## すぐ検索
```bash
pip install -r requirements.txt
python search_rag.py "MemGPTの特徴は？"
python search_rag.py "RAGとChromaDBについて"
```

## ChromaDBにする場合
```bash
pip install -r requirements-chroma.txt
python build_chroma.py
```

## Embedding方式について
この環境では外部Embedding API/ニューラルEmbeddingモデルを利用せず、**日本語文字2〜5-gram + TF-IDF** を8192次元のL2正規化ベクトルとして事前計算しています。固有名詞・専門語・日本語表記の検索に強く、ZIPだけで質問ベクトルを再現できます。

より広い意味類似検索が必要な場合は、`chunks.jsonl` の各 `text` を OpenAI Embeddings / multilingual-e5 / BGE-M3 等で再embeddingし、`embedding_row` 順に差し替えられます。出典メタデータはそのまま利用できます。
