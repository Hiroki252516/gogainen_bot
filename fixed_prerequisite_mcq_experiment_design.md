# 固定前提用語・固定選択問題・動的AI教材生成型AIチューター 実験設計書

## 1. 文書の位置づけ

本書は、`/Users/hiroki/ai_tutor_codex_spec` の現行実装を確認し、研究者回答Q1〜Q65を反映して確定した、次期実装用の実験設計書である。

本書の中心方針は次のとおりである。

- 学習対象概念は現行の5概念を維持する。
- 事前テストで正答した概念は学習対象外とする。
- M1〜M3誤答と「わからない」はすべて学習対象とする。
- 学習対象数は最大5概念とする。
- 前提用語は対象概念ごとに研究者が名称と順序を事前設定する。
- 設定された前提用語は、両群で全件扱う。
- 前提用語教材、概念フェーズ1教材、再学習教材はAIが実験中に動的生成する。
- 前提用語、概念フェーズ1、概念フェーズ2の問題は選択式とする。
- 通常時の問題文・選択肢・正答・誤概念分類はCodexが開発時に作成し、YAMLまたはJSONで事前管理する。
- 問題バンクを使い切った場合だけ、実験中のAIによる追加問題生成を許可する。
- 提案群と統制群は、同じ前提用語、同じ問題、同じ選択肢を使用する。
- 提案群だけが、事前テスト診断と累積学習ログを教材生成に利用する。
- 統制群は、累積診断や過去ログを利用しない通常AIチューターとする。
- 概念フェーズ2は「教材なしで正しい概念を選べるか」を測る。
- 研究目的を「概念説明能力」から「概念弁別・誤概念回避能力」へ変更する。
- 事前アンケート、L0確認、転移テストは実施しない。
- 再テストは学習対象だけではなく、全5概念を出題する。

本書の作成にあたり、リポジトリ内のコードおよびMarkdownは変更していない。

## 2. 確定した研究目的

### 2.1 研究の中心

本研究では、AI・情報系専門用語について、学習者が正しい概念を誤概念選択肢から区別できるかを測定する。

提案群では、事前テストと学習中の選択履歴から確認された誤概念タイプを利用し、AIが教材と再教材を個別生成する。

統制群では、同じ固定学習内容と固定問題を使用するが、事前テスト診断や累積学習ログを教授方略へ利用しない。

### 2.2 測定する能力

主に測定する能力は次のとおりである。

- 正しい概念定義を識別できること
- 類似概念との境界を区別できること
- 名称や表層的キーワードに誘導されないこと
- 教材提示下で正しい概念を選べること
- 教材を外した後も正しい概念を選べること
- 学習後の再テストで誤概念を再発させないこと

### 2.3 測定しない能力

学習セッションをすべて選択式に変更するため、次は現行研究の測定対象から外す。

- 自分の言葉で概念を説明する能力
- 記述文の構成力
- 前提用語を文章内で自然に使用する能力
- 教材なしで自由記述説明を再構成する能力
- 記述回答ルーブリックによる説明品質

したがって、概念フェーズ2を「独立説明成功」と呼ばない。

## 3. 比較する二群

比較対象は現行どおり次の二群とする。

| 群 | 名称 | 中心的な特徴 |
|---|---|---|
| control | 通常AIチューター | 固定学習内容とRAGを使うが、事前診断・累積ログに適応しない |
| proposed | ログ適応型AIチューター | 事前診断と学習中の選択履歴に応じてAI教材を個別化する |

### 3.1 両群で共通にするもの

- 対象概念
- 学習対象選定規則
- 対象概念ごとの前提用語
- 前提用語の件数
- 前提用語の順序
- 前提用語ごとの必須確認問題数
- 概念フェーズ1の必須確認問題数
- 概念フェーズ2の構成
- 問題文
- 選択肢
- 正答
- 誤答選択肢のM分類
- 選択肢ランダム化方式
- 前提用語とフェーズ1の最大試行回数
- 正答提示へ移る条件
- 再テスト問題

### 3.2 提案群だけが利用する情報

- 事前テストで選択した選択肢
- 事前テストのM1〜M3またはunknown
- 学習中に選択した誤答
- 誤概念タイプの継続・変化・再発
- 過去に提示した教材
- 前提用語レビュー履歴
- フェーズ1への戻り履歴
- フェーズ2失敗履歴

### 3.3 統制群が利用しない情報

統制群の教材生成では次を利用しない。

- 事前テスト診断
- 事前テスト選択肢
- M1/M2/M3
- 参加者の累積誤答履歴
- 過去の教授方略
- 前回の誤概念遷移

ただし、統制群でも現在回答した選択肢に対する一般的な正誤表示と、その選択肢が不適切な理由の説明は行う。これは累積学習ログによる個別化ではなく、通常AIチューターが行う即時フィードバックとして扱う。

## 4. 全体の実験フロー

```text
[参加登録]
  ↓
[事前テスト: 5概念]
  ↓
[事前テスト診断]
  ↓
[学習対象選定]
  ├─ stable_correct: 学習対象外
  └─ M1/M2/M3/unknown: 学習対象
  ↓
[学習対象概念ごとの3段階学習]
  1. 固定前提用語フェーズ
  2. 概念理解フェーズ1: AI教材あり
  3. 概念理解フェーズ2: 教材なし
  ↓
[全5概念の即時再テスト]
  ↓
[事後アンケート]
  ↓
[終了・評価・CSV出力]
```

実施しないもの:

- 事前アンケート
- L0確認
- 転移テスト
- 学習セッション内の記述回答
- 自信度入力

## 5. 事前テストと学習対象

### 5.1 事前テスト

事前テストは現行と同じ5概念を測定する。

1. Transformer
2. Attention
3. LLMの学習段階
4. 事前学習
5. 事後学習

回答形式は5択とする。

- correct
- M1
- M2
- M3
- unknown

理由欄と自信度欄は表示しない。

### 5.2 学習対象

| 事前テスト結果 | 学習対象 |
|---|---|
| stable_correct | 対象外 |
| M1 | 対象 |
| M2 | 対象 |
| M3 | 対象 |
| unknown | 対象 |

全問誤答またはunknownの場合は、5概念すべてを学習する。

## 6. 固定前提用語

