# 16. Implementation Tasks

この文書は、現在のチェックアウトにおける3用語・YAML問題・RAG対応の実装状態を示す。研究計画上の未実装条件は「残タスク」に分ける。

## 実装済み

- 現行チェックアウトの実装状態を基準に仕様を整理
- active seedを `llm_knowledge`、`multi_agent`、`memory_process` の3用語へ変更
- テスト系YAML問題バンクと、起動時に検証する版付き学習確認問題バンク
- pretest/final_test各1問、retest v1〜v5、既存参加者向けlearning v1、新規参加者向けlearning v2の30場面variant
- テスト系・learning v2の保存済み選択肢役割による採点と、learning v1の固定ラベル採点（M3優先）
- 現行デバッグ用の全バンク固定役割（A〜C正解、D〜F=M1、G〜I=M3、J=unknown）。研究データ収集には不適切
- 旧Term・問題・ログを削除せず非アクティブ化
- ローカルRAG packの読み込み、用語別section制限、LangGraph除外
- control/proposedの共通RAGと個別化payloadの分離
- 最新M1〜M4/unknown taxonomyを `backend/app/ai/misconception_taxonomy.py` から実行時注入
- 提案群M1/M3/unknownの必須教授要素、本文内証拠検証、最大2回の同一AIバックエンド再生成
- 必須教授要素の研究ログ保存と管理ログ・CSVへの出力
- Codex app-server設定 `gpt-5.6-luna` / `medium`
- frontendの参加者画面から内部debug・M分類表示を除去
- MockAIBackend、backend pytest、frontend smoke/build
- 学習教材・回答解説のMarkdown表示、正誤カード、初回読み込み・回答送信の動的進捗UI
- テスト結果の正誤色分け、学習画面の研究者向け段階表示の削除、アンケート必須表示、各画面の設問進捗表示
- 現行の評価JSON、管理サマリー、全体・被験者別CSV出力

## 残タスク

- 研究データ収集開始前に、テスト系・学習確認問題の正解ラベル手掛かりをなくす役割分散を実装し、問題バンク・ローダー・テスト・運用文書を同時に更新
- 実験本番データ取得前のapp-server接続確認
- アンケート本体の設問拡張
- 管理画面の詳細なグラフ化・高度なフィルタ機能
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
