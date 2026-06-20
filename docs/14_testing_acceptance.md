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
- activeなpretestは `pretest_v2` だけで、旧 `pretest_v1` は非active
- pretest各問にcorrect/M1/M2/M3/unknownが1件ずつ保存される
- pretestのM1〜M3選択肢に診断意図が内部メタデータとして保存される
- 同一参加者・同一問題への再取得で、保存済みの選択肢表示順が維持される
- pretest全誤答時にlearning targetsが5件になる
- stable_correctだけの用語はlearning targetsに入らない
- 提案群セッションで前提用語が3件生成・保存される
- 統制群セッションでも一般小問が3件生成・保存される
- 提案群のAI payloadにRAG、pretest診断、選択誤答、学習ログが入る
- 統制群payloadにはRAGと対象概念だけが入り、誤概念・pretest選択肢・ログ・戻り制御情報が入らない
- 提案群で前提用語2回fail時にsessionがblockedになる
- 統制群で小問fail時に戻らず次小問またはphase1へ進む
- 提案群でphase1 pass後にphase2へ進む
- 提案群でphase1 3回fail時にsessionがfailed_phase1になる
- 提案群でphase2 fail 1〜2回目はphase1へ戻る
- 提案群でphase2を3回failするとsessionがfailed_phase2になる
- 統制群のphase1/phase2は1回だけ採点し、pass/failに関係なく進行・完了する
- retest後のnext stepがpost_surveyになる
- L0/transferはactive出題されない
- phase2補助指標がevaluation_summaryとCSVに出る
- recurrence_flagは同一termでpretest/retestのM1〜M3が一致した場合だけtrue

## Frontend Acceptance

- `/pretest` は5問、選択肢のみ
- `/learning/[termSlug]` はgroup_conditionで分岐する
- 提案群は前提用語、phase1教材あり、phase2教材なしを順に表示する
- 提案群phase2 fail後にphase1画面へ戻る
- 統制群は小問、phase1、phase2を表示するが、適応的戻り処理を表示しない
- `/retest` は選択肢のみで、理由欄と自信度欄を表示しない
- `/retest` 完了後 `/survey/post` へ進む
- `/survey/pre`, `/l0-check`, `/transfer-test` は通常導線に出ない

## AIBackend Acceptance

通常実行では `AI_BACKEND=codex_app_server` を使う。

- `codex_app_server` モードではMockへ自動フォールバックしない
- app-server未接続・未ログイン・timeout・schema失敗は `ai_call_logs.status=failed` に残す
- `AI_BACKEND=mock` はテスト時に完全に動く
- 新AI契約の `generate_concept_phase1_material`, `grade_concept_phase1_answer`, `generate_concept_phase2_prompt`, `grade_concept_phase2_answer`, `generate_control_prerequisite_plan` がMockとCodexAppServerBackendに実装される

## End-to-End Test Scenario

### proposed participant

1. Participant P001をproposedで作成
2. 5問すべてunknownで回答
3. Diagnosis後、learning targetが5件になる
4. 1対象概念のlearning sessionで前提用語3件が生成される
5. 1つ目の前提用語を2回failさせ、sessionがblockedになる
6. 別sessionで前提用語をすべてpassさせる
7. phase1 pass後にphase2へ進む
8. phase2 fail時にphase1へ戻り、再支援後のphase2 passでsessionがcompletedになる
9. retestで同じMを選ぶとrecurrence_flag true
10. evaluation_summaryにretestとphase1/phase2指標が反映される

### control participant

1. Participant P002をcontrolで作成
2. pretest誤答を入力
3. Diagnosisは保存される
4. 学習画面では小問3件、phase1、phase2を行う
5. 小問やphaseのfailで戻り制御されない
6. AI request payloadにはRAGと対象概念だけが入り、誤概念やpretest診断が入らない
7. retest後にpost_surveyへ進む

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
