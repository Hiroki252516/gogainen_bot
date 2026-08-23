# 16. Implementation Tasks

この文書は、3用語・YAML問題・RAG対応の現行実装状態を示す。

## 実装済み

- `codex/soma-three-topic-rag` ブランチ上でsomaの作業状態を引き継ぎ
- active seedを `llm_knowledge`、`multi_agent`、`memory_process` の3用語へ変更
- YAML問題バンクと起動・seed時の形式検証
- pretest/final_test各1問、retest v1〜v4、learning確認 v1〜v5
- A/B/C正答、M3優先、M1、unknownの決定論的採点
- 旧Term・問題・ログを削除せず非アクティブ化
- ローカルRAG packの読み込み、用語別section制限、LangGraph除外
- control/proposedの共通RAGと個別化payloadの分離
- 最新M1〜M4/unknown taxonomyを `backend/app/ai/misconception_taxonomy.py` から実行時注入
- Codex app-server設定 `gpt-5.6-luna` / `medium`
- frontendの参加者画面から内部debug・M分類表示を除去
- MockAIBackend、backend pytest、frontend smoke/build
- 学習教材・回答解説のMarkdown表示、正誤カード、初回読み込み・回答送信の動的進捗UI
- 現行の評価JSON、管理サマリー、全体・被験者別CSV出力

## 残タスク

- 実験本番データ取得前のapp-server接続確認
- アンケート本体の設問拡張
- 管理画面のグラフ化とフィルタ機能
- 手動診断修正UIとaudit_eventsの実運用導線
- 大人数運用時のCSV出力非同期化
- 研究本番データ用のバックアップ手順強化
- 遅延再テスト、完全な転移評価、M2/M4固定診断問題、理解度差分・足場掛け削減量の自動算出

## 実装優先順位

1. 研究ログの完全性
2. Codex app-server経由の実AI応答
3. 実験フローの正確性
4. 評価指標とCSV出力
5. MockAIBackendでのテスト再現性
6. UIの見た目
