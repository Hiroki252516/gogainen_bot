# AI指示の目標と現行契約

## 現行条件（仕様版41：教材内解説・目標800文字・提案群専用指示）

仕様版41では新規参加者を`integrated_material`に固定し、辞書v4のterm/definitionを`glossary_reference`として両群共通の教材生成入力に含める。定義文は転載用ではなく意味を確認する参照情報として扱い、教材文脈に合わせて自然に言い換え、実際に使う登録語だけを説明し、定義にない性質を加えないよう指示する。教材本文は800文字程度を目安とし、上下限を設けない。文字数だけを理由に生成を拒否・再試行しない。実文字数と目標だけを新しい監査記録に残す。

この入力は両群で同じ形で投影し、群専用の診断・教授情報とは分離する。統制群に群別の自然言語方略指示は加えず、提案群だけに診断・タイプ別教授方略指示を加える。`TutorTurn.diagnosis_json.material_glossary`のsnapshotは引き続き保存するが、新規教材では参加者画面の教材用語注釈欄を表示しない。回答後解説のsnapshot・注釈表示は従来どおり。辞書全項目を本文へ列挙する指示ではなく、AIが実際にどの用語を説明したか、定義が意味的に正しいかは機械検査で保証しない。仕様版40以下の参加者のモード、教材、snapshot、監査記録は変更しない。

## 用語注釈と生成契約の境界（仕様版26導入・版41現行）

実験仕様版26で導入した注釈はbackendの固定辞書処理である。仕様版41の新規参加者は教材内解説に固定されるため、辞書v4を両群共通の`glossary_reference`として教材生成へ渡す。教材注釈snapshotは保存するが、教材本文や回答後解説へ自動挿入せず、共通回答履歴にも加えない。生成Schemaと契約v7は維持する。出現語・説明文の保存と再現は[24](24_learning_glossary.md)を参照し、逐語転載を避ける指示は[43](43_glossary_definition_paraphrase.md)に記録する。

Wordと実装判断を[20](20_experiment_plan_alignment.md)に記録する。仕様版39までは計画書6.7.2の統制群指示を送っていたが、仕様版40では削除した。現在は6.7.1の共通指示と6.7.3の提案群指示を適用する。unknownの証拠Schema・taxonomy・検査・Mockも維持する。抜粋と、各入力・Schemaを含む完全な実送信promptを区別する。

## 目標プロンプトと現行原文

### 計画書の指示文の抜粋（仕様版39までの適用）

以下の統制群指示は計画書6.7.2の原文であり、仕様版39まで適用した。仕様版40では統制群の群別自然言語指示としては送信しない。

以下は計画書6.7の抜粋である。6.7.1は現行の共通指示、6.7.2は仕様版39までの履歴、6.7.3は現行の提案群指示に対応する。いずれも完全な送信promptではなく、共通ルール・個別入力・出力Schema等と組み合わせる。

共通教材指示（6.7.1）:

```text
教材には意味や仕組みの解説を含める。一般的な誤解を正確に説明・訂正してよい。
```

統制群の計画書原文（6.7.2）:

```text
通常のAIチューターとして、共通の用語情報、教材コンテキスト、interaction_historyを使い、今回の学習対象を説明する。
general_explanation は、共通の用語情報、教材コンテキスト、回答履歴に基づいて学習対象を説明する通常の教授方略を意味する。
teaching_strategy は general_explanation に固定する。
```

実験群への指示（6.7.3からの抜粋）:

```text
active_misconception_type、pretest_target、pretest_targets、diagnostic_evidence、session_misconception_historyを、その方略に沿った説明・対比例の具体化に利用し、別方略へ変更しない。
misconception_taxonomyにあるM1/M3/unknownの定義と教授方針を守る。M1は誤信念の反駁、M3はカテゴリー再分類、unknownは基礎説明を行う。
diagnostic_evidence.selected_options がある場合、M1の誤った考えまたはM3の誤カテゴリーは選択肢本文に根拠を置く。
unknownは意味や仕組みを示す。
```

