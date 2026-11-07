# 教材・回答後解説・テストの用語注釈

## 現行条件（仕様版40）

現行辞書は[learning_glossary_v4.yml](../backend/app/seed/content/learning_glossary_v4.yml)で、仕様版40の新規参加者に適用する。v4はv3を変更せず、RAG（検索拡張生成）をv1の定義・出典・別表記を引き継いで追加する。v1〜v3は履歴として無変更で保持する。既存参加者の辞書snapshot・教材・テスト・回答後解説は記録時の内容を維持し、仕様版39以下は閲覧専用とする。

新規参加者には教材内解説モードを固定し、教材本文は800文字程度を目安にする。上下限による合否判定や長さを理由にした再生成は行わず、実文字数と目標値を監査用に記録する。仕様版39以下の保存済み教材・snapshot・監査記録は変更しない。管理画面の切替UIと設定APIは提供しない。詳細は[41](41_learning_glossary_material_mode.md)・[42](42_learning_glossary_material_length.md)。

辞書の定義文は教材生成時に逐語転載せず、意味を確認する参照情報として渡す。教材では本文の文脈に合う自然な言葉で言い換え、中心的な意味を保ち、定義にない性質を付け加えず、実際に使う登録語だけを説明する。意味の正確さや学習効果を機械検査で実証したとは扱わない。詳しくは[仕様版31の変更](43_glossary_definition_paraphrase.md)と[仕様版36のRAG追加](49_rag_glossary.md)。

## 教材内解説モード（仕様版29の採用時記録）

仕様版29導入時は管理画面で「注釈欄のみ／教材内解説」を選び、新規参加者へ登録時に固定した。既定の「注釈欄のみ」は本書で定義する表示を保ち、辞書をAI入力へ含めない。仕様版30までは「教材内解説」で辞書版`learning-glossary-v2`の16語を両群共通の`glossary_reference`として渡し、本文に実際に現れる登録語だけを説明するよう指示していた。この段落は当時の実装履歴である。現行v4の言い換え要件とRAG追加は冒頭、[43](43_glossary_definition_paraphrase.md)、[49](49_rag_glossary.md)を参照する。

教材内解説モードでは、重複を避けるため教材右側の用語注釈欄を表示しない。一方、`material_glossary` snapshotの生成・保存は続け、管理ログ・CSVで監査できる。回答後解説とテストの注釈、辞書内容・抽出・保存規則は両モード共通で変更しない。仕様版28以下の教材・snapshotは補完・再生成せず閲覧専用にする。[管理・生成・表示条件](41_learning_glossary_material_mode.md)。

この条件差は新規参加者に対する実験条件の変更であり、辞書説明の意味的な正確さや学習者の理解向上を自動検査のみで実証したとは扱わない。研究者による教材確認と予備調査は別途必要である。

## 目的と比較条件

feature/issue-132で導入した固定辞書を、fix/issue-188-tyusyakuのユーザー依頼に従って改訂する。指定9語を除外し、残る16語を両群に共通表示する。教材・回答後解説に加え、事前/再テスト（画面上で再テスト1と表示する内部final_testも含む）を対象にする。AI入力・プロンプト・出力Schema・生成契約版・問題本文・採点・評価式は変更しない。

教材と回答後解説の各文章について、登録された用語を出現順に一度ずつ「用語の補足」として表示する。教材は広い画面では右側の追従欄、狭い画面では開閉パネルに表示し、回答後解説は従来どおり解説の下に表示する。本文・見出しの表示文字列から抽出し、Markdownの装飾をまたぐ語も扱う。リンクの宛先やHTMLの属性は検索対象にしない。Unicode NFKCと英字の大小文字を正規化し、同じ位置では長い別表記を優先する。長い語の一部としてしか出ていない短い語は追加しないが、短い語が別に登場すれば掲載する。英字略語は英数字・アンダースコアに接する部分一致を認めない。

テストでは用語見出し・問題文・全選択肢を表示順につなぎ、登録語を一度ずつ抽出して教材と同様に右側の追従欄または開閉パネルに表示する。選択・正誤・診断によって項目を変えず、誤答選択肢だけに登場した語も対象にする。確認問題自体と結果確認画面には追加しない。テスト注釈は本文へ挿入しない。教材本文のモード別文字数条件は[42](42_learning_glossary_material_length.md)を参照する。空配列・旧snapshot欠落時は補足欄を出さない。表示位置の変更は進行中の参加者にも適用されるため、実験途中の適用は条件変更として記録する。

