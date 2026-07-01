# Testing Acceptance

## Backend

- 初期・再・最終テストが全5問、5択、理由欄なし、自信度なしで返る。
- 初期テスト不正解/unknownのみが初回学習対象になる。
- 再テスト全問正解時は `next_step=final_test`。
- 再テスト1問以上不正解時は `next_step=learning_targets` で、不正解概念だけが再学習対象になる。
- 再学習では新しい `LearningSession` が作成される。
- 概念フェーズ1完了後、概念フェーズ2へ進まずsessionが完了する。
- 統制群AI payloadに初期診断、Mタイプ履歴、再テスト誤答履歴が入らない。
- 提案群AI payloadには初期診断、学習履歴、再テスト誤答Mタイプが入る。
- 最終テスト採点後は `finish` になり、事後アンケートへ遷移しない。

## Frontend

- `/start -> /initial-test -> /diagnosing -> /learning-targets` が動く。
- 学習画面に概念フェーズ2が出ない。
- `/retest` が不正解時に学習へ戻り、全問正解時に `/final-test` へ進む。
- `/final-test` 後に `/finish` へ進み、得点を表示しない。
