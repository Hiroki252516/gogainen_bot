# 04. Scaffolding and Tutoring

## 足場掛けレベル

| レベル | 名称 | 内容 |
|---|---|---|
| L3 | 強支援 | 詳しい説明、例、反例、比較表、穴埋め |
| L2 | 中支援 | 観点提示、部分的ヒント、短い問い返し |
| L1 | 弱支援 | 着目点だけ、キーワードだけ |
| L0 | 支援なし | 問題のみ、ヒント・例・解説なし |

## レベル別の許可内容

### L3

- 正しい定義を説明
- 誤った理解との対比
- 具体例
- 反例
- 比較表
- 穴埋め問題
- 誘導質問

ただし再テスト・転移テストの答えを直接教えない。

### L2

- 判断観点を提示
- 部分的なヒントを出す
- 比較軸を示す
- 理由説明を求める

完成された解答文は提示しない。

### L1

- 着目点を1つだけ示す
- キーワードを1つだけ示す

詳しい説明、例示、反例、比較表は出さない。

### L0

- 問題提示のみ
- ヒント、例、解説、チャット応答、即時正誤フィードバックは禁止

## 初期レベル決定

| 状態 | 初期レベル |
|---|---|
| unknown | L3 |
| misconception + confidence high | L3 |
| misconception + confidence low | L3 or L2 |
| unstable_correct | L2 |
| stable_correct | L1 |
| transfer_ready | L0 |

## 更新ルール

| 前回 | 今回 | 次回 |
|---|---|---|
| 誤答 | 正答 | 1段階下げる |
| 誤答 | 誤答 | 維持 |
| 誤答 | 同じMで誤答 | 維持 + 方略変更 |
| 正答 | 正答 | 1段階下げる |
| 正答 | 誤答 | 1段階上げる |
| L0 | 正答 | L0維持、支援なし理解 |
| L0 | 誤答 | L1またはL2へ戻す |

## 教授方略

| Mタイプ | 方略ID | 内容 |
|---|---|---|
| M1 | category_reorientation | 概念のカテゴリーを修正する |
| M2 | boundary_comparison | 類似概念との差分を比較する |
| M3 | deep_structure_focus | 表層語ではなく判断基準に注目させる |
| M4 | context_transfer_training | 別文脈で共通構造を使わせる |
| unknown | foundational_explanation | 基礎説明から始める |
| unstable_correct | self_explanation_check | 自己説明で確認する |

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

## 再発時の方略変更

| 1回目の方略 | 再発時の方略 |
|---|---|
| 説明型 | 比較型 |
| 比較型 | 反例型 |
| 反例型 | 自己説明型 |
| 自己説明型 | 文脈変換型 |
| 文脈変換型 | L3に戻して再構成 |
