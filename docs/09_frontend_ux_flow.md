# Frontend UX Flow

```text
/start -> /initial-test -> /diagnosing -> /learning-targets
       -> /learning/[termSlug] ... -> /retest
       -> /learning-targets または /final-test
       -> /finish
```

## Screens

- `/initial-test`: 初期テスト。全5問の選択式のみ。
- `/learning-targets`: 現在ループで学習すべき概念だけを表示。
- `/learning/[termSlug]`: 前提用語フェーズと概念フェーズ1を表示。概念フェーズ2は表示しない。
- `/retest`: 全5概念の再テスト。採点後、APIの `next_url` に従って自動分岐する。
- `/final-test`: 全5概念の最終テスト。採点後、得点を表示せず `/finish` へ進む。

`/pretest`, `/survey/post`, `/l0-check`, `/transfer-test` は参加者導線に出さない。