### 6.1 基本方針

前提用語は、対象概念ごとに異なる固定セットを用意する。

前提用語について研究者が事前設定するものは次の二つに限定する。

- 前提用語の名称
- 表示順

前提用語の定義、学習目標、教材に含める内容、例、比較、反例は、AIが実験中にRAGと一般知識を使って動的に決定する。

### 6.2 件数

- 前提用語数は対象概念ごとに必要数を設定する。
- 全概念で同じ件数に統一する必要はない。
- 設定された前提用語はすべて出題する。
- 参加者の事前テスト結果によって前提用語を省略しない。
- 提案群と統制群で同じセットを使う。

例:

```yaml
target_term: attention
set_version: attention_prerequisites_v1
prerequisites:
  - key: token
    label: トークン
    display_order: 1
  - key: relation
    label: トークン間の関係
    display_order: 2
  - key: weight
    label: 重み付け
    display_order: 3
```

### 6.3 バージョン管理

- 前提用語セットにはバージョンを付ける。
- 修正前のセットは削除せず、非active化して残す。
- 参加者が学習を開始した時点のセットバージョンをセッションへ固定する。
- 実験途中でactive版が変わっても、進行中参加者には切り替えない。

## 7. 固定選択式問題

### 7.1 通常時の作成方法

問題文と選択肢はCodexが開発時にすべて作成する。

作成した問題はYAMLまたはJSONへ保存し、アプリ起動時または専用import処理でDBへ同期する。

専門家確認前でも実装してよい。ただし、確認前の問題には次の状態を付ける。

```text
validation_status = provisional
```

専門家確認後は次へ更新する。

```text
validation_status = approved
```

### 7.2 全問題共通の5択構成

すべての学習問題に次を1件ずつ用意する。

1. correct
2. M1
3. M2
4. M3
5. unknown

1つの選択肢に設定する誤概念タイプは主要タイプ1件だけとする。副次タイプは設定しない。

### 7.3 選択肢メタデータ

各選択肢には次を持たせる。

- `is_correct`
- `misconception_type`
- `diagnostic_rationale`
- `linked_prerequisite_keys`
- `remediation_focus`
- `default_order`

`linked_prerequisite_keys`は、概念フェーズ1やフェーズ2の誤答時に、どの前提用語を再確認するかを決定するために使う。

### 7.4 ランダム表示

- 選択肢順は参加者・問題ごとにランダム化する。
- 一度決定した順序をDBへ保存する。
- 再読み込み時は同じ順序を復元する。
- 画面上のA〜Eはランダム化後に付け直す。
- 内部の正答位置やMタイプは参加者向けAPIへ返さない。

### 7.5 採点

採点はAIではなく、選択肢メタデータで確定する。

```text
is_correct = selected_option.is_correct
diagnosed_status =
  correct なら resolved
  M1/M2/M3 なら misconception
  unknown なら unknown
misconception_type = selected_option.misconception_type
```

AIは正誤とMタイプを決定しない。

## 8. 問題セットとバリアント

### 8.1 問題スロット

問題は「学習上必ず通過すべき問題スロット」と「同じスロットの再試行バリアント」を分けて管理する。

例:

```text
前提用語「トークン」
  required_slot_1
    ├─ attempt_1_variant
    ├─ attempt_2_variant
    └─ attempt_3_variant
  required_slot_2
    ├─ attempt_1_variant
    ├─ attempt_2_variant
    └─ attempt_3_variant
```

### 8.2 前提用語問題

1つの前提用語につき、最初から必須問題を2問設定する。

- 必須問題1と必須問題2は異なる観点または異なる文脈で同じ前提用語を測る。
- 2問とも正答することを通常の通過条件とする。
- 各必須問題について、誤答時に未使用の別バリアントを出す。
- 各必須問題の最大試行回数は3回とする。

研究者回答の「前提用語は最大3回」と「最初から2問を全問正答する」を両立するため、本設計では最大3回を「各必須問題スロットごと」と解釈する。

したがって、1前提用語あたりの最大回答数は次のとおりである。

```text
2必須問題 × 最大3試行 = 最大6回答
```

### 8.3 概念フェーズ1問題

概念フェーズ1も、最初から複数の必須問題を設定する。

初期正式設定では、1対象概念につき2問を必須とする。

- 両方正答することを通常の通過条件とする。
- 各必須問題について最大3回まで回答できる。
- 誤答時は未使用の別バリアントを出す。
- フェーズ2失敗後にフェーズ1へ戻った場合は、新しいcycle用の問題セットを使用する。

YAML/JSONでは必須問題数を可変にできるようにするが、同じコンテンツバージョン内では全参加者に同じ件数を出す。

### 8.4 概念フェーズ2問題

- 1回のフェーズ2到達につき1問を出す。
- 提案群では最大3回までフェーズ2へ到達できる。
- 各回で未使用の別バリアントを使う。
- 統制群は1回だけ実施する。

## 9. 試行上限到達時の共通規則

前提用語と概念フェーズ1では、通常は必須問題をすべて正答しなければ次へ進めない。

ただし、各必須問題を3回連続で誤答した場合は例外とする。

処理:

1. 3回目の誤答を保存する。
2. 正解選択肢を明示する。
3. 正解の短い説明を表示する。
4. その問題を`forced_resolved`として記録する。
5. 次の必須問題または次フェーズへ進む。

この場合は`passed`と同一扱いにしない。

| 状態 | 意味 |
|---|---|
| passed | 自力で正答した |
| forced_resolved | 3回誤答後に正解提示を受けた |
| pending | 未実施または再試行中 |

セッション全体は途中で`blocked`、`failed_phase1`、`failed_phase2`にしない。理解不足による通常終端は廃止し、正解提示後にフローを完走させる。

AI障害やデータ不整合時だけ、技術的停止状態を使う。

## 10. 回答直後のフィードバック

### 10.1 正答時

- 「正解です」と表示する。
- AIが短い要点説明を生成する。
- 正答選択肢の文章をそのまま繰り返さない。
- 次の必須問題または次の前提用語へ進む。

### 10.2 誤答時

- 「不正解です」と表示する。
- 選択した選択肢がなぜ不適切か、AIが自然言語で説明する。
- 1回目・2回目の誤答では正答選択肢を教えない。
- AIが再教材を生成する。
- 未使用の別問題バリアントを出す。

