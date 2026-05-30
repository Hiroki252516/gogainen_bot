# Repository Instructions for Codex

このリポジトリは、卒業研究用AIチューターの仕様リポジトリです。ユーザーから明示的に実装開始を依頼されるまでは、アプリケーションコードを作成しないでください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/99_sources_and_notes.md` は研究計画PPTXと設計判断の根拠として扱う。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 提案群だけが、誤概念タイプ、過去ログ、足場掛けレベルを教授方略に使う。
- 統制群では、誤概念分類を保存しても教授には使わない。
- 被験者画面に `M1`、`M2`、`M3`、`M4` を直接表示しない。
- 再テスト、L0確認、転移テストではチャット、ヒント、即時正解表示を禁止する。
- 同じ問題文をそのまま再利用しない。事前、学習、再テスト、転移で問題バリアントを分ける。

## AI Backend Rules

- OpenAI APIキーを要求しない。
- OpenAI SDKで通常APIを直接呼ばない。
- AI呼び出しは必ず `AIBackend` インターフェース経由にする。
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