指定方略はM1ならbelief_revision、M3ならcategory_reorientation、unknownならfoundational_explanation。backendが選んだ具体的な値を末尾の固定指示と出力Schemaへ入れる。「backend」はJSONキーではなくプログラム側を指す語であり、その語だけからLLMが内部状態を読めるわけではない。

M1/M3の対象主張・訂正・仕組み・対比例、適用確認と本文証拠は維持する。unknownは旧6項目を撤廃し、mandatory_elementsはtype/definitionのみ、既存teaching_contractのmechanism_explanation/transfer_checkと合わせて3点の本文証拠を要求する。unknownの対象ID/訂正/対比例はnullまたは空配列、refutation_modeはnone。

### 現行コードの原文と参照元

下表は現行コードに反映した指示原文の抜粋。パスはリポジトリからの相対位置であり、過去の照合HEADの行番号とは区別する。

| 場所 | 現行原文 |
| --- | --- |
| backend/app/ai/prompts/learning_material.yml | 教材には意味や仕組みの解説を含める。一般的な誤解を正確に説明・訂正してよい。 |
| backend/app/ai/prompts/learning_material.yml（提案群のみ） | `teaching_strategy はbackendで指定された {strategies} に固定する。`。統制群へはこの自然言語指定を送らない。 |
| backend/app/services/experiment.py | 誤概念を推測せず、対象用語の意味や仕組みと、別事例への適用確認を教材本文に含める。 |

教材生成と構造化promptの固定指示文、誤概念taxonomy、タイプ別の必須教授要素、教授方略の固定値は[learning_material.yml](../backend/app/ai/prompts/learning_material.yml)を唯一の設定元とする。モジュール起動時にYAMLを検証して読み込み、`compose_structured_prompt`と`build_tutoring_prompt`が適用条件と動的な値の埋め込みを行う。個別の診断・入力投影、教授要素から作る出力Schema、生成後の検証、方略の選択条件はPython側が担当する。YAMLの文言・定義・値の変更は生成条件の変更として扱う。生成文の意味的な正しさまで機械検査したとは扱わない。

## 教材契約と履歴（版26の基準契約・版29で維持）

現行は実験仕様版41 / `experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`。仕様版26で導入した教材契約`tutoring-teaching-contract-v7-easy-level`、taxonomy `m1-m3-unknown-v3`、共通履歴`interaction-history-v1`、出題規則`shared-diagnosis-route-v1`を維持する。新規参加者には教材内解説を固定し、辞書v4を両群共通入力として渡す。統制群に群別自然言語方略指示を加えず、提案群だけに教授方略の自然言語指示を追加する。出力SchemaとBackend検証は変更せず、統制群のstrategy値は`general_explanation`に固定する。本文は800文字程度を目安とし、文字数による合否判定は行わない。仕様版40以下は閲覧専用。

タスクはgenerate_tutoring_turn、generate_correct_answer_summary、explain_selected_distractorの3つだけ。分類・採点・状態更新・方略決定はbackendが行う。

## 入力と方略

共通入力はterm、component_terms、rag_context、interaction_history。教材内解説モードでは`glossary_reference`を追加する。現在出題する未回答の固定問題・全選択肢・正答を教材生成へ渡さない。既回答の問題本文と選択本文は履歴として利用できる。参加者ID/群名はルーティングとログ照合専用でpromptから除く。

| 入力 | control | proposed |
| --- | --- | --- |
| 用語・構成要素・共通RAG・interaction_history | 共通 | 共通 |
| glossary_reference（教材内解説モードのみ） | 同じ辞書構造 | 同じ辞書構造 |
| active_misconception_type、learner_state、診断要約・診断履歴 | なし | 追加 |
| pretest_target(s)、diagnostic_evidence、訂正メタデータ | なし | 追加 |
| taxonomy、教授方針、必須教授要素、診断由来段階 | なし | 追加 |

仕様版40で導入し、現行仕様版41でも維持する統制群では、`general_explanation`を通常説明として定義する自然言語の方略説明は送らない。これは出力JSONの`teaching_strategy`をSchema enumとBackend検証で固定する内部値である。統制群は共通履歴を利用し、回答から自然に誤りを見つけて訂正することが許容される。比較は明示的な誤概念対応の追加効果であり、統制群が誤概念に全く対応しないことを保証する設計ではない。