### 10.3 3回目の誤答時

- 正答選択肢を提示する。
- 正解の短い説明を表示する。
- `forced_resolved=true`を保存する。
- 規定の次段階へ進む。

### 10.4 内部ラベル

参加者画面には次を表示しない。

- M1/M2/M3
- misconception_type
- diagnostic_rationale
- linked_prerequisite_keys
- 教授方略ID
- AI診断用内部データ

## 11. 新しい学習セッション全体フロー

```text
[対象概念の学習開始]
  ↓
[固定前提用語セットを読み込む]
  ↓
[前提用語1のAI教材を生成]
  ↓
[必須問題1]
  ├─ 正答 → 必須問題2
  └─ 誤答 → AI説明・再教材・別バリアント
              └─ 3回誤答 → 正解提示・forced_resolved
  ↓
[必須問題2]
  ├─ 正答 → 次の前提用語
  └─ 誤答 → 同じ規則
  ↓
[全前提用語を完了]
  ↓
[概念フェーズ1のAI教材を生成]
  ↓
[フェーズ1必須問題を複数出題]
  ├─ 全問正答 → フェーズ2
  ├─ 誤答 → 関連前提用語レビュー・再教材・別バリアント
  └─ 3回誤答 → 正解提示・forced_resolved
  ↓
[概念フェーズ2: 教材なし]
  ├─ 正答 → completed
  ├─ 提案群で1〜2回目誤答 → フェーズ1へ戻る
  ├─ 提案群で3回目誤答 → 正解提示してcompleted
  └─ 統制群で誤答 → 1回でcompleted
```

## 12. 前提用語フェーズ

### 12.1 セッション作成

バックエンドはAIへ前提用語を生成させない。

処理:

1. 対象概念のactiveな前提用語セットをYAML/JSON由来のDBデータから取得する。
2. セットのバージョンを学習セッションへ固定する。
3. 設定された前提用語を表示順どおりにセッションへ展開する。
4. 各前提用語に必須問題2件を割り当てる。
5. 最初の前提用語教材をAI生成する。

### 12.2 教材生成

前提用語の名称以外の教材内容はAIが決定する。

AIは次を生成してよい。

- 定義
- 仕組みの説明
- 例
- 比較
- 反例
- 注意点
- 図を使わない文章上の類推
- 誤答後の再説明

教材の文字数に固定上限は設けない。教材の長さと構成はAIに任せる。

### 12.3 提案群の教材入力

- 対象概念
- 固定前提用語名
- 事前テストで選択した選択肢
- 事前テストのMタイプ
- それまでの学習回答履歴
- 最新の誤概念タイプ
- 選択した誤答の`diagnostic_rationale`
- 選択した誤答の`remediation_focus`
- RAGコンテキスト

### 12.4 統制群の教材入力

- 対象概念
- 固定前提用語名
- 現在出題する固定問題の構成概念
- RAGコンテキスト

統制群は現在の誤答選択肢に対する一般的説明を受けられるが、過去の誤答やMタイプを蓄積して次教材へ利用しない。

### 12.5 両群の試行数

提案群・統制群ともに、各必須問題を最大3回まで回答する。

両群とも、前提用語1件につき必須問題2件を完了してから次の前提用語へ進む。

違いは教材の個別化にある。

- proposed: 事前診断と累積ログに基づく再教材
- control: 固定概念と現在問題だけに基づく一般教材

## 13. 概念理解フェーズ1

### 13.1 目的

AI教材を参照できる状態で、対象概念について複数の異なる問題に正答できるかを測る。

### 13.2 教材

フェーズ1開始時に、参加者ごとにAIが新しい教材を生成する。

提案群では次を反映する。

- 事前テストの誤概念
- 前提用語問題の選択履歴
- 自力正答とforced_resolvedの区別
- 前提用語ごとの最新Mタイプ
- 直近のフェーズ1またはフェーズ2誤答

統制群では、対象概念、固定前提用語名、RAG、一般知識だけを使う。

### 13.3 必須問題

初期正式設定では、対象概念ごとに必須問題2件を出す。

- 2問とも自力正答することを通常の通過条件とする。
- 各問題スロットで最大3回回答できる。
- 誤答時は未使用の別バリアントを使う。
- 3回誤答時は正答を提示し、`forced_resolved`とする。
- すべての問題スロットが`passed`または`forced_resolved`になったらフェーズ2へ進む。

### 13.4 提案群の前提用語レビュー

フェーズ1で誤答した場合は、選択肢に事前設定された`linked_prerequisite_keys`を使って戻る前提用語を決定する。

- AIに戻り先を決めさせない。
- 関連付けられた前提用語をreview状態にする。
- reviewでは未使用の別問題バリアントを使う。
- AIは選択誤答と過去ログに基づくレビュー教材を生成する。
- review完了後、フェーズ1へ戻る。

### 13.5 統制群

統制群はフェーズ1で前提用語へ戻さない。

ただし、提案群と同じく各必須問題を最大3回まで回答し、誤答時は一般的な説明と別バリアントを受ける。

3回誤答した問題は正答を提示して`forced_resolved`とし、全問題スロット完了後にフェーズ2へ進む。

## 14. 概念理解フェーズ2

### 14.1 目的

教材を表示しない状態で、対象概念の正しい説明を誤概念選択肢から識別できるかを測る。

新しい指標名は次とする。

```text
教材なし概念弁別正答率
```

### 14.2 表示内容

フェーズ2回答前に表示するもの:

- 問題文
- 選択肢
- 進捗

表示しないもの:

- 教材本文
- 軽い条件
- 使用語の指定
- ヒント
- 模範説明

### 14.3 提案群

#### 1回目・2回目で正答

- `phase2_passed=true`
- 学習セッションを`completed`にする。

#### 1回目・2回目で誤答

- 正誤を表示する。
- 選択した誤答が不適切な理由をAIが説明する。
- 正答選択肢は教えない。
- 選択肢に紐づく前提用語と誤概念焦点を保存する。
- フェーズ1へ戻る。
- フェーズ1画面でAI再教材を表示する。
- フェーズ1完了後、未使用のフェーズ2問題バリアントを出す。

