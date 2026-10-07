# 現行実験の概要

実験仕様版は `1`。現行の実装とこの版の文書を正本とする。旧設計は [履歴資料](history/2026-10-06/00_project_summary.md) に保存しており、実行要件ではない。

- 対象概念は `llm_knowledge`、`multi_agent`、`memory_process` の3つ。
- 比較は通常AIチューター（control）と誤答・ログ適応型AIチューター（proposed）。両群とも同じ実AI・共通RAGを利用する。
- 分類は M1（単一命題の誤り）、M3（カテゴリー誤り）、unknown（知識不足）。理解状態は `stable_correct`、`misconception`、`unknown`。
- 問題はYAML/backendで固定し、AIは教材と即時解説だけを生成する。
- 事前3問、再テスト3問×5 variant、最終3問の計21問。学習確認は現行v2の30問のみ。
- A〜Iから3つ、またはJのみを選ぶ。正解3つの完全選択だけが正解。M3優先判定を維持する。
- A〜C正解、D〜F=M1、G〜I=M3、J=unknownは一時的なデバッグ配置。研究データ収集前に分散を復旧する。

新規参加者だけに `experiment_spec_version=1` を保存する。既存試用（旧v1/v2とも）と未対応版は閲覧専用で、記録・完了状態を変更しない。独立した追加評価フェーズは設けず、教材内の適用確認 `transfer_check` は維持する。

研究ログ、実AI応答、実験遷移を優先する。OpenAI APIキーを要求せず、Codex app-server未接続時はMockへ自動フォールバックしない。
