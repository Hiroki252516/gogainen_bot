# RAG-ready package: 教材(1).txt

このフォルダは、添付された `教材(1).txt` をRAGで参照するために、ローカル検索できる形へ加工したものです。

## 生成物

- `source/教材(1).txt`: 元ファイル
- `source/教材(1)_normalized.txt`: 改行・分割位置を整えた本文
- `chunks.jsonl`: RAG検索単位に分割したチャンク本文とメタデータ
- `vectors_tfidf_sparse.npz`: チャンクごとのローカル疎ベクトル
- `tfidf_vectorizer.joblib`: クエリを同じ空間へ変換するためのベクトライザ
- `metadata.json`: 作成条件・件数・ハッシュ
- `retrieve_demo.py`: ローカル検索のサンプル
- `rag_prompt_template.md`: 取得チャンクをLLMへ渡すプロンプト例
- `openai_vector_store_setup.py`: OpenAI Vector Storeに登録する場合のテンプレート

## 状態

- チャンク数: 5
- ベクトル形状: 5 chunks × 6827 features
- ベクトル方式: scikit-learn TF-IDF sparse vector

## 使い方

```bash
pip install scikit-learn scipy joblib
python retrieve_demo.py "Transformerの利点は？" --top-k 3
```

出力されたチャンクを `rag_prompt_template.md` の `{retrieved_context}` に入れ、LLMに渡すとRAGとして参照できます。

## 注意

この環境では外部APIキーを使ってOpenAIのEmbedding APIを呼び出せないため、OpenAIの `text-embedding-3-small` 等によるHosted Vector Storeは作成していません。
本番で意味検索品質を高める場合は、`openai_vector_store_setup.py` を手元で実行し、作成された `vector_store_id` をAIアプリに接続してください。
