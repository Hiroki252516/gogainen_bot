# Repository Instructions for Codex

このリポジトリは、卒業研究用AIチューターのアプリケーションリポジトリです。現行実装と実験仕様版1のdocsを基準に作業してください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/99_sources_and_notes.md` は研究計画PPTXと設計判断の根拠として扱う。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 現行分類はM1/M3/unknownのみ。提案群だけが診断・対象主張・過去ログを教材の具体化に使う。方略はbackendで固定する。
- 統制群では、誤概念分類を保存しても教授には使わない。
- 被験者画面に内部分類、群名、教授方略を直接表示しない。
- テスト回答中はチャット・ヒント・即時正解を表示せず、回答送信後の結果確認では正誤を表示する。
- テスト系はpretest 1 variant、retest 5 variant、final_test 1 variant、学習確認は現行v2のみ。同文・選択肢を全フェーズで使い回さない。
- 全対象のA〜C正解、D〜F=M1、G〜I=M3、J=unknownは一時デバッグ配置。研究データ収集に使用しない。
- 既存試用・未対応版は閲覧専用。既存行へ実験仕様版を付け直さず、進行・回答・評価を更新しない。旧案はdocs/historyに隔離する。
- 教材内のtransfer_checkは維持するが、独立した追加テスト・旧支援量・自由回答処理を戻さない。
- 現行MVP対象用語は `llm_knowledge`、`multi_agent`、`memory_process` の3項目とする。

## AI Backend Rules

- OpenAI APIキーを要求しない。
- OpenAI SDKで通常APIを直接呼ばない。
- AI呼び出しは必ず `AIBackend` インターフェース経由にする。
- AIタスクは教材生成・正答要約・誤答解説だけ。採点・分類・状態更新・方略決定はbackendで行う。
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/Codexログイン済みapp-serverへ接続する。
- `MockAIBackend` は自動テスト・障害切り分け専用にし、通常実験データへ混ぜない。
- `AI_BACKEND=codex_app_server` ではMockへ自動フォールバックしない。
- ChatGPT/Codex認証情報、アクセストークン、APIキーをDBに保存しない。

## Implementation Priorities

1. 研究ログの完全性
2. Codex app-server経由の実AI応答
3. 実験フローの正確性
4. 評価指標とCSV出力
5. MockAIBackendでのテスト再現性
6. UIの見た目

## Editing Policy

- 仕様整理の依頼ではMarkdownだけを編集する。
- 実装開始の依頼では、仕様にない独自判断を最小限にし、判断した内容はREADMEまたは該当docsに追記する。
- 不明点が実装を止めるほどでなければ、`docs/19_experiment_operation_runbook.md` と `docs/99_sources_and_notes.md` の方針を優先して進める。
