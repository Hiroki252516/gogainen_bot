# 教材・回答後解説の用語注釈

## 目的と比較条件

feature/issue-132の承認済み計画に基づき、通常版・易しい版、実験群・統制群に共通の固定辞書を追加する。注釈は語の意味を補う追加学習支援であり、誤答タイプ別の教授指示ではない。AIの入力・プロンプト・出力Schema・生成契約版・採点・問題バンク・評価式は変更しない。

教材と回答後解説の各文章について、登録された用語を出現順に一度ずつ「用語の補足」として常時表示する。本文・見出しの表示文字列から抽出し、Markdownの装飾をまたぐ語も扱う。リンクの宛先やHTMLの属性は検索対象にしない。Unicode NFKCと英字の大小文字を正規化し、同じ位置では長い別表記を優先する。長い語の一部としてしか出ていない短い語は追加しないが、短い語が別に登場すれば掲載する。英字略語は英数字・アンダースコアに接する部分一致を認めない。

問題・選択肢・事前/再/最終テスト・結果確認画面には注釈を出さない。注釈は教材本文に挿入せず、600〜800文字の検査にも含めない。教材と解説に同じ語が登場した場合は、それぞれの下に掲載する。該当語なしでは補足欄自体を表示しない。

未登録の語はAIで補わない。この辞書だけで全専門語の網羅や初心者への理解しやすさを保証しない。研究者による内容確認・予備調査を行い、収集開始前に表現と範囲を確定する。両群で同じ規則を使うが、生成文に登場する語が違えば表示する語の組合せも異なる。

## 保存・再現・版

実験仕様版11、protocolは `experiment-plan-2026-10-25-pretest-f-wording-v1`、辞書版は `learning-glossary-v1`。新規登録のみ新版を使い、版10以下・NULL・旧protocolは既存の閲覧専用境界で保護する。既存の教材・注釈・回答・評価を補完・再計算しない。

辞書の正本は [learning_glossary_v1.yml](../backend/app/seed/content/learning_glossary_v1.yml)。起動時に版、非空項目、出典、IDと正規化した別表記の一意性を検証する。説明の変更は辞書改訂として版と運用条件を更新し、収集中に同一版の内容を差し替えない。

backendが生成成功後に表示用snapshotを作る。教材分は `TutorTurn.diagnosis_json.material_glossary`、回答後解説分は `TutorTurn.grading_json.feedback_glossary` に、version、dictionary_sha256、entries（id/term/definition）を保存する。指紋は辞書全体をキー順に正規化したJSONのSHA-256。出現順・当時の説明文を保持し、先行生成の消費・再取得・冪等再送で辞書を引き直さない。AI出力本文は変更しない。

未利用の先行生成に注釈snapshotがあっても表示実績には数えない。教材の表示確認は従来のmaterial-viewと先行生成の利用状態で区別する。

教材・回答後解説の既存APIに `glossary: {version, entries: [{id, term, definition}]}` を追加する。出典と辞書指紋は参加者APIに含めない。DB列・新規ルート・管理切替は追加しない。管理ログと統合CSVのvalue_jsonには保存snapshotを出し、CSV固定ヘッダを維持する。注釈snapshotは表示に供した内容の記録であり、読了の証明ではない。注釈はLLMへの入力と共通回答履歴に含めない。

## 固定辞書全文

以下は研究用に平易化した説明であり、出典の逐語引用ではない。「重み」と「パラメーター」は関連するが同義語にまとめない。出典の語義と共通教材の説明に照合し、用語の範囲を本システムで使う文脈に限定する。学習対象の正誤・個人の診断・選択肢の訂正情報としては使わない。

### 重み (`weights`)

AIの内部の計算で、ある情報をどれくらい結果に反映するかに関わる数値。学習の過程で調整されます。

- 別表記: `重み`、`ウェイト`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#weight)

### パラメーター (`parameters`)

AIの動作を決める内部の数値の総称です。学習で調整される重みなどが含まれます。

- 別表記: `パラメーター`、`パラメータ`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#parameter)

### モデル (`model`)

入力された情報を計算で処理し、予測や文章などの結果を出す仕組み。ここでは、学習済みのAIの仕組みを指します。

- 別表記: `モデル`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#model)

### AI（人工知能） (`ai`)

文章を作る、画像を見分けるなど、人の知的な活動に関わる処理をコンピューターで行う技術です。