interaction_historyは同じ参加者・用語の採点済み事前/再/最終テストと学習確認を全周回から取得する。記録種別、phase/test_round、session_index/turn_index、問題本文、selected_optionsのlabel/body、全体is_correct、表示/回答時刻、回答時間だけを含む。snapshotを優先して復元し、回答時刻または記録時刻で時系列順にする。分類・理由・確信度・段階・方略・再発・訂正メタデータ・内部ID・選択肢別正誤・正答キーは除く。未回答・未利用prefetch・他用語・他参加者を含めない。全文を渡し、暗黙の履歴切り捨てはしない。

AI教材・解説全文は履歴に入れず、過去問題/回答の自動prefix追記もしない。共通履歴と実験群専用情報を別allowlistで投影し、履歴のselected_options内もlabel/bodyだけに制限する。両群で履歴の取得規則は同じだが、参加者ごとの値まで同一にするわけではない。

backend指定方略値はcontrol→general_explanation、M1→belief_revision、M3→category_reorientation、unknown→foundational_explanation。Schemaの`teaching_strategy` enumは当該1つに固定し、不一致を拒否する。仕様版40で値を説明する自然言語テンプレートを提案群だけに追加し、現行仕様版41でもその範囲を維持する。

## 出力検証

両群とも冒頭の `## 用語名` と1つ以上の非空 `###` セクションを要求する。小見出しの文言・数・順序・複数要素のまとめ方はAIに任せ、専用見出しや固定順序を強制しない。従来の見出しを自然に生成してもよい。CommonMarkパーサー（markdown-it-py）で実際の見出しと節本文を解析し、インラインの見出し風文字列、コードブロック・引用内の見出しを教材の節とみなさない。空の節、用語見出しの欠落、内部ラベル露出を拒否する。

proposedの教材はtutor_message、teaching_strategy、mandatory_elements、teaching_contractを持つ。契約項目はtarget_claim_id、addressed_claim_ids、refutation_mode、corrected_claim、mechanism_explanation、contrast_example、transfer_check、target_addressed。

M1は反駁、M3はカテゴリー比較、unknownは基礎説明を生成するよう指示する。transfer_checkは教材内の適用確認であり必須。backendの自動検証は以下の構造・文字列検査であり、教授内容の意味的な正しさを判定するものではない。本文の目標800文字程度は生成時の目安であり、実測長は合否判定・再試行条件に使わない。構造・教授契約・安全性の検証違反時は初回＋最大2回同backendで再生成する。失敗は503。Mockへ切り替えない。更新識別子は`tutoring-prompt-contract-v11-target-800-control-shared-prompt`。

| 区分 | 現行の処理と保証範囲 |
| --- | --- |
| backendの自動検査 | 契約内のtarget_claim_id/addressed_claim_idsが指定対象IDの条件を満たすこと、タイプ別refutation_mode・teaching_strategy、必須フィールドの非空・null条件、target_addressed、証拠文の節本文内出現、用語見出し・非空節・内部ラベルを確認する。証拠一致では空白や一部Markdown記号を正規化する。教材本文の実文字数と目標値は監査するが、文字数で合否を判定しない。 |
| 禁止文字列検査 | 現在の固定確認問題の本文、expected_answer、正解選択肢本文について、各文字列が教材にそのまま含まれる場合を拒否する。言い換えや部分的な手掛かりを意味的に検出する検査ではない。 |
| 入力分離とプロンプト指示 | 直前のAI解説全文を次教材の入力から除き、過去問題・回答・解説の転載、未観察誤概念の創作、正答漏えいをしないよう指示する。入力に渡さないことと、生成文の意味的な混入を判定することは別である。 |
| 研究者の目視確認 | 教材の事実的正しさ、訂正・反駁・カテゴリー比較の妥当性、対象主張への実質的な対応、別事例への適用確認、言い換えによる正答漏えい、意味的な過去解説混入を確認する。これらを自動検証で保証しない。 |