#### 3回目で誤答

- 正答選択肢を提示する。
- 短い正解説明を表示する。
- `phase2_forced_completion=true`を保存する。
- 学習セッションを`completed`にする。

### 14.4 統制群

- フェーズ2は1回だけ実施する。
- 正誤を表示する。
- 誤答の場合は、選択した選択肢が不適切な理由を一般的に説明する。
- 正答でも誤答でも、1回の回答後に`completed`とする。
- フェーズ1へ戻らない。
- 誤答時にも正答選択肢そのものは提示しない。

## 15. AI教材生成

### 15.1 生成タイミング

AI教材は参加者ごとに毎回新規生成する。

- 前提用語の初回
- 前提用語の誤答後
- 前提用語レビュー
- フェーズ1初回
- フェーズ1誤答後
- フェーズ2誤答後に戻ったフェーズ1

同じ条件でも教材を共有またはキャッシュしない。

### 15.2 情報源

AIは次を使用できる。

- `rag_ready_教材`
- 一般知識
- 対象概念
- 固定前提用語名
- 提案群だけの診断・累積ログ

一般知識を補足した場合は、RAG由来部分と区別してログへ保存する。

### 15.3 生成可能な表現

AIは次を生成してよい。

- 例
- 比較
- 反例
- 定義
- 手順説明
- 類似概念との違い
- 誤答の問題点
- 短い正解要点

### 15.4 長さ

教材の文字数に固定上限を設けない。AIが必要な長さを判断する。

ただし、生成時間、画面表示量、実験時間はログに残し、予備実験で過度な長文化がないか確認する。

## 16. AIBackend契約

### 16.1 前提用語教材

```python
async def generate_prerequisite_material(payload: dict) -> dict:
    ...
```

提案群Payload例:

```json
{
  "participant_id": "uuid",
  "group_condition": "proposed",
  "target_term": {
    "slug": "attention",
    "label": "Attention"
  },
  "fixed_prerequisite": {
    "key": "weight",
    "label": "重み付け"
  },
  "diagnosis_context": {
    "pretest_misconception_type": "M3",
    "latest_learning_misconception_type": "M2",
    "selected_distractor_rationale": "重要単語抽出との混同"
  },
  "material_mode": "initial",
  "rag_context": {
    "chunks": []
  },
  "allow_general_knowledge": true
}
```

Result例:

```json
{
  "material": "...",
  "examples": ["..."],
  "comparisons": ["..."],
  "counterexamples": ["..."],
  "rag_sources": ["chunk_id"],
  "general_knowledge_supplement": "...",
  "answer_leak_detected": false
}
```

### 16.2 概念フェーズ1教材

```python
async def generate_concept_phase1_material(payload: dict) -> dict:
    ...
```

AIは教材だけを返す。問題文、選択肢、正答を返さない。

### 16.3 誤答説明

```python
async def explain_selected_distractor(payload: dict) -> dict:
    ...
```

AIは次を説明する。

- 選択した説明のどこが対象概念と一致しないか
- どの観点を見直すべきか

1回目・2回目の誤答では、正答選択肢の本文や位置を返さない。

### 16.4 正答時の短い要点

```python
async def generate_correct_answer_summary(payload: dict) -> dict:
    ...
```

正答文をそのまま繰り返さず、短い要点を返す。

### 16.5 問題バンク不足時の追加問題

```python
async def generate_emergency_question_variant(payload: dict) -> dict:
    ...
```

通常時は使用しない。

問題バンクを使い切った場合だけ、AIが追加問題を生成する。

生成結果は次の検証を通過しなければ出題しない。

- 5択である
- correctが1件だけ
- M1/M2/M3/unknownが1件ずつある
- 既出問題との文字列類似度が高すぎない
- 正答が一意である
- 内部ラベルが本文へ漏れていない
- 対象stageとconstructに一致する

生成問題には次を記録する。

```text
source_type = runtime_ai_fallback
validation_status = runtime_validated
```

事前作成問題とAI追加問題は分析時に区別できるようにする。

## 17. 正答漏洩防止

### 17.1 基本規則

AI教材や誤答説明が、未出題問題の正答選択肢をそのまま含んではならない。

### 17.2 自動検査

1. 教材と未使用正答選択肢を正規化する。
2. 完全一致を検査する。
3. 長い共通部分文字列を検査する。
4. 類似度が閾値を超えた場合は`answer_leak_detected=true`とする。
5. 教材を自動再生成する。
6. 再生成回数と検査結果を保存する。

### 17.3 AIへ渡さない情報

- ランダム化後の正答位置
- `correct_option_id`
- 未使用問題の完全な選択肢一覧

教材生成時は、対象概念名、前提用語名、RAG、許可された診断情報を中心に渡す。

## 18. 問題数

### 18.1 前提用語

前提用語1件につき:

```text
必須問題2件 × 最大3試行 = 6バリアント
```

前提用語が5件の場合:

```text
5前提用語 × 6バリアント = 30問 / 対象概念
```

### 18.2 概念フェーズ1

初期正式設定:

```text
必須問題2件 × 最大3試行 × 最大3cycle = 18問 / 対象概念
```

最大3cycleは、フェーズ2の1回目・2回目誤答後にフェーズ1へ戻る場合を含む。

### 18.3 概念フェーズ2

```text
最大3試行 = 3問 / 対象概念
```

### 18.4 最大概算

前提用語を各概念5件と仮定した場合:

```text
前提用語: 30問
フェーズ1: 18問
フェーズ2: 3問
合計: 51問 / 対象概念

51問 × 5概念 = 最大255問
```

実際の必要数は、対象概念ごとの前提用語数により変わる。

研究者は必要な問題数を許容し、現行上限を維持する。したがって、Codexは必要な固定問題バリアントをすべて事前作成する。

問題バンクを使い切った場合は、AIによる追加問題生成を行う。

## 19. 再テスト

### 19.1 出題範囲

再テストは学習対象だけではなく、全5概念を出題する。

これにより、次を確認できる。

- 学習対象概念の改善
- 事前テスト正答概念の維持
- 学習対象外概念での正答崩れ

### 19.2 問題

現在の`retest_v1`は維持せず、新設計に合わせて再改訂する。

