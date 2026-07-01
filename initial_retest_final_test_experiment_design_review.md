# 初期テスト・再テストループ・最終テスト版 実験設計整理

作成日: 2026-07-01  
更新日: 2026-07-01  
対象リポジトリ: `/Users/hiroki/ai_tutor_codex_spec`  
注意: 本ファイルはリポジトリ外の `/Users/hiroki/Downloads/initial_retest_final_test_experiment_design_review.md` として作成した整理資料であり、リポジトリ配下のファイルは編集していない。

## 1. この文書の目的

この文書は、現行リポジトリの実装内容を確認したうえで、研究者の新しい希望に沿って、実験フェーズ名と実験フローを再設計するための整理資料である。

今回整理する主な変更は次の5点である。

1. これまで「事前テスト」と呼んでいたフェーズを「初期テスト」と呼ぶ。
2. これまで「再テスト」と呼んでいた学習後の最終測定を「最終テスト」と呼ぶ。
3. 全学習対象用語の学習完了後に、新しく「再テスト」を挿入し、全問正解できるまで学習セッションへ戻す。
4. 学習セッション内の「概念理解フェーズ2」は暫定的に参加者フローから外す。
5. 事後アンケートは削除し、最終テスト後に実験終了とする。

## 0. 研究者回答反映後の確定方針

研究者回答Q1〜Q39を反映し、本設計では次を確定方針とする。

| 領域 | 確定方針 |
|---|---|
| URL | `/initial-test`, `/retest`, `/final-test` に完全変更 |
| DB phase名 | `initial_test`, `retest`, `final_test` に全面移行 |
| CSV・研究資料列名 | 新名称へ完全置換 |
| 再テスト出題範囲 | 毎回全5概念 |
| 再テスト分岐 | 1問でも不正解なら学習へ戻す |
| 再テスト上限 | 上限なし |
| 再学習対象 | M1/M2/M3/unknownの概念 |
| 再テスト正解概念 | 次ループの学習対象から外す |
| 全問正解条件 | その回の再テスト全5問が正解 |
| 再学習 | 不正解概念で前提用語全件と概念フェーズ1を再実施 |
| 再学習セッション | 新しい `LearningSession` を作成 |
| 概念フェーズ2 | 暫定的に非表示・非使用。YAML/DBは残すがactiveフローから外す |
| テスト形式 | 初期・再・最終すべて全5概念・5択 |
| 問題作成 | 再テスト・最終テストともCodexが作成 |
| M分類 | 初期・再・最終でM1/M2/M3対応を維持 |
| unknown | 全テスト全問に入れる |
| 再テスト後表示 | 正誤を表示せず自動分岐 |
| 最終テスト後 | 不正解があっても終了。得点表示なし |
| 事後アンケート | 削除 |
| 事前アンケート・L0・転移 | 実施しない |
| 主評価 | 初期テストから再テストへの伸び |
| 再テスト | 到達判定・学習ループ制御を主とし、分析指標にも使う |
| ループ回数 | 主要な補助指標にする |
| Mタイプ変化 | 初期→最終、再テスト誤答推移とも分析 |
| 統制群 | 再テスト不正解なら学習へ戻すが、過去ログは教材生成に使わない |
| 提案群 | 再テスト誤答Mタイプも次教材生成に使う |
| 中断再開 | 途中状態を復元 |
| 問題版 | 参加者開始時点の版を維持 |

未回答のまま残るのは、Q40「この新設計を次の実装対象としてdocs更新から着手してよいか」のみである。本ファイル更新時点では、リポジトリへの実装変更は行っていない。

## 2. 現行実装の確認結果

### 2.1 現行docs上のフロー

現行docsでは、実験フローは次のように定義されている。

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

根拠ファイル:

- `/Users/hiroki/ai_tutor_codex_spec/docs/00_project_summary.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/02_experiment_flow.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/09_frontend_ux_flow.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/19_experiment_operation_runbook.md`

### 2.2 現行API上のフロー

現行APIでは、テスト系フェーズは主に次の2つである。

| 現行API | 現行UI名 | 現行phase | 現行の意味 |
|---|---|---|---|
| `GET /api/experiment/{participant_id}/pretest` | 事前テスト | `pretest` | 学習前に5概念を測り、学習対象を決める |
| `GET /api/experiment/{participant_id}/retest` | 即時再テスト | `retest` | 学習後に全5概念を測り、事後アンケートへ進む |

