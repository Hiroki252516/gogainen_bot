# Backend API Spec

## Participant Flow API

- `POST /api/participants`: 参加者を作成し、`current_step=initial_test` にする。
- `GET /api/participants/{participant_id}/current-step`: `initial_test`, `learning_targets`, `retest`, `final_test`, `finish` をURLへ解決する。
- `GET /api/experiment/{participant_id}/initial-test`: `initial_test_v1` の全5問を返す。
- `POST /api/participants/{participant_id}/diagnose-initial-test`: 初期テストを採点し、正答以外を学習対象にする。
- `GET /api/participants/{participant_id}/learning-targets`: 現在ループで未完了の学習対象だけを返す。
- `POST /api/learning-sessions`: 現在ループ用の固定選択式学習sessionを作成する。再学習では新しいsessionを作る。
- `GET /api/learning-sessions/{session_id}`: 現在教材、問題、表示順、進捗を返す。正答IDやMタイプは返さない。
- `POST /api/learning-sessions/{session_id}/prerequisite-attempts`: 前提用語問題への選択回答を保存する。
- `POST /api/learning-sessions/{session_id}/concept-phase1-attempts`: 概念フェーズ1問題への選択回答を保存する。
- `GET /api/experiment/{participant_id}/retest`: `retest_v1` の全5問を返す。
- `POST /api/participants/{participant_id}/score-retest`: 再テスト回を保存し、全問正解なら `/final-test`、不正解があれば `/learning-targets` を返す。
- `GET /api/experiment/{participant_id}/final-test`: `final_test_v1` の全5問を返す。
- `POST /api/participants/{participant_id}/score-final-test`: 最終テストを採点し、`current_step=finish` にする。

## Inactive Compatibility

事前アンケート、事後アンケート、L0確認、転移テスト、概念フェーズ2の既存テーブルや一部APIは互換のため残してよいが、参加者フローからは呼ばない。