- 別表記: `AI`、`人工知能`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary#artificial_intelligence)

### LLM（大規模言語モデル） (`llm`)

大量の文章などを使って学習し、入力に応じた文章を作るAIの仕組みです。

- 別表記: `LLM`、`大規模言語モデル`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/generative#large_language_model)

### 事前学習 (`pretraining`)

様々な用途に使うための土台として、大量のデータから言葉の使い方や特徴を学ぶ処理です。

- 別表記: `事前学習`、`事前訓練`、`プレトレーニング`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（30-32）

### 追加学習 (`additional_training`)

すでに学習したAIに対し、さらにデータを使って内部の数値を調整する処理です。

- 別表記: `追加学習`、`追加訓練`、`追加トレーニング`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（34-36）、[Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#training)

### ファインチューニング (`fine_tuning`)

学習済みのAIを特定の用途に合わせるため、その用途のデータを使ってさらに学習させる方法です。

- 別表記: `ファインチューニング`、`ファインチューン`、`ファインチューニング処理`、`fine-tuning`、`fine tuning`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（34-36）

### 推論 (`inference`)

ここでは、学習済みのAIが入力を処理し、予測や回答を作る処理を指します。

- 別表記: `推論`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/fundamentals#inference)

### プロンプト (`prompt`)

AIへ渡す質問や指示、参考となる情報を含む入力のことです。

- 別表記: `プロンプト`
- 確認元: [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/generative#prompt)

### プロンプトエンジニアリング (`prompt_engineering`)

望む回答を得られるよう、AIへ渡す質問や指示、参考情報の書き方を工夫することです。

- 別表記: `プロンプトエンジニアリング`、`prompt engineering`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（38-40）

### RAG（検索拡張生成） (`rag`)

質問に関係する資料を外部から検索し、取り出した情報を使ってAIに回答を作らせる仕組みです。

- 別表記: `RAG`、`検索拡張生成`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（43-45）

### コンテキスト (`context`)

AIが今回の回答を作るときに参照する情報。質問、指示、会話や資料の内容などが含まれます。

- 別表記: `コンテキスト`、`入力文脈`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（26-49）、[Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary/generative#context_window)

### データベース (`database`)

多くの情報を整理して保存し、必要な情報を探したり書き換えたりできるようにした仕組みです。

- 別表記: `データベース`、`DB`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（51-66）

### 知識ベース (`knowledge_base`)

回答や判断に使う情報をまとめた保存先。説明書や案内文などを整理して入れておきます。

- 別表記: `知識ベース`、`ナレッジベース`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（43-66）

### エージェント (`agent`)

与えられた目的に向けて、状況を見ながら次の行動を判断して進める担当のような仕組みです。

- 別表記: `エージェント`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（71-80）

### マルチエージェント (`multi_agent`)

複数の担当がそれぞれ判断し、情報や結果をやり取りしながら課題を進める仕組みです。

- 別表記: `マルチエージェント`、`マルチ・エージェント`、`multi-agent`、`multi agent`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（71-84）

### ツール (`tool`)

検索や計算など、特定の処理を実行するために呼び出して使う機能です。

- 別表記: `ツール`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（180-194）

### タスク (`task`)

調べる、予定を作るなど、達成したい作業や課題のことです。

- 別表記: `タスク`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（74-84）

### タスク分解 (`task_decomposition`)

大きな課題を、調査、比較、まとめなどの小さな作業に分けることです。

- 別表記: `タスク分解`、`タスクの分解`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（180-198）

### ワークフロー (`workflow`)

作業をどの順番で進め、条件によってどこへ進むかを決めた流れのことです。

- 別表記: `ワークフロー`、`ワーク・フロー`
- 確認元: [backend/app/seed/content/standard/learning_content.yml](../backend/app/seed/content/standard/learning_content.yml)（teaching_targets.multi_agent.I）

### 記憶プロセス (`memory_process`)

過去の会話などから必要な情報を保存し、後で取り出したり、新しい内容へ更新したりする処理です。

- 別表記: `記憶プロセス`、`メモリ機能`、`メモリー機能`、`記憶機能`
- 確認元: [rag_agent_knowledge_base/sources/source_01.txt](../rag_agent_knowledge_base/sources/source_01.txt)（47-49,216-222）、[backend/app/seed/content/standard/learning_content.yml](../backend/app/seed/content/standard/learning_content.yml)（terms.memory_process）

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
