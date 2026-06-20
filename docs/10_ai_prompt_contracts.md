# 10. AI Prompt Contracts

AIには必ず構造化出力を要求する。通常実行は `AIBackend` 経由でCodex app-serverへ接続し、テスト時のみ `MockAIBackend` を使う。

## 共通制約

- 出力は指定JSONのみ
- 余計なMarkdownや説明文を返さない
- 被験者に直接見せる文章と内部ラベルを分ける
- M1〜M4を学習者向け文面に出さない
- 事前テストと再テストでは理由欄・自信度欄がない前提で採点する
- テスト問題の正解を直接教えない
- `rag_context` がある場合は教材コンテキストを優先し、教材にない内容を推測で断定しない
- 統制群では誤概念タイプ、事前テスト選択肢、過去ログ、適応的戻り情報を教授に使わない

## Diagnosis

事前テスト診断。選択肢メタデータに基づき、正答なら `stable_correct`、M1〜M3誤答なら `misconception`、わからないなら `unknown` を返す。現行pretestでは理由欄がnullであることを欠損扱いしない。

Result:

```json
{
  "is_correct": true,
  "diagnosed_status": "stable_correct",
  "misconception_type": null,
  "secondary_misconception_type": null,
  "diagnosis_confidence": 0.92,
  "natural_language_diagnosis": "この回答では...",
  "evidence": "...",
  "recommended_initial_scaffolding_level": "L1",
  "recommended_teaching_strategy": "self_explanation_check",
  "requires_manual_review": false
}
```

`recommended_initial_scaffolding_level` と `recommended_teaching_strategy` は旧互換列として返すが、提案群の新学習セッション制御には使わない。

## Proposed: generate_prerequisite_plan

対象概念ごとの前提用語計画を生成する。

Payload:

```json
{
  "participant_id": "uuid",
  "group_condition": "proposed",
  "target_term": {
    "slug": "attention",
    "label": "Attention",
    "description": "..."
  },
  "pretest_diagnosis": {
    "diagnosed_status": "misconception",
    "misconception_type": "M1",
    "natural_language_diagnosis": "..."
  },
  "selected_option_body": "...",
  "selection_reason": "...",
  "rag_context": { "source": "rag_ready_教材", "chunks": [] }
}
```

Result:

```json
{
  "prerequisites": [
    {
      "term_label": "トークン",
      "material": "...",
      "check_question": "...",
      "expected_answer": "...",
      "generation_reason": "対象概念理解に必要な基礎単位だから"
    }
  ],
  "plan_rationale": "..."
}
```

前提用語は実装上ちょうど3件に固定する。

## Control: generate_control_prerequisite_plan

統制群の小問3件を生成する。これは前提用語gateではなく、RAG教材に基づく一般的な確認小問である。

Payloadには以下だけを含める。

- participant_id
- group_condition
- target_term
- rag_context

Payloadに含めない。

- pretest_diagnosis
- selected_option_body
- misconception_type
- learner_state
- previous_learning_logs
- adaptive_return_state

Result:

```json
{
  "prerequisites": [
    {
      "term_label": "確認1",
      "material": "...",
      "check_question": "...",
      "expected_answer": "...",
      "generation_reason": "教材に基づく一般確認"
    }
  ],
  "plan_rationale": "統制群のため個別診断は使わず、対象概念の基本説明を確認する。"
}
```

## Proposed: grade_prerequisite_answer

前提用語理解チェックを採点する。

Result:

```json
{
  "is_passed": true,
  "score": 0.8,
  "diagnosed_status": "resolved",
  "primary_misconception_type": null,
  "secondary_misconception_type": null,
  "diagnosis_confidence": 0.9,
  "diagnosis_evidence": "...",
  "recommended_strategy": "fading",
  "strategy_override": false,
  "strategy_override_reason": null,
  "core_elements_covered": ["..."],
  "major_errors": [],
  "rubric_scores": {}
}
```

pass基準は中程度。中核要素が含まれ、重大な誤りがなければpass。

統制群では誤概念診断を含まない専用採点schemaを使い、failしても次小問へ進む。

## Proposed/Control: generate_concept_phase1_material

前提用語/小問3件の後に、対象概念教材と説明promptを生成する。提案群payloadにはRAG、事前テスト診断、選択誤答、学習ログを含める。統制群payloadにはRAGと対象概念だけを含める。

Result:

```json
{
  "concept_material": "...",
  "concept_prompt": "上の前提用語を使って、Attentionを説明してください。",
  "expected_answer": "..."
}
```

