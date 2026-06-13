# 04. Scaffolding and Tutoring

## 2026-06 Iterative Flow Scaffolding Update

学習セッション自体を足場掛けとして扱う。実験全体では、テストで残った未達項目だけを学習し、正解済み用語は次周回から除外する。学習セッション内は現行の `term_understanding → concept_understanding` を維持し、`unknown` とM1〜M3のいずれも `L3用語理解 → L2概念理解` の流れで支援する。

教材方略は `unknown`, M1, M2, M3 を対象にする。M4の文脈転移方略は今回の教材出し分けから外し、M4が検出された場合も専用の `context_transfer_training` へは進めない。


## 2026-06 Stage-Based Learning Update

学習セッションの画面進行は、固定3ターンのL1/L2/L3足場掛け制ではなく、次のステージ制を正とする。

1. `term_understanding`: 対象概念に必要な構成用語を1つずつ確認する。十分回答なら次の構成用語へ進み、不十分なら同じ構成用語を再提示する。
2. `concept_understanding`: 構成用語を用いて対象概念全体を説明させる。十分回答なら `final_feedback` へ進み、不十分なら `term_understanding` の先頭へ戻る。
3. `final_feedback`: 問題・回答欄を出さず、教材フィードバックと次へボタンだけを表示する。

`scaffolding_level` と `next_scaffolding_level` は既存ログ・CSV互換のため保持するが、セッション完了判定や被験者画面の進行表示には使わない。`is_sufficient = true` だけでセッション完了にはしない。完了するのは `concept_understanding` で十分回答した場合のみである。


## 学習ステージと教材提示

現行実装では、`scaffolding_level` によって教材の説明量を減らさない。用語理解段階・概念理解段階のどちらでも、初回教材から以下を提示する。

- 現在の構成用語または対象概念の定義
- 対象概念の中での役割
- よくある誤解との違い
- 短い具体例または判断基準

その後、学習者に自分の言葉で再説明させる記述問題を出す。答えだけを丸写しさせるのではなく、役割や判断基準を含めて説明させる。

`scaffolding_level` / `next_scaffolding_level` は既存ログ、CSV互換、内部分析のために残す。教材生成時にAIが返す `scaffolding_level` は参考値であり、被験者画面には表示しない。

### 確認テスト

許可:

- 問題提示
- 回答欄
- 学習者回答・自己説明

禁止:

- ヒント
- 例
- 解説
- チャット応答
- 即時正誤フィードバック
- 「惜しい」「もう一度考えて」など正誤を示唆する反応

## 初期レベル決定

| 状態 | 初期レベル |
|---|---|
| unknown | L3 |
| misconception | L3 |
| unstable_correct | L2 |
| stable_correct | L1 |
| transfer_ready | L1 |

`stable_correct` でも根拠が不足する場合はL1にする。いきなりL1へ進めるのは、回答と診断根拠が十分に一貫している場合だけにする。

## 更新ルール

学習セッション内のステージ更新は、AIの `next_action` ではなく、回答が現在ステージに対して十分かどうかを示す `is_sufficient` に基づいてbackendが決定論的に決める。

| 場面 | 今回結果 | 次回レベル | 追加処理 |
|---|---|---|---|
| 用語理解段階 | `is_sufficient = true` | 次の構成用語、または概念理解段階へ進む | stable_correct_count加算 |
| 用語理解段階 | `is_sufficient = false` | 同じ構成用語を再提示 | needs_review |
| 概念理解段階 | `is_sufficient = true` | final_feedbackへ進みセッション完了 | stable_correct_count加算 |
| 概念理解段階 | `is_sufficient = false` | 用語理解段階の先頭へ戻る | needs_review |
| 再テスト | 誤答 | 維持 | needs_review |
| 再テスト | 同じMで誤答 | 維持 | strategy_changed=true |
| 再テスト | 正答 | 1段階下げる | L1到達を目指す |
| 確認テスト | 正答 | L1を維持 | l0_success_count加算 |
| 確認テスト | 誤答 | L2相当へ上げる | needs_review |

レベル境界:

- L3より上へは上げない
- L1より下へは下げない
- 1回の更新で2段階以上変えない
- AIが `next_scaffolding_level` を返しても参考値に留め、サービス層の決定論的ルールで最終決定する
- AIがチューターターン生成で `scaffolding_level` を返しても採用せず、`LearnerState.scaffolding_level` を `tutor_turns.scaffolding_level` とデバッグ表示の正とする
- `next_action` は画面遷移補助に使い、正誤や足場掛け更新の根拠にしない
- 回答後のデバッグ欄は `learning_stage` と回答判定を「十分/不十分」で表示する

## 教授方略