`POST /api/participants/{participant_id}/score-retest` は `score_phase(..., "retest")` を呼び、採点後に `participant.current_step = "post_survey"` へ更新する。

根拠ファイル:

- `/Users/hiroki/ai_tutor_codex_spec/backend/app/main.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/services/experiment.py`

### 2.3 現行フロントエンド上の導線

現行の参加者導線は次のとおりである。

```text
/start
  -> /pretest
  -> /diagnosing
  -> /learning-targets
  -> /learning/[termSlug] ...
  -> /retest
  -> /survey/post
  -> /finish
```

根拠ファイル:

- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/pretest/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/diagnosing/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/learning-targets/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/learning/[termSlug]/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/retest/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/components/QuestionRunner.tsx`

### 2.4 現行コンテンツ管理

現行の実験コンテンツは `experiment_content/` のYAMLで管理される。

```text
experiment_content/
  manifest.yaml
  pretest/pretest_v2.yaml
  retest/retest_v2.yaml
  terms/
    transformer.yaml
    attention.yaml
    llm_training_process.yaml
    pretraining.yaml
    post_training.yaml
```

現行のactive releaseは `experiment_content_v1`、検証状態は `provisional` である。

現行YAML構成の確認結果:

| 項目 | 現行値 |
|---|---|
| content release | `experiment_content_v1` |
| 初期テスト相当 | `pretest_v2`, 5問 |
| 現行retest | `retest_v2`, 5問 |
| 対象概念 | 5概念 |
| 各概念の固定前提用語 | 5件 |
| 各概念の学習問題 | 51問 |
| 全概念の学習問題 | 255問 |

学習問題51問の内訳:

```text
前提用語: 5用語 × 2スロット × 3試行 = 30問
概念フェーズ1: 2スロット × 3試行 × 3サイクル = 18問
概念フェーズ2: 3試行 = 3問
合計: 51問 / 概念
```

根拠ファイル:

- `/Users/hiroki/ai_tutor_codex_spec/experiment_content/manifest.yaml`
- `/Users/hiroki/ai_tutor_codex_spec/experiment_content/pretest/pretest_v2.yaml`
- `/Users/hiroki/ai_tutor_codex_spec/experiment_content/retest/retest_v2.yaml`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/content.py`

### 2.5 現行学習セッション

現行の固定選択式学習セッションは `backend/app/services/fixed_learning.py` に実装されている。

状態遷移は次のとおりである。

```text
prerequisite
  -> prerequisite_review
  -> concept_phase1
  -> concept_phase2
  -> completed
```

実際には `prerequisite_review` は提案群の概念フェーズ1誤答時に挿入されるレビュー状態であり、常に通る通常フェーズではない。

現行の通常進行は次のとおりである。

```text
固定前提用語フェーズ
  -> 概念フェーズ1
  -> 概念フェーズ2
  -> セッション完了
```

### 2.6 現行学習対象選定

現行の学習対象選定は `diagnose_pretest()` で行われる。

初期テスト相当の `pretest` で選んだ選択肢から、次のように診断する。

| 選択結果 | diagnosed_status | 学習対象 |
|---|---|---|
| correct | `stable_correct` | 対象外 |
| M1 | `misconception` | 対象 |
| M2 | `misconception` | 対象 |
| M3 | `misconception` | 対象 |
| unknown | `unknown` | 対象 |

`TermAssignment.is_learning_target` は、`diagnosed_status != "stable_correct"` の場合に `true` になる。

根拠ファイル:

- `/Users/hiroki/ai_tutor_codex_spec/backend/app/services/experiment.py`

## 3. 用語整理

### 3.1 新しいフェーズ名称

今後は、参加者向け・研究者向けの用語を次のように整理する。

| 旧名称 | 新名称 | 内部phase候補 | 役割 |
|---|---|---|---|
| 事前テスト | 初期テスト | `initial_test` | 学習前の5概念診断と初回学習対象選定 |
| 再テスト | 最終テスト | `final_test` | 実験の最後に行う全5概念の最終測定 |
| 新設 | 再テスト | `retest` | 学習セッション後に全問正解を確認し、不正解なら学習へ戻す |

### 3.2 内部phase名