正しいclaim_idを返し、本文とJSONの証拠文が一致していても、その証拠文が研究者確認済みの訂正内容を正しく説明しているとは限らない。現在は訂正文の意味的な同値性や、証拠文が反例として成立するかを検査しない。生成検証のvalidは機械検査に合格したことを示し、教材内容全体が正しいとの認定ではない。

M1/M3の内部キーとteaching_contractを維持し、unknownのmandatory_elementsだけを上記のtype/definitionへ変更する。証拠文は見出しを除く実際の節本文に存在する必要があり、複数要素が同じ節でよい。JSONだけ・見出しだけ・空欄・本文と不一致の証拠は拒否し、先頭文等で補正しない。構造・証拠・契約・長さを同じ最大3試行内で検査する。統制群に型別契約を要求しない。

正答要約/誤答解説も共通入力を使い、現在の問題・選択内容・表示済み教材を追加する。不正解の現在選択には従来どおり選ばれた誤答本文だけを使う。履歴は現在回答より前の確定分とし、二重掲載しない。proposedだけ診断と教授方針を追加し、固定採点をAI解説で変えない。

### 回答後解説の現行原文の参照

正答/誤答ごとの基本指示は両群共通。正答要約は [codex_app_server_backend.py](../backend/app/ai/codex_app_server_backend.py) の240行目から（指示原文258〜264行目）、誤答解説は273行目から（295〜303行目）。群別入力だけを切り替え、教材生成プロンプト全体をそのまま流用しない。

正答は要点を短くまとめてsummaryを返し、冒頭に「今回の要点」を置くよう指示する。誤答は正答本文・位置を直接示さず、「どこが違うか」「見直す観点」を中心とするfeedbackを生成するよう指示する。これらの内容上の条件を全て自動検査しているわけではない。remediation_focusとgeneral_knowledge_supplementも返すが、現行画面に表示する解説本文はfeedbackだけ。

入力の組立てはbackend/app/services/experiment.py:2453-2496。両群に現在問題・表示済み教材・必要な選択本文・共通履歴・RAGを渡し、実験群だけに現在の誤答タイプ・学習者状態・指針・taxonomy・診断履歴を追加する。pretest_target(s)など教材用入力の全項目を解説にも渡すわけではない。固定の正誤表示はfrontend/app/learning/[termSlug]/page.tsx:404でありAI生成ではない。

確認問題は両群ともshared-diagnosis-route-v1の規則を使い、unknownはenrichment、M1/M3はconceptual_change。同じ状態・回答・ターンなら同じ問題/variant。controlのモデルへこの段階は渡さない。次教材の先行生成では、現在の固定採点・選択・時刻を履歴へ副作用なしに投影し、回答確定後だけ公開する。解説失敗時は生成物を破棄する。

## 監査

AICallLogの既存JSON内に実送信thread/start、turn/start全文、SchemaとSHA-256、モデル・推論設定、RAG条件/chunk本文hash、版、試行・検証、生応答を保存する。interaction-history-v1の件数とSHA-256、出題規則版、モデル入力投影も記録する。controlのinstruction_routeはshared_history_general、proposedはshared_history_diagnostic。認証情報を保存しない。Mock入力を実送信として扱わない。TutorTurnにも版・履歴指紋・契約・検証を保存する。

監査ログ・CSVを研究者限定で取り扱うことは運用方針である。現行管理APIに管理者認証・権限確認はなく、アクセスがシステムで制限されているとはみなさない。[セキュリティ仕様](15_security_privacy.md) に未解決事項を記載する。

`AICallLog.response_payload.generation_validation.material_structure` と `TutorTurn.diagnosis_json.material_structure_validation` に、headings（表示順）、section_count、sectionsの位置/見出し/本文文字数、evidence_placements（内部フィールド→節番号）、valid/missingを保存する。各生成試行を監査し、成功した最後の検証をTutorTurnに残す。AI出力Schema、公開API、DB列、CSV固定ヘッダは追加しない。Mockの決定論的な章立てはテスト専用で、実AIの見出しを固定する根拠にしない。
