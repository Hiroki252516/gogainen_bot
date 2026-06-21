# 09. Frontend UX Flow

## Participant Route

```text
/start -> /pretest -> /diagnosing -> /learning-targets
       -> /learning/[termSlug] ... -> /retest -> /survey/post -> /finish
```

事前アンケート、L0確認、転移テストは導線に含めない。

## Learning Page

表示:

- 対象概念
- 前提用語・必須問題・試行・サイクルの進捗
- AI教材。ただしフェーズ2では表示しない
- 固定5択問題
- 回答後の正誤
- 正答時の短い要点
- 誤答時の不適切理由と再教材

表示しない:

- textarea
- 自信度
- 自由記述による追加確認
- M1〜M4
- 正答位置。ただし3回目誤答時の強制解決では表示する

## Group Difference

- 提案群: フェーズ1誤答時の前提用語レビュー、フェーズ2誤答後のフェーズ1復帰を表示
- 統制群: 同じ問題と試行上限を使うが、適応的レビューは表示しない。フェーズ2は1回

## Retest

全5概念、選択式のみ。正誤、教材、ヒント、得点は表示しない。