新しい正式版は例として次のversionを使う。

```text
retest_v2
```

新しい再テストも5択とする。

- correct
- M1
- M2
- M3
- unknown

事前テスト、学習問題、再テストで同じ文面を使わない。

### 19.3 結果表示

再テスト中は、学習セッションと異なり次を表示しない。

- 正誤
- 解説
- 教材
- ヒント
- 正答

全問終了後も参加者には得点やMタイプを表示しない。

## 20. 誤概念状態

### 20.1 確定方法

学習中の誤概念タイプは選択肢メタデータから確定する。

AIは診断を確定しない。

### 20.2 状態

| 選択 | diagnosed_status | misconception_type |
|---|---|---|
| correct | resolved | null |
| M1 | misconception | M1 |
| M2 | misconception | M2 |
| M3 | misconception | M3 |
| unknown | unknown | unknown |

### 20.3 遷移

| 前状態 | 今回 | transition |
|---|---|---|
| M1 | M1 | persistence |
| M1 | M2 | M1_to_M2 |
| M1 | correct | resolution |
| resolved | M1 | recurrence |
| unknown | correct | resolution |
| any | unknown | knowledge_gap |

### 20.4 前提用語と対象概念

- 前提用語問題は、その前提用語の状態を更新する。
- フェーズ1・フェーズ2は、対象概念の状態を更新する。
- 前提用語のMタイプで対象概念の状態を直接上書きしない。
- フェーズ1・フェーズ2の選択肢に紐づく前提用語は、review先の決定に使う。

## 21. YAML/JSON管理

### 21.1 管理方式

固定前提用語と固定問題は、コード内のPython定数ではなくYAMLまたはJSONで管理する。

推奨構成:

```text
experiment_content/
  manifest.yaml
  terms/
    transformer.yaml
    attention.yaml
    llm_training_process.yaml
    pretraining.yaml
    post_training.yaml
  retest/
    retest_v2.yaml
```

### 21.2 概念ファイル例

```yaml
schema_version: 1
content_version: attention_learning_v1
target_term: attention
prerequisite_set:
  version: attention_prerequisites_v1
  items:
    - key: token
      label: トークン
      display_order: 1
      required_questions:
        - slot_key: token_q1
          variants:
            - variant_key: token_q1_attempt1_v1
              body: ...
              options: ...
            - variant_key: token_q1_attempt2_v1
              body: ...
              options: ...
            - variant_key: token_q1_attempt3_v1
              body: ...
              options: ...
        - slot_key: token_q2
          variants: ...
concept_phase1:
  required_questions:
    - slot_key: attention_phase1_q1
      cycle_variants: ...
    - slot_key: attention_phase1_q2
      cycle_variants: ...
concept_phase2:
  variants:
    - variant_key: attention_phase2_attempt1_v1
    - variant_key: attention_phase2_attempt2_v1
    - variant_key: attention_phase2_attempt3_v1
```

### 21.3 Import検証

YAML/JSONをDBへ読み込む前に次を検査する。

- schema version
- content version
- target term
- 前提用語keyの重複
- display_orderの重複
- 必須問題スロット数
- 必要バリアント数
- 5択構成
- 正答1件
- M1/M2/M3/unknown各1件
- linked prerequisite keyの存在
- variant keyの重複
- active versionの一意性

### 21.4 更新

- 新versionを追加する。
- 旧versionは非active化して残す。
- DB上の既存回答が参照する問題を削除しない。
- 進行中セッションは開始時点のversionを維持する。

## 22. 推奨データモデル

### 22.1 content_versions

- id
- content_type
- version_key
- source_file
- file_hash
- validation_status
- is_active
- imported_at

### 22.2 prerequisite_definitions

- id
- target_term_id
- prerequisite_key
- label
- display_order
- set_version
- is_active

研究者は名称と順序だけを設定するため、定義や学習目標の固定列は必須にしない。

### 22.3 learning_question_slots

- id
- target_term_id
- prerequisite_definition_id nullable
- stage
- slot_key
- required_order
- cycle_index nullable
- content_version

### 22.4 learning_questions

- id
- slot_id
- variant_key
- attempt_index
- body
- source_type
- validation_status
- is_active
- generated_at nullable

`source_type`:

- predefined_codex
- runtime_ai_fallback

### 22.5 learning_question_options

- id
- learning_question_id
- body
- is_correct
- misconception_type
- diagnostic_rationale
- linked_prerequisite_keys
- remediation_focus
- default_order

副次誤概念タイプ列は不要とする。

### 22.6 learning_question_display_orders

- participant_id
- learning_question_id
- option_order
- random_seed
- created_at

### 22.7 generated_learning_materials

- id
- participant_id
- learning_session_id
- target_term_id
- prerequisite_definition_id nullable
- stage
- material_mode
- cycle_index
- slot_key nullable
- attempt_index
- group_condition
- diagnosis_snapshot nullable
- rag_context
- material
- examples
- comparisons
- counterexamples
- rag_sources
- general_knowledge_supplement
- answer_leak_detected
- regeneration_count
- ai_call_log_id
- created_at

### 22.8 learning_choice_attempts

- id
- participant_id
- learning_session_id
- target_term_id
- prerequisite_definition_id nullable
- stage
- slot_key
- question_id
- selected_option_id
- displayed_option_order
- cycle_index
- attempt_index
- is_correct
- misconception_type
- transition_type
- is_persistence
- is_recurrence
- result_status
- forced_answer_shown
- response_time_sec
- material_id
- idempotency_key
- created_at

`result_status`:

- passed
- retry
- forced_resolved
- completed

### 22.9 learning_sessions

追加・変更する主な列:

- content_version
- prerequisite_set_version
- current_stage
- current_prerequisite_key
- current_slot_key
- current_cycle_index
- phase2_attempt_count
- phase2_forced_completion
- completed_at
- technical_block_reason

理解不足による`blocked`、`failed_phase1`、`failed_phase2`は使用しない。

## 23. API設計

### 23.1 セッション開始

```http
POST /api/learning-sessions
```

処理:

1. 対象概念のactive content versionを取得する。
2. 前提用語セットと問題セットのversionをセッションへ固定する。
3. 最初の前提用語教材をAI生成する。
4. 最初の必須問題スロットの第1バリアントを返す。