研究者回答により、内部DBのphase名も全面的に新名称へ移行する。

| 参加者向け名称 | 研究上の意味 | 内部phase名 | URL |
|---|---|---|---|
| 初期テスト | 学習前診断 | `initial_test` | `/initial-test` |
| 再テスト | 学習後ループ判定 | `retest` | `/retest` |
| 最終テスト | 最終測定 | `final_test` | `/final-test` |

既存の `pretest` phaseは新規フローでは使用しない。既存データの参照が必要な場合は、移行スクリプトまたは旧CSVの保管によって対応する。

## 4. 新しい全体実験フロー

今回の希望を反映した新フローは次のとおりである。

```text
Start
  -> Participant Registration
  -> 初期テスト
       - 全5概念
       - 選択式のみ
       - 正誤・ヒント・解説なし
  -> 初期診断
       - correctは学習対象外
       - M1/M2/M3/unknownは学習対象
  -> 学習対象一覧
  -> 学習セッション
       1. 固定前提用語フェーズ
       2. 概念理解フェーズ1
       ※ 概念理解フェーズ2は暫定的に実施しない
  -> 再テスト
       - 初期テストと同じ5概念
       - 初期テストと同じ構成概念・同じM設計
       - 表現だけ変えた別問題
       - 全問正解なら最終テストへ
       - 1問でも不正解なら、該当概念を学習対象にして学習セッションへ戻る
  -> 学習セッション再実施
       - 再テストで不正解だった概念のみ
       - 必要に応じて複数ループ
  -> 再テスト再実施
       - 全問正解まで繰り返す
  -> 最終テスト
       - 全5概念
       - 正誤・ヒント・解説なし
       - 実験の最終評価
  -> Finish
```

## 5. 新しいフローの意味づけ

### 5.1 初期テスト

初期テストは、旧「事前テスト」に相当する学習前診断フェーズである。新規実装ではURLを `/initial-test`、内部phaseを `initial_test` とする。

目的:

- 学習前の理解状態を測る。
- 学習対象概念を選定する。
- 提案群の教材生成で使う初期Mタイプを得る。

出題範囲:

- Transformer
- Attention
- LLMの学習段階
- 事前学習
- 事後学習

出題形式:

- 5択
- correct/M1/M2/M3/unknown
- 理由欄なし
- 自信度なし
- 正誤表示なし
- ヒントなし

現行実装との対応:

- 現行 `/pretest` は `/initial-test` へ置き換える。
- 現行 `pretest` phaseは `initial_test` へ置き換える。
- 現行 `pretest_v2` は `initial_test_v1` へ移行する。
- CSV・研究資料も `pretest_*` ではなく `initial_test_*` へ置換する。

### 5.2 初期診断

初期診断は現行 `diagnose_pretest()` の考え方を維持しつつ、名称を `diagnose_initial_test()` に変更する。

| 初期テスト結果 | 学習対象 |
|---|---|
| correct | 対象外 |
| M1 | 対象 |
| M2 | 対象 |
| M3 | 対象 |
| unknown | 対象 |

全問正解の場合は、学習対象は0件になる。この場合でも、今回の新設計では再テストループの前に学習セッションをスキップし、再テストへ進む。

### 5.3 学習セッション

学習セッションは、暫定的に2段階構成とする。

```text
固定前提用語フェーズ
  -> 概念理解フェーズ1
  -> セッション完了
```

今回外すもの:

- 概念理解フェーズ2
- 教材なし概念弁別確認
- フェーズ2誤答後のフェーズ1復帰
- フェーズ2関連評価指標

残すもの:

- 固定前提用語
- 固定5択問題
- AI教材生成
- AI誤答説明
- AI正答要点
- 提案群だけの初期診断・累積ログ適応
- 統制群との情報分離
- 3回誤答時の強制解決
- 提案群の概念フェーズ1誤答時の前提用語レビュー

### 5.4 再テスト

新しく挿入する「再テスト」は、現行の「retest_v2」とは意味が異なる。

目的:

- 学習対象だった概念だけでなく、全5概念について、学習後に正しく弁別できるかを確認する。
- 1問でも不正解なら、該当概念を再度学習対象にして学習セッションへ戻す。
- 全5問正解できるまで、学習と再テストをループさせる。

出題範囲:

- 全5概念

問題設計:

- 初期テストと同じ構成概念を測る。
- correct/M1/M2/M3/unknownの5択。
- 初期テストと同じ正答概念・同じ誤概念タイプ対応を保つ。
- 問題文と選択肢表現は変える。
- 初期テストと同じ文章は使わない。
- 覚えているから解ける状態を避けるため、文脈、言い換え、具体場面、比較対象を変える。

再テストの採点後分岐:

| 再テスト結果 | 次の遷移 |
|---|---|
| 全5問正解 | 最終テストへ進む |
| 1問以上不正解 | 不正解概念を学習対象として学習セッションへ戻る |

学習へ戻す対象:

- 再テストでM1/M2/M3/unknownを選んだ概念のみ
- 再テストで正解した概念は、そのループでは学習対象外

### 5.5 再学習セッション

再テストで不正解だった概念について、学習セッションを再実施する。

再学習時の確定設計:

1. 既存学習セッションを再利用せず、新しい `LearningSession` を作る。
2. `session_index` を増やし、同一概念の何回目の学習かを保存する。
3. 提案群では、初期テストの診断だけでなく、再テストの誤答Mタイプと過去学習ログも教材生成に渡す。
4. 統制群では、再テスト誤答をログとして保存しても、教材生成には累積ログとして使わない。ただし、現在の再学習対象概念であることは通常フロー上の情報として使う。

- 再学習は新しいセッションとして作成する。
- `learning_sessions.session_index` を同一participant・term内で増やす。
- `learning_cycle_index` または `retest_cycle_index` を追加して、どの再テスト後の再学習かを識別する。

### 5.6 最終テスト

最終テストは、現行の「再テスト」に相当する最後の測定フェーズである。

目的:

- 再テストループで全問正解に到達した後、別表現の問題で最終的な理解を測る。
- 学習ループに使った再テスト問題とは別の問題を用い、過学習や短期記憶の影響を減らす。

出題範囲:

- 全5概念

出題形式:

- 5択
- correct/M1/M2/M3/unknown
- 理由欄なし
- 自信度なし
- 正誤・ヒント・解説なし

採点後:

- 正誤・得点・解説は参加者へ表示しない。
- 不正解があっても学習へ戻さず、実験終了とする。
- `participant.current_step = "finish"` へ進める。
- 事後アンケートは実施しない。
- 最終テストは、主評価そのものではなく、到達後の保持・汎化確認として分析する。
- 主評価は、初期テストから再テストへの伸びとする。

## 6. 概念理解フェーズ2を外す場合の設計整理

### 6.1 外す理由

研究者が、概念理解フェーズ2を学習セッションに含めるか検討中であるため、現時点では参加者フローから暫定的に除外する。完全削除ではなく、YAML・DB・既存互換列は残し、activeな参加者フローから外す。

### 6.2 現行フェーズ2の役割

現行フェーズ2は「教材なしで正しい概念を選べるか」を測るための学習内フェーズである。

現行の関連指標:

- `concept_phase2_success_rate`
- `no_material_concept_discrimination_accuracy`
- `phase2_after_retry_success_rate`
- `phase2_max_retry_rate`
- `phase2_forced_completion_rate`
- `phase2_pass_retest_correct_rate`
- `phase2_fail_retest_correct_rate`
- `phase2_misconception_recurrence_rate`

### 6.3 フェーズ2非使用後の代替

フェーズ2を外す場合、「教材なしで正しい概念を選べるか」は学習内ではなく、再テストと最終テストで測る。

対応関係:

| 現行 | 新設計 |
|---|---|
| 概念フェーズ2 | 暫定的に非表示・非使用 |
| 教材なし概念弁別正答率 | 再テスト正答率・最終テスト正答率に統合 |
| フェーズ2失敗後のフェーズ1復帰 | 再テスト不正解後の学習セッション復帰へ移行 |

フェーズ2関連のCSV互換列は残す。ただし新分析では主指標として使わず、値はnullまたは非使用扱いにする。

### 6.4 学習セッション完了条件

フェーズ2削除後は、各学習対象概念のセッション完了条件を次のようにする。

```text
固定前提用語フェーズが完了
  かつ
概念フェーズ1の全必須スロットが passed または forced_resolved
  -> learning_session.status = completed
```

現行実装では、概念フェーズ1完了後に必ず `concept_phase2` へ進むため、実装時には `fixed_learning.py` の `_advance_after_completed_slot(..., stage="concept_phase1")` の遷移を変更する必要がある。

