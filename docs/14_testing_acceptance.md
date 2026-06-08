# 14. Testing and Acceptance Criteria

## Testing Strategy

研究システムなので、見た目よりも以下を重点的にテストする。

- 実験フローが崩れないこと
- 群条件が混ざらないこと
- ログが欠けないこと
- 評価指標が再計算可能であること
- 通常実行でCodex app-server経由のAI呼び出しが動くこと
- 自動テストではMockAIBackendを明示指定して決定論的に動くこと

## Backend Acceptance

- pretestは5問、選択肢のみ、理由欄/自信度なし
- pretest全誤答時にlearning targetsが5件になる
- stable_correctだけの用語はlearning targetsに入らない
- 提案群セッションで前提用語が3件生成・保存される
- 提案群の前提用語AI payloadにRAGとpretest診断が入る
- 用語理解2回failで概念理解へ進まず、sessionがblockedになる
- 概念理解failで不足用語 + 直前関連用語レビューへ戻る
- 概念理解4回failでsessionがfailedになる
- 統制群payloadにはRAGが入り、誤概念・ログ・前提用語ゲート情報が入らない
- retest後のnext stepがpost_surveyになる
- L0/transferはactive出題されない
- recurrence_flagは同一termでpretest/retestのM1〜M3が一致した場合だけtrue

## Frontend Acceptance

- `/pretest` は5問、選択肢のみ
- `/learning/[termSlug]` はgroup_conditionで分岐する
- 提案群は前提用語カード、記述確認、概念説明確認を表示する
- 統制群は通常説明と自己説明欄だけを表示し、前提用語ゲートを表示しない
- `/retest` は選択肢のみで、理由欄と自信度欄を表示しない
- `/retest` 完了後 `/survey/post` へ進む
- `/survey/pre`, `/l0-check`, `/transfer-test` は通常導線に出ない

## AIBackend Acceptance

通常実行では `AI_BACKEND=codex_app_server` を使う。

- `codex_app_server` モードではMockへ自動フォールバックしない
- app-server未接続・未ログイン・timeout・schema失敗は `ai_call_logs.status=failed` に残す
- `AI_BACKEND=mock` はテスト時に完全に動く
- 新AI契約の6メソッドがMockとCodexAppServerBackendに実装される

## End-to-End Test Scenario

### proposed participant

1. Participant P001をproposedで作成
2. 5問すべてunknownで回答
3. Diagnosis後、learning targetが5件になる
4. 1対象概念のlearning sessionで前提用語3件が生成される
5. 1つ目の前提用語を2回failさせ、sessionがblockedになる
6. 別sessionで前提用語をすべてpassさせる
7. 概念理解fail時に不足用語レビューへ戻る
8. 概念理解pass時にsessionがcompletedになる
9. retestで同じMを選ぶとrecurrence_flag true
10. evaluation_summaryにretestとgate指標が反映される

### control participant

1. Participant P002をcontrolで作成
2. pretest誤答を入力
3. Diagnosisは保存される
4. 学習画面では一般解説のみ
5. AI request payloadにはRAGだけが入り、誤概念やpretest診断が入らない
6. retest後にpost_surveyへ進む

## Required Commands

- `cd backend && .venv/bin/pytest -q`
- `cd frontend && npm test`
- `cd frontend && npm run build`
- `docker compose build backend frontend`

## Definition of Done

- backend tests pass
- frontend tests pass
- frontend build passes
- docker compose build passes
- `/api/health` がok
- `/api/admin/ai/status` が応答する
- `/pretest` が表示できる