### 23.2 セッション状態

```http
GET /api/learning-sessions/{session_id}
```

参加者向けResponse例:

```json
{
  "status": "prerequisite",
  "target_term": {
    "label": "Attention"
  },
  "progress": {
    "prerequisite_index": 1,
    "prerequisite_total": 3,
    "required_question_index": 1,
    "required_question_total": 2,
    "attempt_index": 1,
    "max_attempts": 3
  },
  "material": {
    "material_id": "uuid",
    "body": "..."
  },
  "question": {
    "question_id": "uuid",
    "body": "...",
    "options": [
      {
        "option_id": "uuid",
        "label": "A",
        "body": "..."
      }
    ]
  }
}
```

返してはいけないもの:

- is_correct
- misconception_type
- diagnostic_rationale
- linked_prerequisite_keys
- correct_option_id
- remediation_focus

### 23.3 回答

段階別API:

```http
POST /api/learning-sessions/{id}/prerequisite-attempts
POST /api/learning-sessions/{id}/concept-phase1-attempts
POST /api/learning-sessions/{id}/concept-phase2-attempts
```

Request:

```json
{
  "question_id": "uuid",
  "selected_option_id": "uuid"
}
```

`Idempotency-Key`を必須にする。

### 23.4 回答処理

1. 現在のstageとquestion_idが一致するか確認する。
2. selected optionがquestionに属するか確認する。
3. 重複送信を検査する。
4. 選択肢メタデータで採点する。
5. 回答ログを保存する。
6. 正誤表示用データを作る。
7. 必要に応じてAI説明・教材を生成する。
8. backendの固定規則で次状態を決定する。
9. 未使用variantを選ぶ。
10. 不足時はAI追加問題を生成・検証する。

## 24. フロントエンド

### 24.1 共通画面

```text
対象概念名
段階名
進捗
AI教材
固定問題
ラジオ選択肢
回答ボタン
正誤フィードバック
```

### 24.2 前提用語画面

- 前提用語 `2 / 5`
- 必須問題 `1 / 2`
- 試行 `2 / 3`
- AI教材
- 5択問題
- 正誤
- 短い要点または誤答説明

### 24.3 フェーズ1画面

- 必須問題 `1 / 2`
- cycle `2 / 3`
- 試行 `1 / 3`
- AI教材
- 5択問題
- 前提用語reviewへの遷移表示

### 24.4 フェーズ2画面

- 教材を表示しない
- 軽い条件を表示しない
- 問題と選択肢だけを表示する
- 提案群は試行 `1 / 3`
- 統制群は1回のみ

### 24.5 削除するUI

- 学習セッション内textarea
- 理由記述欄
- 自信度
- ambiguous用自由記述
- 記述回答ルーブリック表示

## 25. 評価指標

### 25.1 主指標

- `pretest_score_all_terms`
- `retest_score_all_terms`
- `learning_target_retest_score`
- `non_target_retest_retention_rate`
- `same_misconception_recurrence_rate`
- `m1_recurrence_rate`
- `m2_recurrence_rate`
- `m3_recurrence_rate`
- `no_material_concept_discrimination_accuracy`

`no_material_concept_discrimination_accuracy`を、旧`concept_phase2_success_rate`の研究上の名称として扱う。

### 25.2 学習中指標

#### 前提用語必須問題正答率

```text
prerequisite_required_question_accuracy =
正答した前提用語必須問題スロット数 /
全前提用語必須問題スロット数
```

#### 前提用語初回正答率

```text
prerequisite_first_attempt_accuracy =
初回正答スロット数 /
全前提用語必須問題スロット数
```

#### 前提用語再支援後回復率

```text
prerequisite_retry_recovery_rate =
初回誤答後に自力正答したスロット数 /
初回誤答スロット数
```

#### 前提用語強制解決率

```text
prerequisite_forced_resolution_rate =
forced_resolvedスロット数 /
全前提用語必須問題スロット数
```

#### フェーズ1全問自力通過率

```text
phase1_all_questions_pass_rate =
全必須問題をforced_resolvedなしで通過したセッション数 /
phase1実施セッション数
```

#### フェーズ1強制解決率

```text
phase1_forced_resolution_rate =
1件以上forced_resolvedを含むphase1セッション数 /
phase1実施セッション数
```

#### 教材なし概念弁別正答率

```text
no_material_concept_discrimination_accuracy =
phase2正答数 /
phase2回答数
```

#### フェーズ2再支援後正答率

```text
phase2_after_retry_success_rate =
phase2初回誤答後に後続試行で正答したセッション数 /
phase2初回誤答セッション数
```

#### フェーズ2強制完了率

```text
phase2_forced_completion_rate =
phase2を3回誤答して正答提示を受けたセッション数 /
proposedのphase2実施セッション数
```

### 25.3 Mタイプ推移

分析する。

- 事前テストMタイプ
- 前提用語Mタイプ
- フェーズ1Mタイプ
- フェーズ2Mタイプ
- 再テストMタイプ
- persistence
- transition
- recurrence
- resolution

### 25.4 削除する指標

- independent_explanation_success
- 記述回答ルーブリックスコア
- 前提用語の文章内使用率
- 自由記述説明品質
- concept_phase2を説明能力として扱う指標

## 26. 問題項目分析

固定選択式へ変更するため、次を分析できる。

- 問題別正答率
- 必須問題スロット別正答率
- variant別正答率
- 選択肢別選択率
- M1/M2/M3/unknown選択率
- 群別項目正答率
- 正答位置別選択偏り
- 初回正答率
- 再試行正答率
- forced_resolved率
- 回答時間
- predefined問題とAI追加問題の成績差

## 27. AI障害と問題不足

### 27.1 AI教材生成失敗

- セッションを停止する。
- Mockへ自動フォールバックしない。
- 問題だけを先に表示しない。
- `material_generation_failed`を保存する。
- 研究者または参加者が再試行する。
- 同じ回答ログを重複作成しない。

### 27.2 RAG取得失敗

一般知識の補足は許可するが、RAG取得自体に失敗した場合は、実験条件が変化するためセッションを停止する。

### 27.3 問題バンク不足