| 対象 | 方略ID | 内容 |
|---|---|---|
| M1 | category_reorientation | 概念のカテゴリーを修正する |
| M2 | boundary_comparison | 類似概念との差分を比較する |
| M3 | deep_structure_focus | 表層語ではなく判断基準に注目させる |
| M4 | self_explanation_check | 今回の教材方略では専用出し分けしない |
| unknown | foundational_explanation | 基礎説明から始める |
| unstable_correct | self_explanation_check | 自己説明で確認する |
| control | general_explanation | 一般的な解説に留める |

## 誤概念タイプ x 教授方略の出し分け

| Mタイプ | L3 | L2 | L1 |
|---|---|---|---|
| M1 | 誤カテゴリーと正カテゴリーを明示し、例と反例を出す | 「何の種類の概念か」を問い返す | 上位カテゴリーだけ示す |
| M2 | 比較表で入力・処理・出力・用途を対比する | 比較軸を1〜2個示す | 区別すべき相手概念だけ示す |
| M3 | 表層判断の反例を示し、判断基準を説明する | 表面語ではなく見るべき関係を示す | 着目する関係を1つだけ示す |
| M4 | 今回は専用方略なし | 今回は専用方略なし | 今回は専用方略なし |

## 学習セッションテンプレート

```text
【前回の回答】
{learner_answer}

【今回の確認ポイント】
{natural_language_diagnosis}

【ミニ説明】
{mini_lesson}

【問い返し】
{scaffolded_question}

【あなたの回答】
{learner_input}

【次ターン冒頭の前ターン情報】
前の問題: {previous_practice_question}
あなたの回答: {previous_learner_response}
前の回答を踏まえて: {previous_feedback_for_learner}

【確認問題】
{practice_question}

【自己説明】
{self_explanation_prompt}
```

学習セッションでは、デバッグ用に誤概念タイプ判定、learning_stage、回答判定、教授方略を通常の被験者画面にも表示する。教材・フィードバック本文では、たとえばM1の場合は「この説明では、概念を少し別の種類のものとして捉えている可能性があります」のように自然言語へ変換し、内部ラベルを説明文へ混ぜない。

ターン継続時は回答確認後の単独フィードバック枠を表示しない。継続ターンがある場合は、保存した前の問題、学習者回答、`ai_feedback` を次ターン教材の冒頭に統合する。セッション完了時は問題を出さず、教材フィードバックだけを表示してから次へ進む。

## 再発時の方略変更

| 1回目の方略 | 再発時の方略 |
|---|---|
| foundational_explanation | category_reorientationまたはboundary_comparison |
| category_reorientation | contrastive_example |
| boundary_comparison | discrimination_practice |
| deep_structure_focus | counterexample_prompt |
| context_transfer_training | 今回の教材方略では使用しない |
| self_explanation_check | guided_self_correction |

再発時は同じ説明文の再送を禁止する。`tutor_turns.strategy_changed` を true にし、変更前後の方略を保存する。

## チャット制御

学習セッション中の自由入力は完全な自由チャットではない。被験者が選べる補助ボタンを用意し、研究条件を壊さない範囲で応答する。

許可する要求:

- もう少し簡単に
- 例を見たい
- 反例を見たい
- 違いを比較したい
- 自分の説明を確認して

禁止する要求:

- 答えだけ教えて
- テスト問題の正解を教えて
- 次の問題を解いて
- 選択肢のどれが正解か教えて
- レポート用に完成文を書いて

禁止要求への返答:

```text
この実験では、正解だけを提示することはできません。
代わりに、考えるための観点を1つ示します。
```

## 統制群のチューター挙動

統制群では、AIは一般的な解説を提示する。内部的に診断しても、発話生成には誤概念タイプ、過去ログ、学習ステージ履歴による個別化を使わない。初回教材は提案群と同じく十分な説明量を持つ。

統制群で許可:

- 一般的な定義説明
- 簡単な例
- 一般的な確認問題

統制群で禁止:

- 「前回と同じ誤りです」のようなログ参照
- 誤概念タイプ別の説明切替
- 学習ステージ履歴や誤概念タイプに基づく個別化
- 再発に応じた方略変更

## 状態更新の責務分離

AIは次アクション、互換scaffolding_level、方略を提案してよい。ただし次ステージ、構成用語インデックス、セッション完了、最終方略の決定はbackendの学習進行ロジックが行う。

理由:

- 研究条件を決定論的に保つ
- app-serverのAI出力が揺れても評価指標の定義を保つ
- AI出力の揺れで評価指標が変わらないようにする

## RAG教材参照

学習ターン生成と学習回答フィードバックでは、`rag_ready_教材` のローカルTF-IDF検索結果を `rag_context` としてAIBackend payloadへ渡す。OpenAI APIキーや外部vector storeは通常実行に使わない。RAG資産が見つからない場合は空のcontextとして扱い、実験フローを停止しない。