## 7. 新設計のデータモデル方針

### 7.1 既存テーブルを活かすもの

既存の次のテーブルはそのまま使える。

- `participants`
- `terms`
- `content_versions`
- `term_assignments`
- `questions`
- `question_options`
- `question_display_orders`
- `attempts`
- `learner_states`
- `learning_sessions`
- `learning_session_prerequisites`
- `learning_question_slots`
- `learning_questions`
- `learning_question_options`
- `learning_question_display_orders`
- `learning_choice_attempts`
- `generated_learning_materials`
- `misconception_observations`
- `ai_call_logs`
- `evaluation_summaries`

### 7.2 追加する概念

再テストループを正確に保存するため、既存の `attempts` に加えて、再テストループ専用テーブルを追加する。

例:

```text
retest_cycles
  id
  participant_id
  cycle_index
  status
  all_correct
  started_at
  completed_at

retest_cycle_results
  id
  retest_cycle_id
  term_id
  attempt_id
  is_correct
  misconception_type
  becomes_learning_target
```

メリット:

- ループ構造が分析しやすい。
- 何回目の再テストでどの概念が残ったかを明確に追える。
- 回答本体は既存 `attempts` に保存し、cycleテーブルは構造化された紐づけにする。
- 毎回全5概念を出題し、その回の5問がすべて正解なら `retest_cycles.all_correct = true` とする。
- 1問でも不正解なら `retest_cycles.status = "needs_relearning"` とし、不正解概念だけを次の学習対象にする。

### 7.3 学習セッションへの追加列

再学習セッションを扱うため、`learning_sessions` に次を追加するとよい。

```text
learning_cycle_index
triggered_by_phase
triggered_by_retest_cycle_id
is_relearning_session
```

意味:

| 列 | 意味 |
|---|---|
| `learning_cycle_index` | 初期診断後の学習を1、再テスト1回目後の再学習を2、という形で保存 |
| `triggered_by_phase` | `initial_test` / `retest` など |
| `triggered_by_retest_cycle_id` | どの再テストサイクルがこの学習を発生させたか |
| `is_relearning_session` | 初回学習か再学習か |

## 8. YAMLコンテンツ設計

### 8.1 現行YAML

現行は次の2種類のテストYAMLを持つ。

```text
pretest/pretest_v2.yaml
retest/retest_v2.yaml
```

### 8.2 新設計で必要なYAML

新設計では、最低3種類のテストYAMLが必要である。

```text
experiment_content/
  initial_test/initial_test_v1.yaml
  retest/retest_v1.yaml
  final_test/final_test_v1.yaml
```

`manifest.yaml` は次のような構造へ変更する。

```text
initial_test_file: initial_test/initial_test_v1.yaml
retest_file: retest/retest_v1.yaml
final_test_file: final_test/final_test_v1.yaml
```

現行の `pretest/pretest_v2.yaml` と `retest/retest_v2.yaml` は、新規フローではactiveコンテンツとしては使わない。必要であれば旧版として非active保持する。

### 8.3 再テスト問題の設計

再テストは、初期テストと同じ概念を測るが、表現を変える。

例:

| 初期テスト | 再テスト |
|---|---|
| Transformerの計算構造を最も適切に説明しているものはどれか。 | Transformerの構造を別のモデル構造と区別して説明したものとして、最も適切なものはどれか。 |
| LLMの事前学習を最も適切に説明しているものはどれか。 | 事前学習でモデルが獲得する能力として、最も適切なものはどれか。 |

設計条件:

- 初期テストと同じ正答概念を測る。
- 初期テストと同じM1/M2/M3の誤概念対応を持つ。
- 選択肢本文は丸暗記で対応できないように言い換える。
- 正答文も完全一致させない。
- unknownは全問に入れる。

### 8.4 最終テスト問題の設計

最終テストは、再テストループで全問正解できた後の最終評価なので、再テストとも別表現にする。

設計条件:

- 全5概念を出題する。
- 初期テスト、再テストと同じ構成概念を測る。
- ただし、問題文・選択肢表現は別にする。
- Mタイプ推移を分析できるよう、M1/M2/M3の意味対応は維持する。

## 9. バックエンドAPI設計案

### 9.1 名称変更後のAPI

