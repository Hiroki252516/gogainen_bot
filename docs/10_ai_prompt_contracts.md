# 現行AI契約

実験仕様版は3、契約版は `tutoring-teaching-contract-v5-dynamic-sections`、taxonomy版は `m1-m3-unknown-v2`。共通履歴はinteraction-history-v1、共通出題規則はshared-diagnosis-route-v1のまま。

タスクはgenerate_tutoring_turn、generate_correct_answer_summary、explain_selected_distractorの3つだけ。分類・採点・状態更新・方略決定はbackendが行う。

## 入力と方略

共通入力はterm、component_terms、rag_context、interaction_history。現在出題する未回答の固定問題・全選択肢・正答を教材生成へ渡さない。既回答の問題本文と選択本文は履歴として利用できる。参加者ID/群名はルーティングとログ照合専用でpromptから除く。

| 入力 | control | proposed |
| --- | --- | --- |
| 用語・構成要素・共通RAG・interaction_history | 共通 | 共通 |
| active_misconception_type、learner_state、診断要約・診断履歴 | なし | 追加 |
| pretest_target(s)、diagnostic_evidence、訂正メタデータ | なし | 追加 |
| taxonomy、教授方針、必須教授要素、診断由来段階 | なし | 追加 |

general_explanationは、backendの明示的診断・タイプ別教授方針によらず共通履歴を利用する通常説明としてプロンプト内で定義する。回答から自然に誤りを見つけて訂正することは許容する。比較は明示的な誤概念対応の追加効果であり、統制群が誤概念に全く対応しないことを保証する設計ではない。

interaction_historyは同じ参加者・用語の採点済み事前/再/最終テストと学習確認を全周回から取得する。記録種別、phase/test_round、session_index/turn_index、問題本文、selected_optionsのlabel/body、全体is_correct、表示/回答時刻、回答時間だけを含む。snapshotを優先して復元し、回答時刻または記録時刻で時系列順にする。分類・理由・確信度・段階・方略・再発・訂正メタデータ・内部ID・選択肢別正誤・正答キーは除く。未回答・未利用prefetch・他用語・他参加者を含めない。全文を渡し、暗黙の履歴切り捨てはしない。

AI教材・解説全文は履歴に入れず、過去問題/回答の自動prefix追記もしない。共通履歴と実験群専用情報を別allowlistで投影し、履歴のselected_options内もlabel/bodyだけに制限する。両群で履歴の取得規則は同じだが、参加者ごとの値まで同一にするわけではない。

backend指定方略はcontrol→general_explanation、M1→belief_revision、M3→category_reorientation、unknown→foundational_explanation。Schemaのteaching_strategy enumは当該1つに固定し、不一致を拒否する。

## 出力検証

両群とも冒頭の `## 用語名` と1つ以上の非空 `###` セクションを要求する。小見出しの文言・数・順序・複数要素のまとめ方はAIに任せ、専用見出しや固定順序を強制しない。従来の見出しを自然に生成してもよい。CommonMarkパーサー（markdown-it-py）で実際の見出しと節本文を解析し、インラインの見出し風文字列、コードブロック・引用内の見出しを教材の節とみなさない。空の節、用語見出しの欠落、内部ラベル露出を拒否する。

proposedの教材はtutor_message、teaching_strategy、mandatory_elements、teaching_contractを持つ。契約項目はtarget_claim_id、addressed_claim_ids、refutation_mode、corrected_claim、mechanism_explanation、contrast_example、transfer_check、target_addressed。

M1は反駁、M3はカテゴリー比較、unknownは基礎説明を生成するよう指示する。transfer_checkは教材内の適用確認であり必須。backendの自動検証は以下の構造・文字列検査であり、教授内容の意味的な正しさを判定するものではない。600〜800文字、700文字前後を維持する。検証違反時は初回＋最大2回同backendで再生成し、失敗は503。Mockへ切り替えない。