## Proposed/Control: grade_concept_phase1_answer

教材あり概念理解チェックを採点する。提案群では最大3回、統制群では1回だけ採点し、pass/failに関係なくフェーズ2へ進む。

Result:

```json
{
  "is_passed": false,
  "score": 0.45,
  "feedback": "...",
  "missing_prerequisite_labels": ["トークン"],
  "review_prerequisite_labels": ["重み付け"],
  "core_elements_covered": ["..."],
  "major_errors": ["..."]
}
```

提案群のfail時は、不足用語とその直前の関連用語を返す。backendは最大3回の上限を管理する。

## Proposed/Control: generate_concept_phase2_prompt

教材本文なしの確認promptと軽い条件を生成する。提案群ではフェーズ1の成功内容を踏まえてよい。統制群では対象概念とRAGだけを使う。

Result:

```json
{
  "phase2_prompt": "教材を見ずに、...を説明してください。",
  "light_conditions": "前提用語を2つ以上使い、仕組みを中心に説明してください。",
  "expected_answer": "..."
}
```

## Proposed/Control: grade_concept_phase2_answer

教材なし概念説明を採点する。

Result:

```json
{
  "is_passed": false,
  "score": 0.45,
  "feedback": "...",
  "independent_explanation_success": false,
  "return_to_phase1": true,
  "rubric_scores": {
    "core_concept": 0.4,
    "independent_reconstruction": 0.3,
    "condition_following": 0.6,
    "misconception_absence": 0.5
  }
}
```

提案群ではpassなら `completed`、fail 1〜2回目はフェーズ1へ戻り、3回目failで `failed_phase2` にする。統制群では1回だけ採点し、pass/failに関係なく `completed` にする。

提案群のgrade契約は誤概念診断を含む。統制群では診断情報を要求せず、pass/fail、score、一般フィードバック、phase固有情報だけを返す専用schemaを使う。

## Proposed: generate_adaptive_support

確定・保存済みの診断と更新後状態から、次の支援を生成する。

```json
{
  "mode": "remediation",
  "feedback": "...",
  "supplemental_material": "...",
  "next_check_question": "...",
  "diagnostic_focus": {
    "core_elements": [],
    "M1_features": [],
    "M2_features": [],
    "M3_features": [],
    "unknown_criteria": "..."
  },
  "rag_sources": [],
  "general_knowledge_supplement": null
}
```

完成回答は禁止する。RAG教材を優先し、一般知識を補足した場合は区別して返す。

## Legacy Control: generate_control_learning_turn

旧互換API。現行参加者フローでは、統制群も `generate_control_prerequisite_plan` とconcept phase APIを使う。

Payloadには以下だけを含める。

- participant_id
- group_condition
- target_term
- rag_context

Payloadに含めない。

- pretest_diagnosis
- misconception_type
- previous_answer
- learner_state
- prerequisite_terms

Result:

```json
{
  "tutor_message": "...",
  "learner_prompt": "自分の言葉で説明してください。",
  "practice_question": {
    "body": "...",
    "expected_answer": "..."
  },
  "forbidden_help_given": false
}
```

## Control: grade_control_learning_answer

旧互換API。統制群の自己説明に一般的フィードバックを返す。

Result:

```json
{
  "feedback": "...",
  "is_complete": true,
  "forbidden_help_given": false
}
```

## Retest Grading

再テスト採点は `grade_response` を使う。選択肢メタデータに基づき、正答、M1〜M3、unknownを保存する。再発判定はAIではなくbackendが行う。

## MockAIBackend Rules

テスト用に決定論的に実装する。

- correct optionなら `stable_correct`
- known M optionならそのMを返す
- unknown optionなら `unknown`
- 前提用語計画は常に3件返す
- 統制群小問計画も常に3件返す
- 前提用語回答は「pass」「十分」「関係」「重み」「事前」「事後」などの語を含む場合にpassしやすくする
- 2回fail、フェーズ1 3回fail、フェーズ2 3回failの境界をテストできるよう、短い回答はfailにする
- 統制群payloadに誤概念情報が混入した場合はテストで検出する

## Forbidden Help Detection

AIは `forbidden_help_given` を返す。backendも簡易検査を行う。

検査例:

- 「正解はA」
- 「この問題の答えは」
- 「選択肢Bを選べばよい」
- テストフェーズのexpected_answerに極端に近い文

検出時:

- 管理画面で警告
- ログに `forbidden_help_given = true`
- 研究データから除外できるようCSVへ出す