新規参加者フローでは、次のAPIを正式に使う。

```text
GET  /api/experiment/{participant_id}/initial-test
POST /api/participants/{participant_id}/diagnose-initial-test

GET  /api/experiment/{participant_id}/retest
POST /api/participants/{participant_id}/score-retest

GET  /api/experiment/{participant_id}/final-test
POST /api/participants/{participant_id}/score-final-test
```

既存 `/pretest` APIや `pretest` phaseは新規フローでは使用しない。必要であれば旧データ参照・移行専用として別途保持する。

### 9.2 再テスト採点APIの挙動

`score-retest` は、最終テストへ進むか学習へ戻るかを決める。

擬似仕様:

```text
POST /api/participants/{participant_id}/score-retest
  1. retest phaseのattemptを採点する
  2. 全5問の正誤を確認する
  3. 全問正解なら
       participant.current_step = "final_test"
       next_step = "final_test"
       next_url = "/final-test"
  4. 不正解が1問以上なら
       不正解termだけ TermAssignment.is_learning_target = true
       正解termは今回ループの学習対象から外す
       participant.current_step = "learning_targets"
       next_step = "learning_targets"
       next_url = "/learning-targets"
       retest_cycle.status = "needs_relearning"
```

### 9.3 最終テスト採点APIの挙動

`score-final-test` は、採点後に実験終了へ進める。

```text
POST /api/participants/{participant_id}/score-final-test
  1. final_test phaseのattemptを採点する
  2. final_testのMタイプ・正答率を保存する
  3. participant.current_step = "finish"
  4. completed_at を保存する
  5. next_url = "/finish"
```

### 9.4 current-stepの更新

現行 `current_step` は次を持つ。

```text
pretest
learning_targets
retest
post_survey
finish
```

新設計では次を持つのが自然である。

```text
initial_test
learning_targets
retest
final_test
finish
```

## 10. フロントエンド設計案

### 10.1 新しい参加者導線

```text
/start
  -> /initial-test
  -> /diagnosing
  -> /learning-targets
  -> /learning/[termSlug] ...
  -> /retest
  -> /learning-targets  # 不正解があった場合
  -> /retest            # 再学習後
  -> /final-test        # 再テスト全問正解後
  -> /finish
```

### 10.2 `/initial-test`

表示名:

```text
初期テスト
```

画面説明:

- 学習前の理解を確認する。
- 正誤やヒントは表示しない。

### 10.3 `/retest`

表示名:

```text
再テスト
```

画面説明:

- 学習後にもう一度理解を確認する。
- 全問正解できたら最終テストへ進む。
- 正誤やヒントは表示しない。

注意:

- 参加者に「不正解があれば戻る」と明示するかは研究上の反応に影響する可能性があるため、画面文言は慎重に決める。
- 最低限、「このフェーズでは正誤やヒントは表示されません」という現行文言は維持できる。

### 10.4 `/final-test`

表示名:

```text
最終テスト
```

画面説明:

- 最後に理解を確認する。
- 正誤やヒントは表示しない。

完了後:

- 正誤・得点を表示せず `/finish` へ遷移する。

### 10.5 `/learning/[termSlug]`

フェーズ2削除により、学習画面で次を表示しない。

- `教材なし確認`
- `概念フェーズ2 教材なし`
- フェーズ2のサイクル表示

`stageTitle()` は次の2段階を中心にする。

```text
前提用語
概念フェーズ1 教材あり
```

## 11. 評価指標の再整理

### 11.1 名称変更

CSV・研究資料の列名は、旧名称を残さず新名称へ置換する。

| 旧指標 | 新指標 |
|---|---|
| `pretest_score_all_terms` | `initial_test_score_all_terms` |
| 旧 `retest_score_all_terms` | `final_test_score_all_terms` |
| 旧 `learning_target_retest_score` | `learning_target_final_test_score` |
| 旧 `non_target_retest_retention_rate` | `non_target_final_test_retention_rate` |
| `same_misconception_recurrence_rate` | `initial_to_retest_same_m_rate` と `initial_to_final_same_m_rate` に分離 |

主評価は、初期テストから再テストへの伸びとする。再テストは全問正解まで繰り返すため、主評価では「1回目の再テスト」を中心に扱うのが最も解釈しやすい。最終的に全問正解した再テストは到達判定として扱う。

