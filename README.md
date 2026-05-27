# 学習ログ駆動型AIチューター 開発仕様書

このディレクトリは、Codexに渡して「誤概念タイプと足場掛けレベルに基づく AI・情報系専門用語の概念理解支援システム」を実装してもらうための仕様書一式です。

## 目的

AI・情報系専門用語の学習において、学習者の回答ログから誤概念タイプを診断し、教授方略と足場掛けレベルを調整するAIチューターを実装する。

主評価指標:

1. 同種誤答再発率
2. 足場掛けなし自力解答率
3. 足場掛けなし転移率

## 前提

- 開発対象環境: MacBook Air M4
- 実行環境: Docker / Docker Compose
- AIバックエンド: OpenAI APIキーは使わない
- AI呼び出し: Codex app-server 経由
- 認証: ユーザーの ChatGPT/Codex ログインを利用
- ただしCodex app-serverは仕様変更可能性があるため、AI呼び出し部分は必ず抽象化する

## 推奨構成

- frontend: Next.js + TypeScript
- backend: FastAPI + Python
- db: PostgreSQL
- ai-adapter: Codex app-server JSON-RPC client
- analysis: CSV export + pandas互換出力
- docker: docker-compose

## Codexへの依頼

`prompt.md` をCodexの最初のプロンプトとして渡してください。
