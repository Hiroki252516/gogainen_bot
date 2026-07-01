# 16. Implementation Tasks

このファイルは現行プログラムの実装状態を示す。未実装チェックリストではなく、運用時に確認する実装済み機能と残タスクを整理する。

## 実装済み

- Next.js frontend と FastAPI backend のDocker Compose構成
- PostgreSQL本番相当構成とSQLiteローカル構成
- SQLAlchemy models と起動時の軽量スキーマ更新
- active seed: `llm_training_process`, `transformer`
- 事前テスト、診断、学習対象選択、学習セッション、再テスト、最終テスト、survey遷移
- 再テストは事前テスト対象の全問を出題
- L2概念理解問題・再テスト・最終テストの同一問題文/選択肢運用
- テスト回答と学習ターン回答の `question_shown_at`, `answered_at`, `response_time_sec` 保存
- `answer_history` によるテスト回答と学習ターン回答の統合ログ
- 全体ログCSV、被験者別ログCSV、Excel向けUTF-8 BOM付きCSV
- Codex app-server backend、AI status、ChatGPT/device codeログイン導線
- `AI_BACKEND=codex_app_server` でMockへ自動フォールバックしない失敗ログ
- MockAIBackendを使った自動テスト
- 管理画面で全体ログ、被験者別ログ、AI呼び出し、再発イベント、評価サマリーを確認
- 現行評価サマリーとして `pretest_score`, `retest_score`, `l0_correct_rate`, 同種誤答再発率、Mタイプ別再発率を保存

## 残タスク

- アンケート本体の設問拡張
- 管理画面のグラフ化とフィルタ機能
- 事前テスト、再テスト1、再テスト2、最終テストの得点率推移ログ
- 誤概念タイプの時系列推移ログ
- 手動診断修正UIとaudit_eventsの実運用導線
- export_jobsの実ジョブ履歴化
- 大人数運用時のCSV出力非同期化
- 研究本番データ用のバックアップ手順強化

## 実装優先順位

1. 研究ログの完全性
2. Codex app-server経由の実AI応答
3. 実験フローの正確性
4. 評価指標とCSV出力
5. MockAIBackendでのテスト再現性
6. UIの見た目
