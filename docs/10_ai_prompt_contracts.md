# 10. AI Prompt Contracts

AIには必ず構造化出力を要求する。できれば app-server の `outputSchema` を使う。使えない場合は「JSONのみ」を返すようにプロンプトし、backendで検証する。

## 共通制約

- 出力は指定JSONのみ
- 余計なMarkdownや説明文を返さない
- M1〜M4の定義に従う
- 被験者に直接見せる文章と内部ラベルを分ける
- `unknown` と誤概念を混同しない
- 正答選択肢でも理由が不十分なら `unstable_correct`
- テスト問題の正解を直接教えない
- L0ではヒント、例、解説を出さない

## Diagnosis Payload

```json
{
  "participant_id": "uuid",
  "group_condition": "proposed",
  "term": {
    "slug": "attention",
    "label": "Attention",
    "definition": "..."
  },
  "question": {
    "id": "uuid",
    "phase": "pretest",
    "question_type": "definition",
    "body": "...",
    "expected_answer": "..."
  },
  "selected_option": {
    "id": "uuid",
    "body": "...",
    "is_correct": false,
    "initial_misconception_type": "M3"
  },
  "learner_response": {
    "reason_text": "...",
    "free_text_answer": null,
    "confidence": 4
  },
  "history": {
    "previous_attempts": []
  }
}
```

## Diagnosis Result

```json
{
  "is_correct": true,
  "diagnosed_status": "stable_correct",
  "misconception_type": null,
  "secondary_misconception_type": null,
  "diagnosis_confidence": 0.92,
  "natural_language_diagnosis": "この回答では...",
  "evidence": "学習者は理由欄で...",
  "recommended_initial_scaffolding_level": "L1",
  "recommended_teaching_strategy": "self_explanation_check",
  "requires_manual_review": false
}
```

### Diagnosis Prompt Template

```text
あなたは教育実験用AIチューターの診断モジュールです。
学習者の回答を、正誤だけでなく誤概念タイプに基づいて診断してください。

重要:
- 出力は指定JSONのみ。
- 被験者に直接見せる文章と内部ラベルを分ける。
- M1〜M4の定義に厳密に従う。
- 「わからない」「空欄」は誤概念ではなく unknown とする。
- 正答選択肢を選んでいても、理由が誤っていれば unstable_correct または misconception とする。
- M4は原則として転移問題で判定する。

M1: カテゴリー誤分類型
M2: 類似概念境界混同型
M3: 表層特徴・キーワード反応型
M4: 文脈転移失敗型
unknown: 知識不足
ambiguous: 判定困難

入力:
{payload_json}

指定JSONスキーマ:
{schema_json}
```

## Tutoring Turn Payload

```json
{
  "participant_id": "uuid",
  "group_condition": "proposed",
  "term": {
    "slug": "overfitting",
    "label": "過学習"
  },
  "learner_state": {
    "current_status": "misconception",
    "primary_misconception": "M3",
    "scaffolding_level": "L2",
    "teaching_strategy": "deep_structure_focus",
    "recurrence_count": 1
  },
  "previous_answer": "...",
  "previous_diagnosis_for_learner": "言葉の表面ではなく、訓練データと未知データの性能差に注目します。",
  "allowed_help": ["hint", "question_prompt", "self_explanation"],
  "forbidden_help": ["direct_answer", "test_answer", "option_elimination"]
}
```

## Tutoring Turn Result

```json
{
  "tutor_message": "string",
  "teaching_strategy": "category_reorientation",
  "scaffolding_level": "L3",
  "requires_learner_response": true,
  "learner_prompt": "string",
  "practice_question": {
    "body": "string",
    "expected_answer": "string",
    "question_type": "practice"
  },
  "forbidden_help_given": false
}
```

### Tutoring Turn Prompt Template

```text
あなたは教育実験用AIチューターです。
この実験では、正解をすぐに教えるだけではなく、誤概念タイプと足場掛けレベルに応じて学習支援を行います。

目的:
- 誤概念を修正する
- 自己説明を促す
- 最終的にL0で自力解答できる状態へ移行させる

制約:
- 再テスト、L0確認、転移テストの答えを直接教えない
- L0ではヒント・例・解説を出さない
- 被験者にM1/M2/M3/M4という内部ラベルを直接見せない
- 統制群では過去ログや誤概念タイプに応じた支援をしない
- 出力は指定JSONのみ

足場掛けレベル:
L3: 詳しい説明、例、反例、比較表、穴埋めが可能
L2: 観点提示、部分ヒントのみ
L1: 着目点のみ
L0: 問題提示のみ

入力:
{payload_json}

指定JSONスキーマ:
{schema_json}
```

## Grading Result

```json
{
  "is_correct": true,
  "score": 1.0,
  "misconception_type": null,
  "secondary_misconception_type": null,
  "diagnosed_status": "stable_correct",
  "recurrence_flag": false,
  "l0_success": true,
  "transfer_success": true,
  "feedback_for_log": "string",
  "evidence": "string",
  "requires_manual_review": false
}
```

## Feedback Result

```json
{
  "feedback": "string",
  "next_action": "continue",
  "next_scaffolding_level": "L2",
  "strategy_changed": false,
  "state_update_reason": "string"
}
```

## State Summary Result

```json
{
  "summary_for_admin": "string",
  "summary_for_learner": "string",
  "risk_flags": ["same_misconception_recurred"],
  "recommended_next_focus": "string"
}
```

## JSON Schema Validation

backendはAI出力をPydanticで検証する。

検証失敗時:

1. raw_textを `ai_call_logs` に保存
2. JSON抽出を試す
3. 1回だけ修復依頼を出す
4. それでも失敗したら `requires_manual_review = true`

## MockAIBackend Rules

必ず実装する。Codex app-serverなしでもテストが通るようにする。

決定論的ルール:

- correct optionなら `stable_correct`
- known M optionならそのMを返す
- unknown optionなら `unknown`
- reason_textに「同じ」「同一」「混同」があればM2寄せ
- reason_textに「言葉」「字」「単語」「名前」があればM3寄せ
- reason_textが空または10文字未満なら `unstable_correct` または `unknown`
- transfer phaseで基本説明は正しいが別文脈の適用理由がない場合はM4
- recurrence判定はAIではなくbackendが行う

## Control Group Prompt Differences

統制群では、AIに誤概念タイプ別支援をさせない。

追加制約:

```text
この参加者は統制群です。
一般的な解説のみを提示してください。
過去ログ、誤概念タイプ、足場掛けレベルに基づく個別化は行わないでください。
ただし分析用の内部診断JSONは返してください。
```

## Forbidden Help Detection

AIは `forbidden_help_given` を返す。backendも簡易検査を行う。

検査例:

- 「正解はA」
- 「この問題の答えは」
- 「選択肢Bを選べばよい」
- テストフェーズのexpected_answerに極端に近い文

検出時:

- 管理画面で警告
- tutor_turns.forbidden_help_given = true
- 研究データから除外できるようCSVへ出す