主評価候補:

```text
initial_to_first_retest_gain =
  first_retest_score_all_terms - initial_test_score_all_terms
```

補助的に、最終テストは再テスト到達後の保持・別表現への対応を確認する指標として扱う。

### 11.2 新しく追加したい指標

再テストループを入れる場合、次の指標が重要になる。

| 指標名候補 | 意味 |
|---|---|
| `retest_loop_count` | 最終テスト到達までに必要だった再テスト回数 |
| `retest_first_pass_rate` | 1回目の再テストで全問正解した割合 |
| `retest_relearning_trigger_count` | 再テスト不正解で再学習に戻った回数 |
| `retest_to_relearning_target_count` | 再テストごとの再学習対象概念数 |
| `retest_loop_mastery_rate` | 再テストで全問正解に到達した割合 |
| `retest_error_resolution_rate` | ある再テストで誤答した概念が次回再テストで正答になった割合 |
| `initial_to_retest_same_m_rate` | 初期テストと再テストで同じM誤答を選んだ割合 |
| `retest_to_final_same_m_rate` | 再テストと最終テストで同じM誤答を選んだ割合 |
| `final_test_score_all_terms` | 再テスト全問正解後の最終テスト正答率 |

### 11.3 削除または非主指標化するもの

概念フェーズ2を暫定削除するため、次は主評価から外す。

- `concept_phase2_success_rate`
- `no_material_concept_discrimination_accuracy`
- `phase2_after_retry_success_rate`
- `phase2_max_retry_rate`
- `phase2_forced_completion_rate`
- `phase2_pass_retest_correct_rate`
- `phase2_fail_retest_correct_rate`
- `phase2_misconception_recurrence_rate`

既存DB列は互換性のため残してよいが、新規分析ではnullまたは非使用扱いにする。

## 12. 提案群・統制群の情報分離

今回の設計変更後も、研究上の重要な比較条件は維持する。

### 12.1 両群共通

- 初期テスト問題
- 再テスト問題
- 最終テスト問題
- 固定前提用語
- 学習セッション内の固定問題
- 正誤判定規則
- 強制解決規則
- 再テストで不正解なら学習へ戻る規則

### 12.2 提案群だけが使う情報

- 初期テストのMタイプ
- 再テストのMタイプ
- 再テストで選択した誤答選択肢
- 再テストから再学習へ戻った回数
- 学習中の累積Mタイプ
- 学習履歴
- 前提用語レビュー履歴
- 再学習ループ履歴

### 12.3 統制群が使わない情報

統制群では、次を教材生成payloadに含めない。

- 初期テスト診断
- 再テスト誤答履歴
- 累積学習ログ
- Mタイプ推移
- 過去の教材履歴
- 提案群的な戻り履歴

ただし、統制群も実験フロー上は再テスト不正解なら学習へ戻る。これは教授方略の個別化ではなく、実験手順として両群に共通に適用する。

## 13. 実装時の主な変更対象

この文書ではリポジトリを編集していないが、実装する場合の変更対象は次のとおりである。

### 13.1 docs

更新対象:

- `/Users/hiroki/ai_tutor_codex_spec/docs/00_project_summary.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/02_experiment_flow.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/04_scaffolding_and_tutoring.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/07_data_model.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/08_backend_api_spec.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/09_frontend_ux_flow.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/10_ai_prompt_contracts.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/11_seed_questions.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/12_evaluation_metrics.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/14_testing_acceptance.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/16_implementation_tasks.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/17_traceability_matrix.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/18_implementation_blueprint.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/19_experiment_operation_runbook.md`
- `/Users/hiroki/ai_tutor_codex_spec/docs/99_sources_and_notes.md`

### 13.2 コンテンツYAML

追加または変更:

- `experiment_content/manifest.yaml`
- `experiment_content/initial_test/initial_test_v1.yaml`
- `experiment_content/retest/retest_v1.yaml`
- `experiment_content/final_test/final_test_v1.yaml`

既存 `pretest_v2` と `retest_v2` は新規フローではactive利用しない。必要であれば旧版として非active保持する。

### 13.3 バックエンド

変更対象:

- `/Users/hiroki/ai_tutor_codex_spec/backend/app/content.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/models/__init__.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/db/session.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/services/experiment.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/services/fixed_learning.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/app/main.py`
- `/Users/hiroki/ai_tutor_codex_spec/backend/tests/test_experiment_flow.py`

