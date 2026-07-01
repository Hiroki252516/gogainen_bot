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
- `/learning/[termSlug]`: L3（前提用語学習）とL2（概念理解フェーズ1）を表示。概念フェーズ2は表示しない。
- `/retest`: 全5概念の再テスト。採点後、APIの `next_url` に従って自動分岐する。
- `/final-test`: 全5概念の最終テスト。採点後、得点を表示せず `/finish` へ進む。

`/pretest`, `/survey/post`, `/l0-check`, `/transfer-test` は参加者導線に出さない。

## Learning Session Progress

`/learning/[termSlug]` は、上部にステップバーと現在対象サマリーを表示する。表示する情報は、対象概念、現在フェーズ、L3用語の位置、現在のL3用語またはL2確認、小問数、試行数、サイクルである。L3は5件の前提用語を扱うが、暫定運用では各用語1小問だけを必須にする。L2は2小問を維持する。

回答送信後は結果が返るまで、ボタンを分析中表示にし、回答記録、解説生成、次教材準備などの処理状態を進捗ステップとして表示する。これは内部思考の開示ではなく、待機中の状態説明に限定する。

## Learning Text Rendering

学習セッション内のAI生成文はMarkdownとして表示する。対象は教材、誤答解説、正答時・強制解決時の要点である。raw HTMLは有効化せず、見出し、箇条書き、太字、短い段落を読みやすいカード内に描画する。
