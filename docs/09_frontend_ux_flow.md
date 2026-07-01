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

## Learning Text Rendering

学習セッション内のAI生成文はMarkdownとして表示する。対象は教材、誤答解説、正答時・強制解決時の要点である。raw HTMLは有効化せず、見出し、箇条書き、太字、短い段落を読みやすいカード内に描画する。