主な変更:

- `pretest` から `initial_test` への全面移行
- `retest` phaseを学習ループ判定として再定義
- 最終テストphase追加
- 再テスト全問正解判定
- 再テスト不正解概念の再学習対象化
- 同一概念の再学習セッション作成
- 概念フェーズ2の参加者フロー除外
- フェーズ2関連指標の非主指標化

### 13.4 フロントエンド

変更対象:

- 新規 `/Users/hiroki/ai_tutor_codex_spec/frontend/app/initial-test/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/retest/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/learning-targets/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/app/learning/[termSlug]/page.tsx`
- 新規 `/Users/hiroki/ai_tutor_codex_spec/frontend/app/final-test/page.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/components/QuestionRunner.tsx`
- `/Users/hiroki/ai_tutor_codex_spec/frontend/tests/smoke.mjs`

主な変更:

- `/pretest` を廃止し、`/initial-test` を正式導線にする
- 「即時再テスト」ではなく「再テスト」と表示する
- `/retest` 完了後の遷移をbackend応答に従って分岐
- `/final-test` 追加
- 学習画面から概念フェーズ2表示を削除
- 学習完了後の次遷移を再テストへ維持

## 14. 推奨する実装順序

実装する場合は、次の順序が安全である。

1. docsを新用語と新フローへ更新する。
2. YAML manifestを `initial_test`, `retest`, `final_test` の3テスト構成へ変更する。
3. `content.py` のTestFile読み込みを3種類以上のテストphaseに対応させる。
4. DBに `retest_cycles` と `retest_cycle_results` を追加する。
5. `question_payloads()` が `initial_test`, `retest`, `final_test` を返せるようにする。
6. 初期診断を `diagnose_initial_test()` として実装する。
7. `score-retest` をループ判定用に変更する。
8. `score-final-test` を追加する。
9. `fixed_learning.py` で概念フェーズ2へ進まず、概念フェーズ1完了でセッション完了にする。
10. フロントに `/initial-test` と `/final-test` を追加し、`/retest` の遷移を分岐させる。
11. 評価指標とCSVを新名称に対応させる。
12. テストを更新し、ブラウザで両群のループを確認する。

## 15. 回答反映後の確定事項と残論点

研究者回答により、実験設計上の主要論点は次のように確定した。

- 再テストは毎回全5概念を出し、その回の全5問正解で最終テストへ進む。
- 再テストで1問でも不正解なら、不正解概念だけを学習対象にして学習へ戻す。
- 再テストループに上限は設けない。
- 再学習では、不正解概念について前提用語フェーズ全件と概念フェーズ1を再実施する。
- 再学習は新しい `LearningSession` として保存する。
- 再学習問題は未使用バリアントを優先し、不足時は現行どおりAI緊急問題生成を使う。
- 概念フェーズ2は暫定的に非表示・非使用にするが、YAML・DB・互換CSV列は残す。
- 初期テスト、再テスト、最終テストはすべて全5概念・5択で統一する。
- 再テスト・最終テスト問題はCodexが作成する。
- 最終テストで不正解があっても実験終了とする。
- 事後アンケートは削除する。
- 主評価は初期テストから再テストへの伸びとする。

唯一残る運用上の未回答事項は、Q40「この新設計を次の実装対象としてdocs更新から着手してよいか」である。

## 16. 新フロー要約

新しい研究フローは、次の設計として整理できる。

```text
初期テスト
  -> 初期診断
  -> 不正解概念を学習対象化
  -> 学習セッション
       - 固定前提用語
       - 概念フェーズ1
       - 概念フェーズ2は暫定除外
  -> 再テスト
       - 全5概念
       - 初期テストと同じ構成を別表現で測る
       - 全問正解できなければ不正解概念の学習へ戻る
  -> 再テスト全問正解
  -> 最終テスト
       - 全5概念
       - 最終評価
  -> 終了
```

この設計により、現行の「学習後に一度だけretestして終了する」構造から、「再テストで全問正解到達を確認し、不正解概念を再学習させたうえで、別問題の最終テストを受けて終了する」構造へ変わる。

また、概念フェーズ2の役割は一時的に学習セッション外へ移され、教材なし弁別は再テストと最終テストで測定する。
