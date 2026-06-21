# 14. Testing and Acceptance Criteria

## Content

- YAML schemaとrelease版が有効
- 255学習問題をDBへ展開
- 全問題が5択、correct/M1/M2/M3/unknown各1件
- 前提用語・問題・retest版を参加者へ固定
- 旧版を非activeで保持

## Backend

- pretestは5問、選択式のみ
- 全誤答時に学習対象5件
- 両群が同じ固定前提用語・固定問題を使う
- 前提用語とフェーズ1の各スロットで最大3試行
- 3回誤答で正答提示とforced_resolved
- 提案群だけがフェーズ1誤答で前提用語レビューへ戻る
- 提案群だけがフェーズ2誤答でフェーズ1へ戻る
- 統制群フェーズ2は1回でcompleted
- 統制群AI payloadに事前診断・累積ログ・戻り履歴がない
- 教材漏洩検出、最大3回再生成、技術停止、retry
- 問題枯渇時にruntime_ai_fallbackを検証・保存
- retest_v2を全5概念返す
- 新評価指標とCSVを再計算可能

## Frontend

- learning pageにtextarea、自信度、自由記述確認がない
- 固定5択、教材、進捗、即時正誤を表示
- 1〜2回目誤答で正答を表示しない
- 強制解決時だけ正答を表示
- フェーズ2では教材と軽い条件を表示しない
- 再読み込み後も選択肢順と進捗を維持

## Commands

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
docker compose build backend frontend
```