現行の除外語はAI（人工知能）、事前学習、ファインチューニング、プロンプトエンジニアリング、データベース、マルチエージェント、タスク、記憶プロセスの8語。RAG（検索拡張生成）は仕様版36で注釈対象に追加した。excluded_aliasesにはプロンプトエンジニアリング・マルチエージェントの別表記を登録し、残したプロンプト・エージェントへの部分一致を抑える。除外語は単独で登場した場合には補足し、タスク分解など指定されていない語は維持する。

未登録の語はAIで補わない。この辞書だけで全専門語の網羅や初心者への理解しやすさを保証しない。研究者による内容確認・予備調査を行い、収集開始前に表現と範囲を確定する。両群で同じ規則を使うが、生成文に登場する語が違えば表示する語の組合せも異なる。

## 保存・再現・版

実験仕様版26、protocolは `experiment-plan-2026-10-27-test-glossary-v2`、当時の辞書版は `learning-glossary-v2`。この節は導入時の履歴であり、現行版境界は仕様版36で35以下を閲覧専用とする。旧教材・注釈・回答・評価を補完・再計算しない。旧仕様版25のテスト結果復元にはscenario-actions-v9を指定し、問題バンク自体は変更しない。

`learning_glossary_v2.yml`は版26の履歴辞書として無変更で保持し、旧25語の[learning_glossary_v1.yml](../backend/app/seed/content/learning_glossary_v1.yml)、v3も履歴用に保持する。現行正本は冒頭に記したv4である。起動時に版・非空項目・出典・ID・正規化した別表記の一意性と、除外語の型・競合を検査する。指紋にはexcluded_aliasesも含める。同じ辞書版の説明・除外語は変更せず、対象変更時は新しい辞書版を追加する。

backendが生成成功後に表示用snapshotを作る。教材分は `TutorTurn.diagnosis_json.material_glossary`、回答後解説分は `TutorTurn.grading_json.feedback_glossary` に、version、dictionary_sha256、entries（id/term/definition）を保存する。指紋は辞書全体をキー順に正規化したJSONのSHA-256。出現順・当時の説明文を保持し、先行生成の消費・再取得・冪等再送で辞書を引き直さない。AI出力本文は変更しない。

未利用の先行生成に注釈snapshotがあっても表示実績には数えない。教材の表示確認は従来のmaterial-viewと先行生成の利用状態で区別する。

教材・解説と各テスト問題の既存APIへ `glossary: {version, entries: [{id, term, definition}]}` を返す。出典・辞書指紋・正答・分類情報は公開しない。仕様版26時点では新規ルート・管理切替を追加しなかった。仕様版29では教材生成モードの管理APIを追加するが、テスト注釈のAPI・snapshotは変更しない。テスト用にnullableなAttempt.glossary_snapshot（SQLiteはJSON、PostgreSQLはJSONB）を追加し、旧行はNULLのまま保持する。

テストの未回答GETはDBへ書き込まず、不変の現行辞書v4と固定問題から導出する。回答時に同じ本文・全表示選択肢から辞書版・指紋・表示順・説明文を保存し、回答済みの再取得・冪等再送で再計算しない。未回答の再読み込み・backend再起動でも同じ辞書・問題なら同じ一覧となる。これは読了・表示の証明ではなく、未回答の注釈閲覧イベントも追加しない。

管理ログはtest_glossary、教材/解説は従来のmaterial_glossary/feedback_glossaryを出し、統合CSVのvalue_jsonにも保存値を含める。CSV固定ヘッダは維持する。欠落時は後付けしない。既定モードでは注釈をLLM入力・共通回答履歴へ追加しない。教材内解説モードでのみ、明示的な任意入力`glossary_reference`を教材生成へ渡す。共通回答履歴には追加しない。

## 測定上の注意

