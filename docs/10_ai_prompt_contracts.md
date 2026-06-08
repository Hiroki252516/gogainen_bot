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
- 統制群では誤概念タイプ、過去ログ、前提用語ゲート情報を教授に使わない

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
      "expected_answer": "..."
    }
  ],
  "plan_rationale": "..."
}
```

前提用語は原則3件。多すぎる場合は、対象概念を理解するために不可欠なものへ絞る。

## Proposed: grade_prerequisite_answer

前提用語理解チェックを採点する。

Result:

```json
{
  "is_passed": true,
  "score": 0.8,
  "feedback": "...",
  "remediation_material": null,
  "core_elements_covered": ["..."],
  "major_errors": []
}
```

pass基準は中程度。中核要素が含まれ、重大な誤りがなければpass。

## Proposed: generate_concept_material

全前提用語pass後に、対象概念教材と説明promptを生成する。

Result:

```json
{
  "concept_material": "...",
  "concept_prompt": "上の前提用語を使って、Attentionを説明してください。",
  "expected_answer": "..."
}
```

## Proposed: grade_concept_answer

対象概念理解チェックを採点する。

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

fail時は、不足用語とその直前の関連用語を返す。backendは最大4回の上限を管理する。

## Control: generate_control_learning_turn

統制群の通常AI説明を生成する。

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

統制群の自己説明に一般的フィードバックを返す。

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
- 前提用語回答は「pass」「十分」「関係」「重み」「事前」「事後」などの語を含む場合にpassしやすくする
- 2回failや4回failの境界をテストできるよう、短い回答はfailにする
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
