# 17. Traceability Matrix

この文書は、研究計画PPTXに含まれていた研究上の主張・設計要素が、どの仕様書・実装要素へ落ちているかを示す。

## Research Plan to Spec

| PPTX上の要点 | 仕様への反映 | 実装要素 |
|---|---|---|
| 専門用語は「知っているつもり」でも誤って理解する | `00_project_summary.md`, `03_misconception_taxonomy.md` | diagnosis, misconception_type |
| その場の正解だけでは不十分 | `02_experiment_flow.md`, `12_evaluation_metrics.md` | retest, final_test |
| 評価は正答率だけでなく再発と自力解答を見る | `12_evaluation_metrics.md` | evaluation_summaries |
| AIを使うかではなくログで支援を変えるかを比較 | `01_research_requirements.md` | group_condition control/proposed |
| 学習ログは次の支援を決める診断材料 | `05_system_architecture.md`, `07_data_model.md` | learner_states, tutor_turns |
| 誤概念タイプで支援を変える | `03_misconception_taxonomy.md`, `04_scaffolding_and_tutoring.md` | teaching_strategy |
| 足場掛けは支えるだけでなく段階を記録する | `04_scaffolding_and_tutoring.md` | learning_stage, scaffolding_level L3/L2互換ログ |
| 同じ誤概念が再発したら方略変更 | `02_experiment_flow.md`, `04_scaffolding_and_tutoring.md` | recurrence_events, strategy_changed |
| YAMLの問題variantを段階ごとに使う | `11_seed_questions.md` | construct_key, variant_key |
| 遅延再テストも可能 | `02_experiment_flow.md`, `07_data_model.md` | delayed_retest phase |
| ログDBとCSVで分析する | `07_data_model.md`, `12_evaluation_metrics.md` | export endpoints |

## Taxonomy Evolution

5月18日の初期案は、次のように細分化されていた。

- 日常語混同型
- 類似概念混同型
- 因果誤認型
- 定義暗記型
- 適用条件誤解型
- 表層キーワード依存型

現行の研究計画では、先行研究に基づく知識構造の粒度として次の4分類を使う。

- M1: 誤信念型
- M2: 欠陥メンタルモデル型
- M3: カテゴリー錯誤型
- M4: 欠如したスキーマ型
- unknown: 知識不足

固定問題の選択肢はM1/M3/unknownを診断対象とし、M2/M4はAI内部taxonomyとして保持する。taxonomyの実行時定義は `backend/app/ai/misconception_taxonomy.py` にある。

## Research Questions to Data

### RQ1

誤概念タイプに応じて説明を変えると、同じ誤りの再発は減るか。

必要データ:

- pretest misconception_type
- retest misconception_type
- recurrence_flag
- group_condition
- teaching_strategy

主要出力:

- same_misconception_recurrence_rate
- M1〜M4 recurrence rate

### RQ2

足場掛けを段階的に減らすと、足場掛けなしで解けるようになるか。

必要データ:

- scaffolding_level history
- final_test attempts
- l0_check attempts  # 互換・補助
- l0_success
- stable_correct_count

主要出力:

- l0_correct_rate
- scaffolding_reduction

### RQ3

AI・情報系専門用語では、どの誤概念が再発しやすいか。

必要データ:

- term_slug
- misconception_type
- recurrence_flag

主要出力:

- term x misconception_type count
- term x recurrence rate
- unknown persistence rate

## Implementation Traceability

| Research Object | DB Table | Backend Service | Frontend Page |
|---|---|---|---|
| 被験者 | participants | ExperimentService | /start |
| 問題 | questions, question_options | QuestionService | /pretest, /retest |
| 回答 | attempts | ExperimentService | all test pages |
| AI診断 | attempts, ai_call_logs | DiagnosisService | /diagnosing, /admin |
| 学習者状態 | learner_states | LearnerStateService | /learning-targets |
| 学習対話 | tutor_sessions, tutor_turns | TutoringService | /learning/[termSlug] |
| 再発 | recurrence_events | ScaffoldingService | /admin |
| 評価 | evaluation_summaries | EvaluationService | /admin |
| CSV | export_jobs | ExportService | /admin |

## Control vs Proposed Traceability

| Behavior | control | proposed |
|---|---|---|
| AI explanation | general only | misconception-specific |
| Uses pretest log for tutoring | no | yes |
| Uses M type for tutoring | no | yes |
| Dynamic scaffolding | no | yes |
| Strategy changes on recurrence | no | yes |
| Stores diagnosis | yes | yes |
| Stores AI logs | yes | yes |
| Includes in evaluation | yes | yes |

## PPTX Details Captured

- 現行MVPの3用語の問題は `backend/app/seed/content/learning_content.yml` に反映する
- Transformer等の旧用語は過去ログ・DB互換用として非アクティブ化する
- Problem phase separation from 5月25日 slide 22/23 is reflected in `02_experiment_flow.md`
- 問題バリエーションの再利用上限は `construct_key` と `variant_key`、YAMLのvariant定義で管理する
- 教材参照は `rag_agent_knowledge_base` のローカルRAG資産として実装し、用語別sectionとLangGraph除外を適用する
- "足場掛けはどうやってやるのか" is answered in `04_scaffolding_and_tutoring.md`

## Remaining Research Decisions

The following are intentionally left configurable rather than fixed.

- Participant count
- Whether to run delayed retest
- Whether to use between-subject or within-subject design
- Exact statistical test in final thesis
- Whether optional terms Loss, ハルシネーション, 正則化 are included
