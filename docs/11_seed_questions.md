# Seed Questions

テスト問題と学習確認v1の正本は `backend/app/seed/content/learning_content.yml`、新規参加者向けの学習確認v2は `backend/app/seed/content/learning_questions_v2.yml` である。

`backend/app/seed/content_loader.py` が起動・seed時に形式を検証し、`backend/app/seed/seed_questions.py` がDBへ投入する。

## Active topics

| slug | label | RAG section |
|---|---|---|
| `llm_knowledge` | LLMに知識を与える方法 | 第3章「LLMに知識を与える」 |
| `multi_agent` | マルチエージェント | 第4章「マルチエージェントとは」 |
| `memory_process` | 記憶プロセス | 第5章「記憶プロセス」 |

LangGraphを含む見出し・セクションのチャンクは検索結果から除外する。

## 固定問題の構成

pretest、retest、final_testと学習確認の固定複数選択問題はA〜Jの10選択肢を持つ。実験用の基準ではテスト系のA〜Iの役割をvariantごとに分散し、学習確認v2も同様にvariantごとに循環させる。学習確認v1は既存参加者との互換性のためA〜Cが正解、D〜FがM1、G〜IがM3の固定配置を維持する。`l0_check`の自由回答と`transfer`の互換問題は別形式である。

`fix/issue-124`では開発者の判定確認用に、テスト系および学習確認v2の役割をA〜C=正解、D〜F=M1、G〜I=M3、J=unknownへ一時固定する。これは実験用の基準ではなく、正解ラベルを手掛かりにできるため、このブランチで参加者データを収集してはならない。実験開始前にvariant別の分散配置へ戻し、分布検査を復旧する。

- テスト系: 各variantの3選択肢に`is_correct: true`を設定し、残り6選択肢にM1/M3を3つずつ設定（`fix/issue-124`のデバッグ上書き中はA〜Cが正解、D〜FがM1、G〜IがM3）
- 学習確認v1のA〜C: `is_correct: true`
- 学習確認v1のD〜F: `misconception_type: M1`
- 学習確認v1のG〜I: `misconception_type: M3`
- 学習確認v2: 実験用の基準ではvariant別に役割を分散（デバッグ上書き中はA〜Cが正解、D〜FがM1、G〜IがM3）
- J: `misconception_type: unknown`

正解はvariantごとの正解metadataを持つ3選択肢だけをすべて選んだ場合に限定し、Jは単独選択だけを有効とする。テスト系は各用語につきpretest 1種類、retest 5種類、final_test 1種類の全21variantを持ち、再テスト6回目以降はv5を再利用する。実験用の基準では全21問を通じてA〜Iの各ラベルを正解・M1・M3に各7回割り当てる。各問題はシナリオと判断タスクを持ち、選択肢本文は教材や他variantから流用しない。M1誤答は単一命題の誤り、M3誤答は概念カテゴリーの取り違えとして設計する。Jは全問「わからない」。YAMLローダーはvariant数、場面・タスク、役割配分、重複、文字数差、LangGraph混入を検証する。M1/M3のテスト系選択肢には、`teaching_targets`として研究者確認済みの`corrected_claim`、`mechanism_explanation`、`contrast_example`を置き、M3には`wrong_category`、`correct_category`、`boundary_criterion`も置く。選択肢本文は既存の`QuestionOption.body`を正本とし、claim IDは`{term_slug}:pretest:{option_label}`から実行時に作る。

`teaching_targets`は採点用データではない。`Attempt.is_correct`、`diagnosed_status`、`misconception_type`を変更せず、提案群の教材生成payloadを具体化するためだけに使う。J「わからない」には誤った主張のtargetを作らず、unknownの基礎説明へ分岐する。

## Variant policy

| phase | 用語ごとの定義 |
|---|---|
| `pretest` | 1問（`pretest_v1`） |
| `retest` | 5問（`retest_v1`〜`retest_v5`）、6回目以降はv5再利用 |
| learning confirmation | `enrichment` / `conceptual_change`の各stageで5問（v1〜v5）、6回目以降はv5再利用 |
| `final_test` | 1問（`final_test_v1`） |

学習確認問題はDBの`questions`へseedしない。`generate_tutor_turn`が参加者に固定した版のYAML stage・用語別定義から問題・選択肢を組み立て、AI生成教材とともに`tutor_turns.practice_question_json`へ保存する。新規参加者は作成時にv2、版未記録を含む既存参加者はv1を使う。各turnの`diagnosis_json.learning_content_version`に実際の版を保存し、回答時も同じ版から選択肢を再構成して採点する。L3/L2は問題stageではなく、内部の`scaffolding_level`互換値である。

学習確認のvariantは、学習セッション内で新しく取得した教材の順に`v1`、`v2`、`v3`を使う。誤答後に`learning_stage`が変わってもこの順序をリセットしない。現行の標準フローでは1用語あたり3回目の不正解で次の学習対象へ進むため、`v4`、`v5`は将来の上限設定や既存ログ互換のために保持する。現在の問題への回答結果表示は新しい教材取得ではないため、画面の用語進捗分子を進めない。

v2の`scenario_type`は`application`、`prediction`、`comparison`、`boundary`、`diagnosis`で、各term・stageに1 variantずつ配置する。選択肢の採点役割は文字ラベルに依存せず、内部option metadataの`is_correct`と`misconception_type`を使う。参加者向けAPIは問題文・選択肢・選択数制約だけを返し、正答キーや誤概念メタデータを返さない。既存参加者のv1問題は変更せず、新旧の問題が同一参加者の進行中に混ざらない。

旧Transformerなど既存DB内の問題は削除せず非アクティブ化し、新規seed・新規参加者の導線には含めない。
