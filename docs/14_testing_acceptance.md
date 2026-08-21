# Testing Acceptance

## Backend

- YAMLにactive termが `llm_knowledge`、`multi_agent`、`memory_process` の3件だけ存在する。
- 各固定問題がA〜Jの10選択肢で、A/B/C、M1、M3、unknownの配分が3/3/3/1になる。
- pretest・final_testが各用語1問、retestが各用語4バリエーション、learning確認がstage・用語ごとに5バリエーションになる。
- A/B/C完全一致だけが正解、J単独だけがunknown、M3がM1より優先される。
- retestはv1〜v4を使い、5回目以降はv4を再利用する。
- learning確認はv1〜v5を使い、6回目以降はv5を再利用する。
- RAGは用語別の指定sectionだけを検索し、LangGraphチャンクを返さない。
- controlとproposedのRAG本文が共通で、proposedだけにtaxonomy・履歴・足場掛け情報が入る。
- app-server payloadが `gpt-5.6-luna` / `medium` を使う。

## Frontend

- pretest/retest/final-testで3用語が表示される。
- 10択複数選択UIで、3つまたはJ単独以外は送信できない。
- 学習画面にM1〜M4、unknown、LangGraph、内部教授方略を表示しない。
- 学習本文、問題、結果表示がモバイル幅で重ならない。
- 旧stage名や旧Transformerの新規導線に依存しない。

## Regression

- `AI_BACKEND=mock` で固定問題・遷移・RAG契約テストが通る。
- `AI_BACKEND=codex_app_server` でMockへ自動フォールバックしない。
- 既存の単一選択API互換、DB列、CSV列、過去ログを壊さない。

## Commands

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
docker compose build backend frontend
docker compose up -d --force-recreate backend frontend
```
