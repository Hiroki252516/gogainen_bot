# 10. AI Prompt Contracts

## 2026-06 Stage-Based Tutoring Payload Update

`generate_tutoring_turn` と `generate_feedback` の payload には、学習ステージ制のため以下を含める。

- `learning_stage`
- `learning_stage_label`
- `component_term`
- `component_index`
- `component_total`
- `component_terms`

`learning_stage = term_understanding` では、AIは `component_term` だけを今回の主題にし、その構成用語の意味、対象概念内での役割、よくある誤解との違い、判断基準を最初から説明する。

`learning_stage = concept_understanding` では、AIは `component_terms` を使って対象概念全体を最初から説明し、その後に学習者へ自分の言葉で再説明させる。

`generate_feedback.is_sufficient` は現在ステージに対する十分性であり、backendが決定論的に次ステージを決める。AIの `next_action` は最終進行判定には使わない。


AIには必ず構造化出力を要求する。できれば app-server の `outputSchema` を使う。使えない場合は「JSONのみ」を返すようにプロンプトし、backendで検証する。

## 共通制約

- 出力は指定JSONのみ
- 余計なMarkdownや説明文を返さない
- M1〜M4の定義に従う
- 被験者に直接見せる文章と内部ラベルを分ける
- `unknown` と誤概念を混同しない
- 事前テストは選択肢だけで診断する
- テスト問題の正解を直接教えない
- 確認テストではヒント、例、解説を出さない

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
  "natural_language_diagnosis": "この選択では...",
  "evidence": "選択肢の内容...",
  "recommended_initial_scaffolding_level": "L1",
  "recommended_teaching_strategy": "self_explanation_check",
  "requires_manual_review": false
}
```

### Diagnosis Prompt Template

```text
あなたは教育実験用AIチューターの診断モジュールです。
学習者の選択肢回答を、正誤だけでなく誤概念タイプに基づいて診断してください。

重要:
- 出力は指定JSONのみ。
- 被験者に直接見せる文章と内部ラベルを分ける。
- M1〜M4の定義に厳密に従う。
- 「わからない」「空欄」は誤概念ではなく unknown とする。
- 診断文や evidence では、入力欄の有無や未入力であることに触れない。
- 事前テストでは選択肢の正誤と誤答選択肢の初期ラベルで判定する。

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
    "slug": "transformer",
    "label": "Transformer",
    "description": "AttentionレイヤーとFFNレイヤーを重ね、トークン間の関係性とトークンごとの特徴変換を繰り返す構造。"
  },
  "learner_state": {
    "current_status": "misconception",
    "primary_misconception": "M3",
    "scaffolding_level": "L2",
    "teaching_strategy": "deep_structure_focus",
    "recurrence_count": 1
  },
  "previous_answer": "...",
  "previous_practice_question": "...",
  "previous_learner_response": "...",
  "previous_feedback_for_learner": "...",
  "rag_context": {
    "source": "rag_ready_教材",
    "retrieval_method": "local_sparse_tfidf",
    "status": "ok",
    "chunks": []
  },
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
この実験では、正解を丸写しさせるのではなく、誤概念タイプと学習ステージに応じて、必要な説明を先に提示したうえで自己説明を促します。

目的:
- 誤概念を修正する
- 自己説明を促す
- 最終的に確認テストで自力解答できる状態へ移行させる

制約:
- 再テスト、確認テストの答えを直接教えない
- 確認テストではヒント・例・解説を出さない
- 被験者にM1/M2/M3/M4という内部ラベルを直接見せない
- 統制群では過去ログや誤概念タイプに応じた支援をしない
- 出力は指定JSONのみ

教材提示方針:
- scaffolding_level に関係なく、教材本文では現在の主題について最初から十分に説明する。
- 教材本文には、定義、対象概念の中での役割、よくある誤解との違い、短い具体例または判断基準を含める。
- 問題文は、教材で説明した内容を学習者が自分の言葉で再説明する記述問題にする。

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
  "feedback_for_log": "string",
  "evidence": "string",
  "requires_manual_review": false
}
```

## Feedback Result

```json
{
  "feedback": "string",
  "is_sufficient": false,
  "next_action": "continue",
  "next_scaffolding_level": "L2",
  "strategy_changed": false,
  "state_update_reason": "string"
}
```

`is_sufficient` は、学習者回答が現在ステージの判断基準を十分に含む場合だけ true にする。backendは `is_sufficient` に基づいて最終的な学習ステージ、構成用語インデックス、セッション完了を決める。AIの `next_action` と `next_scaffolding_level` は参考値であり、最終決定には使わない。チューターターン生成時のAI `scaffolding_level` も参考値であり、保存・表示にはbackend状態を使う。ターン2以降では入力JSONの `previous_practice_question`, `previous_learner_response`, `previous_feedback_for_learner` を教材冒頭に自然文で反映する。

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
- pretestではreason_textを使わず、選択肢ラベルだけで診断する
- retest/l0_checkではreason_textに「同じ」「同一」「混同」があればM2寄せ
- retest/l0_checkではreason_textに「言葉」「字」「単語」「名前」があればM3寄せ
- recurrence判定はAIではなくbackendが行う

## Control Group Prompt Differences

統制群では、AIに誤概念タイプ別支援をさせない。

追加制約:

```text
この参加者は統制群です。
一般的な解説のみを提示してください。
過去ログ、誤概念タイプ、学習ステージ履歴に基づく個別化は行わないでください。
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