| 区分 | 現行の処理と保証範囲 |
| --- | --- |
| backendの自動検査 | 契約内のtarget_claim_id/addressed_claim_idsが指定対象IDの条件を満たすこと、タイプ別refutation_mode・teaching_strategy、必須フィールドの非空・null条件、target_addressed、証拠文の節本文内出現、用語見出し・非空節・内部ラベル、教材文字数を確認する。証拠一致では空白や一部Markdown記号を正規化する。 |
| 禁止文字列検査 | 現在の固定確認問題の本文、expected_answer、正解選択肢本文について、各文字列が教材にそのまま含まれる場合を拒否する。言い換えや部分的な手掛かりを意味的に検出する検査ではない。 |
| 入力分離とプロンプト指示 | 直前のAI解説全文を次教材の入力から除き、過去問題・回答・解説の転載、未観察誤概念の創作、正答漏えいをしないよう指示する。入力に渡さないことと、生成文の意味的な混入を判定することは別である。 |
| 研究者の目視確認 | 教材の事実的正しさ、訂正・反駁・カテゴリー比較の妥当性、対象主張への実質的な対応、別事例への適用確認、言い換えによる正答漏えい、意味的な過去解説混入を確認する。これらを自動検証で保証しない。 |

正しいclaim_idを返し、本文とJSONの証拠文が一致していても、その証拠文が研究者確認済みの訂正内容を正しく説明しているとは限らない。現在は訂正文の意味的な同値性や、証拠文が反例として成立するかを検査しない。生成検証のvalidは機械検査に合格したことを示し、教材内容全体が正しいとの認定ではない。

mandatory_elementsとteaching_contractの内部キー・対象IDの条件・型別フィールドは維持する。証拠文はどの節でもよいが、見出しを除く実際の節本文に存在する必要がある。複数要素が同じ節に存在してよい。JSONだけの証拠、見出しだけの証拠、空フィールド、本文に同じ証拠文字列がない要約は拒否し、先頭文や任意の適用らしい行で補正しない。構造・証拠一致・契約・長さの検査は同じ最大3試行内で行う。統制群には型別必須要素や契約を要求せず、本文構造・文字数・禁止文字列・指定方略の検査を共通に適用する。

正答要約/誤答解説も共通入力を使い、現在の問題・選択内容・表示済み教材を追加する。不正解の現在選択には従来どおり選ばれた誤答本文だけを使う。履歴は現在回答より前の確定分とし、二重掲載しない。proposedだけ診断と教授方針を追加し、固定採点をAI解説で変えない。

確認問題は両群ともshared-diagnosis-route-v1の規則を使い、unknownはenrichment、M1/M3はconceptual_change。同じ状態・回答・ターンなら同じ問題/variant。controlのモデルへこの段階は渡さない。次教材の先行生成では、現在の固定採点・選択・時刻を履歴へ副作用なしに投影し、回答確定後だけ公開する。解説失敗時は生成物を破棄する。

## 監査

AICallLogの既存JSON内に実送信thread/start、turn/start全文、SchemaとSHA-256、モデル・推論設定、RAG条件/chunk本文hash、版、試行・検証、生応答を保存する。interaction-history-v1の件数とSHA-256、出題規則版、モデル入力投影も記録する。controlのinstruction_routeはshared_history_general、proposedはshared_history_diagnostic。認証情報を保存しない。Mock入力を実送信として扱わない。TutorTurnにも版・履歴指紋・契約・検証を保存する。

監査ログ・CSVを研究者限定で取り扱うことは運用方針である。現行管理APIに管理者認証・権限確認はなく、アクセスがシステムで制限されているとはみなさない。[セキュリティ仕様](15_security_privacy.md) に未解決事項を記載する。

`AICallLog.response_payload.generation_validation.material_structure` と `TutorTurn.diagnosis_json.material_structure_validation` に、headings（表示順）、section_count、sectionsの位置/見出し/本文文字数、evidence_placements（内部フィールド→節番号）、valid/missingを保存する。各生成試行を監査し、成功した最後の検証をTutorTurnに残す。AI出力Schema、公開API、DB列、CSV固定ヘッダは追加しない。Mockの決定論的な章立てはテスト専用で、実AIの見出しを固定する根拠にしない。