- AIが追加問題を生成する。
- schema検証、正答数検証、M分類検証、類似度検証を行う。
- 検証に通過した問題だけを表示する。
- `runtime_ai_fallback`としてログへ残す。
- 分析では事前作成問題と区別する。

## 28. 内容バージョンと再現性

保存するもの:

- 前提用語セットversion
- 問題セットversion
- 再テストversion
- YAML/JSONのfile hash
- question source type
- validation status
- 実際の表示順
- selected option ID
- 正誤
- Mタイプ
- response time
- AI教材全文
- AI教材生成payload
- RAG chunk IDとscore
- 一般知識補足
- answer leak検査結果
- AI backend
- model
- AI call log ID
- forced answer表示の有無

進行中参加者は、開始時点のversionを最後まで維持する。

## 29. Attentionを例にした流れ

固定設定例:

```text
対象概念: Attention
前提用語:
  1. トークン
  2. トークン間の関係
  3. 重み付け

各前提用語:
  必須問題2件
  各問題最大3試行

フェーズ1:
  必須問題2件
  各問題最大3試行

フェーズ2:
  提案群最大3回
  統制群1回
```

### 29.1 提案群

1. 事前テストでAttentionのM3を選ぶ。
2. Attentionが学習対象になる。
3. 固定前提用語「トークン」を開始する。
4. AIはM3診断、RAG、一般知識を使って教材を生成する。
5. トークン必須問題1を出す。
6. M2誤答なら不正解を表示し、AIが混同理由を説明する。
7. AIがM2向け再教材を生成する。
8. 必須問題1の別バリアントを出す。
9. 正答後、必須問題2を出す。
10. 両問題を完了して次の前提用語へ進む。
11. 全前提用語完了後、フェーズ1教材を生成する。
12. フェーズ1必須問題2件を順に行う。
13. 誤答選択肢に紐づく前提用語へreviewとして戻る。
14. review後、フェーズ1の未使用バリアントへ進む。
15. フェーズ1全スロット完了後、教材を隠す。
16. フェーズ2固定問題を出す。
17. 誤答ならフェーズ1へ戻り、AI再教材を表示する。
18. 後続フェーズ2で正答すればcompletedとなる。
19. 3回誤答した場合は正答を提示してcompletedとなる。

### 29.2 統制群

1. 同じ固定前提用語、同じ必須問題を使用する。
2. AIは事前診断や累積M履歴を使わず一般教材を生成する。
3. 前提用語の各必須問題を最大3回行う。
4. 誤答時は現在選択した誤答への一般説明と再教材を受ける。
5. 3回誤答なら正答を提示して次へ進む。
6. フェーズ1も各必須問題を最大3回行う。
7. フェーズ1誤答時に前提用語へ戻らない。
8. フェーズ2は教材なしで1回だけ行う。
9. 正答でも誤答でもcompletedとなる。

## 30. 実装変更対応表

| 現行 | 確定後設計 |
|---|---|
| AIが前提用語3件を生成 | YAML/JSONの固定前提用語を全件使用 |
| 前提用語数は3件固定 | 対象概念ごとに可変 |
| AIが前提用語教材・質問を生成 | AIは教材だけ生成、質問は固定 |
| 前提用語は記述式 | 5択式 |
| 前提用語1件につき1質問 | 必須問題2件 |
| 提案群前提用語最大2回 | 両群とも各必須問題最大3回 |
| 2回failでblocked | 3回誤答で正答提示し次へ |
| AIがフェーズ1質問を生成 | 固定必須問題を複数出題 |
| フェーズ1は記述式 | 5択式 |
| 3回failでfailed_phase1 | 3回誤答で正答提示し次へ |
| 統制群フェーズ1は1回 | 統制群も各必須問題最大3回 |
| AIがフェーズ2質問を生成 | 固定問題バリアント |
| フェーズ2は記述式 | 5択式 |
| 提案群3回failでfailed_phase2 | 3回誤答で正答提示してcompleted |
| 統制群phase2は1回 | 維持 |
| 学習対象だけ再テスト | 全5概念を再テスト |
| retest_v1 | 再改訂したretest_v2 |
| Python seed中心 | YAML/JSON import |
| 問題不足で停止 | AI追加問題を生成・検証 |

## 31. テスト計画

### 31.1 コンテンツ

- YAML/JSON schemaが有効である。
- 対象概念ごとに前提用語数を可変設定できる。
- 各前提用語に必須問題2スロットがある。
- 各スロットに3バリアント以上ある。
- フェーズ1に必須問題2スロットがある。
- 各cycle・slotに必要なバリアントがある。
- フェーズ2に3バリアントがある。
- 各問題がcorrect/M1/M2/M3/unknownを持つ。
- 正答が1件だけである。
- 各誤答に主要Mタイプが1件だけある。
- linked prerequisite keyが実在する。
- versionとhashが保存される。

### 31.2 Backend

- セッション開始時にAIが前提用語を選ばない。
- activeな固定前提用語を全件読み込む。
- 順序が固定される。
- 選択肢表示順が参加者ごとにランダム化・保存される。
- option metadataだけで採点できる。
- 正答直後に短い要点を返す。
- 誤答直後に正答を漏らさず不適切理由を返す。
- 各必須問題で最大3回が機能する。
- 3回誤答時に正答提示とforced_resolvedが保存される。
- 提案群phase1誤答時に固定リンク先の前提用語へ戻る。
- 統制群phase1誤答時は前提用語へ戻らない。
- 提案群phase2誤答時はphase1へ戻る。
- 提案群phase2第3誤答で正答提示後completedになる。
- 統制群phase2は1回でcompletedになる。
- blocked/failed_phase1/failed_phase2を理解不足終端として使わない。
- AI教材の正答漏洩検出と再生成が動く。
- 問題不足時にAI追加問題を生成・検証する。
- 統制群payloadに事前診断と累積ログが入らない。
- 再テストが全5概念を返す。

### 31.3 Frontend

- 学習セッションにtextareaがない。
- すべて5択ラジオボタンである。
- 未選択では送信できない。
- 正誤が即時表示される。
- 正答時は短い要点が表示される。
- 誤答時は不適切理由が表示される。
- 1回目・2回目の誤答では正答が表示されない。
- 3回目の誤答では正答が表示される。
- 前提用語、必須問題、試行回数の進捗が表示される。
- フェーズ2では教材と軽い条件が表示されない。
- M1/M2/M3が表示されない。

