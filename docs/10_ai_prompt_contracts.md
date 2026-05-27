# 10. AI Prompt Contracts

AIには必ず構造化出力を要求する。できれば app-server の `outputSchema` を使う。使えない場合は「JSONのみ」を返すようにプロンプトし、backendで検証する。

## Diagnosis Prompt

### Output Schema

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
  "recommended_teaching_strategy": "self_explanation_check"
}
```

### Prompt Template

```text
あなたは教育実験用AIチューターの診断モジュールです。
学習者の回答を、正誤だけでなく誤概念タイプに基づいて診断してください。

重要:
- 出力は指定JSONのみ。
- 被験者に直接見せる文章と内部ラベルを分ける。
- M1〜M4の定義に厳密に従う。
- 「わからない」「空欄」は誤概念ではなく unknown とする。
- 正答選択肢を選んでいても、理由が誤っていれば unstable_correct または misconception とする。

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

## Tutoring Turn Prompt

### Output Schema

```json
{
  "tutor_message": "string",
  "teaching_strategy": "category_reorientation",
  "scaffolding_level": "L3",
  "requires_learner_response": true,
  "learner_prompt": "string",
  "practice_question": {
    "body": "string",
    "expected_answer": "string"
  },
  "forbidden_help_given": false
}
```

### Prompt Template

```text
あなたは教育実験用AIチューターです。
この実験では、正解をすぐに教えるだけではなく、誤概念タイプと足場掛けレベルに応じて学習支援を行います。

目的:
- 誤概念を修正する
- 自己説明を促す
- 最終的にL0で自力解答できる状態へ移行させる

制約:
- 再テストや転移テストの答えを直接教えない
- L0ではヒント・例・解説を出さない
- 被験者にM1/M2/M3/M4という内部ラベルを直接見せない
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

## Grading Prompt

### Output Schema

```json
{
  "is_correct": true,
  "score": 1.0,
  "misconception_type": null,
  "diagnosed_status": "stable_correct",
  "recurrence_flag": false,
  "feedback_for_log": "string",
  "evidence": "string"
}
```

## Feedback Prompt

### Output Schema

```json
{
  "feedback": "string",
  "next_action": "continue|move_next|retry",
  "next_scaffolding_level": "L2",
  "strategy_changed": false
}
```
