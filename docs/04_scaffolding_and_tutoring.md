# 04. Scaffolding and Tutoring

## 足場掛けレベル

| レベル | 名称 | 内容 |
|---|---|---|
| L3 | 強支援 | 詳しい説明、例、反例、比較表、穴埋め |
| L2 | 中支援 | 観点提示、部分的ヒント、短い問い返し |
| L1 | 弱支援 | 着目点だけ、キーワードだけ |
| L0 | 支援なし | 問題のみ、ヒント・例・解説なし |

足場掛けは、理解が進んだら減らす。支援を多くすること自体が目的ではない。

## レベル別の許可内容

### L3

許可:

- 正しい定義を説明
- 誤った理解との対比
- 具体例
- 反例
- 比較表
- 穴埋め問題
- 誘導質問

禁止:

- 再テスト、L0、転移テストの答えを直接教える
- 学習者の代わりに自己説明を完成させる

### L2

許可:

- 判断観点を提示
- 部分的なヒントを出す
- 比較軸を示す
- 理由説明を求める

禁止:

- 完成された解答文の提示
- 長い定義の丸暗記誘導

### L1

許可:

- 着目点を1つだけ示す
- キーワードを1つだけ示す
- 自己説明を促す

禁止:

- 詳しい説明
- 例示
- 反例
- 比較表
- 選択肢の消去法を直接教える

### L0

許可:

- 問題提示
- 回答欄
- 自信度入力

禁止:

- ヒント
- 例
- 解説
- チャット応答
- 即時正誤フィードバック
- 「惜しい」「もう一度考えて」など正誤を示唆する反応

## 初期レベル決定

| 状態 | 自信度 | 初期レベル |
|---|---:|---|
| unknown | 任意 | L3 |
| misconception | 4-5 | L3 |
| misconception | 1-3 | L2 |
| unstable_correct | 任意 | L2 |
| stable_correct | 1-3 | L1 |
| stable_correct | 4-5 | L0候補 |
| transfer_ready | 任意 | L0 |

`stable_correct` でも理由が短すぎる場合はL1にする。いきなりL0へ進めるのは、選択肢、理由、自信度が一貫している場合だけにする。

## 更新ルール

| 前回状態 | 今回結果 | 次回レベル | 追加処理 |
|---|---|---|---|
| 誤答 | 正答 | 1段階下げる | stable_correct_count加算 |
| 誤答 | 誤答 | 維持 | needs_review |
| 誤答 | 同じMで誤答 | 維持 | strategy_changed=true |
| 正答 | 正答 | 1段階下げる | L0到達を目指す |
| 正答 | 誤答 | 1段階上げる | primary_misconception更新 |
| L0 | 正答 | L0維持 | l0_success=true |
| L0 | 誤答 | L1またはL2へ戻す | l0_success=false |

レベル境界:

- L3より上へは上げない
- L0より下へは下げない
- 1回の更新で2段階以上変えない
- AIが提案しても、サービス層の決定論的ルールで最終決定する

## 教授方略

| 対象 | 方略ID | 内容 |
|---|---|---|
| M1 | category_reorientation | 概念のカテゴリーを修正する |
| M2 | boundary_comparison | 類似概念との差分を比較する |
| M3 | deep_structure_focus | 表層語ではなく判断基準に注目させる |
| M4 | context_transfer_training | 別文脈で共通構造を使わせる |
| unknown | foundational_explanation | 基礎説明から始める |
| unstable_correct | self_explanation_check | 自己説明で確認する |
| control | general_explanation | 一般的な解説に留める |

## 誤概念タイプ x 足場掛けの出し分け

| Mタイプ | L3 | L2 | L1 |
|---|---|---|---|
| M1 | 誤カテゴリーと正カテゴリーを明示し、例と反例を出す | 「何の種類の概念か」を問い返す | 上位カテゴリーだけ示す |
| M2 | 比較表で入力・処理・出力・用途を対比する | 比較軸を1〜2個示す | 区別すべき相手概念だけ示す |
| M3 | 表層判断の反例を示し、判断基準を説明する | 表面語ではなく見るべき関係を示す | 着目する関係を1つだけ示す |
| M4 | 学習文脈と別文脈の共通構造を説明する | 共通点と相違点を問い返す | 共通構造という観点だけ示す |

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

【フィードバック】
{feedback}

【確認問題】
{practice_question}

【自己説明】
{self_explanation_prompt}
```

被験者画面では内部ラベルを出さない。たとえばM1の場合は「この説明では、概念を少し別の種類のものとして捉えている可能性があります」のように自然言語へ変換する。

## 再発時の方略変更

| 1回目の方略 | 再発時の方略 |
|---|---|
| foundational_explanation | category_reorientationまたはboundary_comparison |
| category_reorientation | contrastive_example |
| boundary_comparison | discrimination_practice |
| deep_structure_focus | counterexample_prompt |
| context_transfer_training | common_structure_extraction |
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

統制群では、AIは一般的な解説を提示する。内部的に診断しても、発話生成には誤概念タイプ、過去ログ、足場掛け更新を使わない。

統制群で許可:

- 一般的な定義説明
- 簡単な例
- 一般的な確認問題

統制群で禁止:

- 「前回と同じ誤りです」のようなログ参照
- 誤概念タイプ別の説明切替
- L3〜L0の動的調整
- 再発に応じた方略変更

## 状態更新の責務分離

AIは次レベルや方略を提案してよい。ただし最終決定はbackendの `ScaffoldingService` が行う。

理由:

- 研究条件を決定論的に保つ
- MockAIBackendでも同じ結果にする
- AI出力の揺れで評価指標が変わらないようにする
