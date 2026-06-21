# 08. Backend API Spec

## Tests

- `GET /api/experiment/{participant_id}/pretest`: `pretest_v2`
- `GET /api/experiment/{participant_id}/retest`: 参加者に固定された `retest_v2`、全5概念
- `POST /api/attempts`: テスト回答保存。即時正誤は返さない

## Learning Session

### `POST /api/learning-sessions`

activeコンテンツ版を固定し、前提用語を展開し、最初のAI教材と問題を返す。

### `GET /api/learning-sessions/{id}`

返す:

- stageと進捗
- 現在教材
- 現在問題
- ランダム化済み選択肢
- 前回フィードバック

返さない:

- correct option ID
- is_correct
- Mタイプ
- 診断理由
- linked prerequisite keys

### Answer APIs

- `POST /api/learning-sessions/{id}/prerequisite-attempts`
- `POST /api/learning-sessions/{id}/concept-phase1-attempts`
- `POST /api/learning-sessions/{id}/concept-phase2-attempts`

Request:

```json
{
  "question_id": "uuid",
  "selected_option_id": "uuid"
}
```

`Idempotency-Key` は必須。backendが選択肢メタデータで採点し、次状態を決める。

### Retry

`POST /api/learning-sessions/{id}/retry-material`

技術停止した教材生成だけを再試行する。回答ログを再作成しない。

## Content Administration

- `POST /api/seed`: YAMLを再検証・同期
- 旧版を削除せず非active化
- runtime生成問題は `runtime_ai_fallback` として保存
