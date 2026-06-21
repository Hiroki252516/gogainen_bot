# 02. Experiment Flow

```text
Start
  -> Participant Registration
  -> Pretest (5 concepts, MCQ only)
  -> Diagnosis and Learning Target Selection
  -> Learning Sessions for non-correct concepts, max 5
       1. Fixed prerequisites
       2. Concept phase 1 with AI material
       3. Concept phase 2 without material
  -> Retest v2 (all 5 concepts)
  -> Post Survey
  -> Finish
```

## Pretest

- active版は `pretest_v2`
- 選択式のみ
- 選択肢順を参加者ごとにランダム化して保存
- correctは学習対象外
- M1/M2/M3/unknownはすべて学習対象

## Fixed Prerequisites

- YAMLで概念ごとの名称と順序を固定
- 初期版は各概念5件
- 両群で全件実施
- 各用語は必須2スロット、各スロット最大3バリアント
- AIは教材だけを参加者ごとに生成

## Immediate Feedback

- 正答: 正答表示と短い要点を表示
- 1〜2回目誤答: 不正解表示、AI誤答説明、再教材、別バリアント。正答は非表示
- 3回目誤答: 正答と要点を表示し `forced_resolved`

## Concept Phase 1

- AI教材あり
- 必須2スロット、各最大3試行
- 提案群の誤答時は `linked_prerequisite_keys` の先頭前提用語を未使用問題で1問レビュー
- 統制群は前提用語へ戻らず一般再教材を表示
- 全スロットがpassedまたはforced_resolvedならフェーズ2へ進む

## Concept Phase 2

- 教材・ヒント・軽い条件を表示しない
- 提案群は最大3回。1〜2回目誤答は新しいフェーズ1サイクルへ戻り、3回目誤答は正答提示後completed
- 統制群は1回でcompleted

理解不足によるblocked/failed状態は使わない。AI、RAG、コンテンツ不整合時だけ `technical_blocked` とする。

## Retest

- active版は `retest_v2`
- 全5概念を出題
- 正誤、教材、ヒント、正答を表示しない
- 完了後は事後アンケートへ進む