### 31.4 評価

- 全5概念の再テスト正答率を計算できる。
- 学習対象だけの再テスト正答率も計算できる。
- 学習対象外概念の維持率を計算できる。
- forced_resolvedと自力正答を区別できる。
- 教材なし概念弁別正答率を計算できる。
- 学習中から再テストまでのMタイプ遷移を集計できる。
- predefined問題とAI追加問題を分けて集計できる。

## 32. 内容妥当性

Codexが問題を完全作成し、専門家確認前でも実装する。

ただし、本実験前には次を行う。

- 専門家による正答一意性確認
- M1/M2/M3分類の確認
- 前提用語と問題の対応確認
- 問題バリアント間の難易度確認
- 正答文だけが長くならないかの確認
- 語調から正答を推測できないかの確認
- 認知インタビュー

確認前の問題で取得したデータと、承認後の問題で取得した本実験データを混在させない。

## 33. 設計上の注意点

1. フェーズ2は説明能力ではなく概念弁別を測る。
2. 選択肢に含まれない誤概念は観測できない。
3. 前提用語数と必須問題数により、実験時間が大きくなる。
4. 最大問題数は旧見積りの約110問より増える。
5. 正答提示で進んだ参加者と自力正答者を区別する必要がある。
6. 統制群にも再試行と即時フィードバックがあるため、群間差は「支援の有無」ではなく「累積ログ適応の有無」である。
7. AI追加問題は再現性を下げるため、source typeを必ず保存する。
8. AI教材の一般知識補足は、RAG由来情報と分けて記録する。
9. 教材文字数をAIに任せるため、予備実験で所要時間を確認する。
10. 3回誤答時の正答提示は、後続成績へ直接影響する可能性があるため、分析時に明示する。

## 34. 確定事項一覧

1. フェーズ2は教材なし概念弁別を測る。
2. 研究目的を概念弁別・誤概念回避能力へ変更する。
3. 通常AI対ログ適応型AIの二群比較を維持する。
4. 事前アンケート、L0、転移テストは実施しない。
5. 事前テスト正答概念は学習対象外とする。
6. M1〜M3とunknownは全件学習対象とする。
7. 学習対象は最大5概念とする。
8. 前提用語は概念別固定セットとする。
9. 前提用語数は概念ごとに可変とする。
10. 設定前提用語は全件出題する。
11. 出題順は固定する。
12. 研究者は前提用語名と順序だけを設定する。
13. 両群で同じ前提用語を使う。
14. 統制群の一般小問を固定前提用語へ置き換える。
15. 学習問題はすべて5択とする。
16. unknownを全問題に入れる。
17. M1/M2/M3を事前設定する。
18. 選択肢には主要Mタイプだけを設定する。
19. 選択肢順はランダム化して保存する。
20. 両群で同じ問題を使う。
21. Codexが問題を作成する。
22. 専門家確認前でもprovisionalとして実装できる。
23. 学習中は正誤を即時表示する。
24. 正答時は短い要点を表示する。
25. 誤答時はAIが不適切理由を説明する。
26. 1〜2回目の誤答では正答を教えない。
27. 各必須問題は最大3回とする。
28. 誤答時は別バリアントを使う。
29. 3回誤答時は正答提示して進む。
30. 統制群も前提用語問題を最大3回行う。
31. 前提用語は必須2問、フェーズ1も複数必須問題とする。
32. フェーズ1の各必須問題は最大3回とする。
33. 提案群フェーズ1誤答時は前提用語へ戻る。
34. 戻り先は選択肢へ事前設定する。
35. reviewでは未使用バリアントを使う。
36. フェーズ1上限時は正答提示してフェーズ2へ進む。
37. 統制群フェーズ1も最大3回後に正答提示して進む。
38. フェーズ2回答前には教材を表示しない。
39. フェーズ2に軽い条件は表示しない。
40. 提案群フェーズ2誤答時はフェーズ1へ戻る。
41. 再教材はフェーズ1画面で表示する。
42. 提案群フェーズ2は最大3回とする。
43. 各回で別バリアントを使う。
44. 第3誤答時は正答提示して完了する。
45. 統制群フェーズ2は1回で完了する。
46. AI教材は参加者ごとに毎回生成する。
47. 提案群初回教材へ事前Mタイプを反映する。
48. 前提用語教材にも事前テスト誤答を使う。
49. 一般知識補足を許可する。
50. 例、比較、反例を許可する。
51. 教材長はAIに任せる。
52. 正答文漏洩時は自動再生成する。
53. AI失敗時は停止して再試行する。
54. 必要な固定問題数を許容する。
55. 現行上限を維持する。
56. 問題不足時はAIが追加問題を生成する。
57. 再テストは全5概念を出す。
58. 再テストを新設計に合わせて改訂する。
59. 学習中から再テストまでのM推移を分析する。
60. フェーズ2指標を教材なし概念弁別正答率へ変更する。
61. 記述能力指標を削除する。
62. 前提用語・問題セットをversion管理する。
63. 旧問題を非activeで残す。
64. 進行中参加者は開始時versionを維持する。
65. 固定コンテンツはYAML/JSONで管理する。

## 35. 実装前提として採用した解釈

回答内容には、複数問題制と最大3回制を同時に成立させるため、試行回数の単位を明確にする必要がある。

本書では次のように解釈した。

- 前提用語は必須問題2スロットを持つ。
- 最大3回は前提用語全体ではなく、各必須問題スロットに適用する。
- フェーズ1も必須問題2スロットを初期設定とする。
- 最大3回は各フェーズ1必須問題スロットに適用する。
- 3回誤答後は正答提示により`forced_resolved`とし、全スロット完了後に次フェーズへ進む。
- 統制群は前提用語・フェーズ1で同じ試行数を持つが、前提用語への適応的戻りと累積Mログによる教材変更は行わない。
- 統制群フェーズ2だけは回答どおり1回で完了する。

この解釈により、「複数問すべてを正答しなければ進めない」という通常規則と、「3回誤答した場合は正答を提示して進む」という上限規則を両立させる。
