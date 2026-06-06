# 11. Seed Questions

## 基本方針

事前テストは `問題 (1).md` の5問を採用する。被験者には選択肢のみを提示し、理由欄と自信度欄は出さない。

各選択式問題には以下を持たせる。

- correct option
- M1 option
- M2 option
- M3 option
- unknown option

添付問題の `L4` は、本システムの最強支援 `L3` として正規化する。システム、DB、AI schemaには `L4` を追加しない。

正式な再テスト、L0確認、転移テスト問題は後で差し替える。MVPではアプリを完走できるよう、5概念それぞれに仮問題を `*_temporary_v1` としてseedする。

## Seed Terms

1. Transformer
2. Attention
3. LLMの学習段階
4. 事前学習
5. 事後学習

## PRE_Q01 Transformer

Transformerの構造について、最も適切な説明はどれか。

A. AttentionレイヤーとFFNレイヤーを重ね、トークン間の関係性とトークンごとの特徴変換を繰り返す構造。
B. Transformerとは、AIが文章全体を人間のように意識して読む能力そのもの。
C. TransformerはRNNと同じで、前の時刻の隠れ状態を順番に渡しながら処理する構造。
D. Transformerは『変換する』という名前なので、単に文章を別の言語へ翻訳する機能のこと。
E. わからない。

Labels: A correct / B M1 / C M2 / D M3 / E unknown

## PRE_Q02 Attention

TransformerにおけるAttentionの役割として、最も適切なものはどれか。

A. 入力中のトークン同士の関係の強さを計算し、重要度に応じて情報を重み付けして利用する仕組み。
B. AIが人間のように注意や集中を向ける心理的な能力。
C. FFNと同じで、各トークンの特徴量ベクトルを個別に変化させる処理。
D. 文章中に出てくる重要そうな単語だけを探して印を付ける処理。
E. わからない。

Labels: A correct / B M1 / C M2 / D M3 / E unknown

## PRE_Q07 LLMの学習段階

対象範囲で説明されているLLMの主な学習プロセスの組み合わせとして、最も適切なものはどれか。

A. 事前学習、インストラクションチューニング、事後学習。
B. 入力、思考、感情、会話という人間の学習段階。
C. プロンプト、コンテキストウィンドウ、Function Calling。
D. 『事前』『事後』という語があるので、学習前と学習後のテストだけを指す。
E. わからない。

Labels: A correct / B M1 / C M2 / D M3 / E unknown

## PRE_Q08 事前学習

LLMの事前学習の目的として、最も適切なものはどれか。

A. 大規模で多様なテキストデータなどから、言語理解・生成能力や一般的知識の基盤を獲得すること。
B. 人間が使う前に、AIに性格や倫理観を教え込む最終調整のこと。
C. インストラクションチューニングと同じで、質問と理想回答のペアだけを学習すること。
D. 事前という言葉があるので、モデルを使う前にユーザが入力する注意書きのこと。
E. わからない。

Labels: A correct / B M1 / C M2 / D M3 / E unknown

## PRE_Q14 事後学習

LLMの事後学習の説明として、最も適切なものはどれか。

A. LLMの出力を人間の価値観や安全性・有用性により合うよう、人間評価や報酬モデルなどを用いて調整する段階。
B. AIが出力した後に、人間のように反省して感情を整える段階。
C. 事前学習と同じで、Web上の膨大なテキストから次単語予測を学ぶ段階。
D. 事後という語があるので、ユーザへの回答が終わった後にログを保存するだけの処理。
E. わからない。

Labels: A correct / B M1 / C M2 / D M3 / E unknown

## Temporary Retest / L0 / Transfer

正式問題が提供されるまで、以下の仮問題をseedする。

- Retest: 事前テストと同じ構成概念を別文面の選択式で測る。
- L0: 各概念をヒントなしで自由記述説明させる。
- Transfer: 教材と異なる短い応用場面で概念を説明させる。

仮問題の `variant_key` は `retest_temporary_v1`, `l0_temporary_v1`, `transfer_temporary_v1` とし、正式問題と区別できるようにする。

## RAG Reference

学習セッションでは `rag_ready_教材` をローカルRAGとして参照する。

- `chunks.jsonl`
- `vectors_tfidf_sparse.npz`
- `tfidf_vectorizer.joblib`

取得した上位3チャンクをAI payloadの `rag_context` に入れる。統制群にも同じ教材コンテキストを渡すが、統制群では誤概念タイプや過去ログに基づく個別化は行わない。