テスト時の補足は用語の意味を提供する支援であり、特定選択肢の正解や診断を示さないが、解答の判断材料になり得る。両群共通の条件として収集し、従来のテスト注釈なし条件の得点と混ぜない。注釈の個別効果・理解しやすさを機械検査だけで実証したとは扱わない。

## 固定辞書全文（現行v4・17語）

以下は研究用に平易化した説明であり、出典の逐語引用ではない。「重み」と「パラメーター」は関連するが同義語にまとめない。出典の語義と共通教材の説明に照合し、用語の範囲を本システムで使う文脈に限定する。学習対象の正誤・個人の診断・選択肢の訂正情報としては使わない。

### 重み (`weights`)

AIが文章を作るための計算に使う数値です。学習によってこの数値が調整されると、AIが選ぶ言葉や回答の仕方が変わることがある

- 別表記: `重み`、`ウェイト`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#weight)

### パラメーター (`parameters`)

AIの動作を決める内部の数値の総称です。学習で調整される重みなどが含まれます。

- 別表記: `パラメーター`、`パラメータ`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#parameter)

### モデル (`model`)

AI本体を指す

- 別表記: `モデル`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#model)

### LLM（大規模言語モデル） (`llm`)

大量の文章などを使って学習し、入力に応じた文章を作るAIの仕組みです。

- 別表記: `LLM`、`大規模言語モデル`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/generative#large_language_model)

### 追加学習 (`additional_training`)

既に学習したAIに、新しい学習用データを使ってさらに学習させ、回答の仕方などを目的に合わせて調整すること

- 別表記: `追加学習`、`追加訓練`、`追加トレーニング`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（34-36）、[Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#training)

### 推論 (`inference`)

ここでは、学習済みのAIが入力を処理し、予測や回答を作る処理を指します。

- 別表記: `推論`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#inference)

### プロンプト (`prompt`)

AIへ渡す質問や指示、参考となる情報を含む入力のことです。

- 別表記: `プロンプト`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/generative#prompt)

### コンテキスト (`context`)

AIが今回の回答を作るときに参照する情報。質問、指示、会話や資料の内容などが含まれます。

- 別表記: `コンテキスト`、`入力文脈`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（26-49）、[Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/generative#context_window)

### 知識ベース (`knowledge_base`)

回答や判断に使う情報をまとめた保存先。説明書や案内文などを整理して入れておきます。

- 別表記: `知識ベース`、`ナレッジベース`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（43-66）

### エージェント (`agent`)

与えられた目的に向けて、状況を見ながら次の行動を判断して進めるAI

- 別表記: `エージェント`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（71-80）

### ツール (`tool`)

検索や計算など、特定の処理を実行するために呼び出して使う機能です。

- 別表記: `ツール`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（180-194）

### タスク分解 (`task_decomposition`)

大きな課題を、調査、比較、まとめなどの小さな作業に分けることです。

- 別表記: `タスク分解`、`タスクの分解`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（180-198）

### ワークフロー (`workflow`)

作業をどの順番で進め、条件によってどこへ進むかを決めた流れのことです。

- 別表記: `ワークフロー`、`ワーク・フロー`
- 確認元: [backend/app/seed/content/standard/learning_content.yml](../backend/app/seed/content/standard/learning_content.yml)（teaching_targets.multi_agent.I）

### 永続化 (`persistence`)

今回の処理や会話が終わった後でも使えるよう、情報を保存先に残しておくことです。

- 別表記: `永続化`、`永続保存`
- 確認元: [rag_agent_knowledge_base/sources/source_02.txt](../rag_agent_knowledge_base/sources/source_02.txt)（64-76）

### ベクトル (`vector`)

ここでは、文章などの特徴を表すために、複数の数値をひとまとめにしたものを指します。

- 別表記: `ベクトル`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（64-66）、[Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary#vector)

### 埋め込み (`embedding`)

文章などの特徴を数値の並びで表すこと。意味や特徴が近い情報を探す際などに使います。

- 別表記: `埋め込み`、`埋込み`、`エンベディング`、`エンベッディング`、`embedding`、`embeddings`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（64-66）、[Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary#embedding)

### RAG（検索拡張生成） (`rag`)

質問に関係する資料を外部から検索し、取り出した情報を使ってAIに回答を作らせる仕組みです。

- 別表記: `RAG`、`検索拡張生成`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（43-45）
