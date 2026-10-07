# 現行AI契約

実験仕様版は2、契約版は `tutoring-teaching-contract-v4-shared-history`、taxonomy版は `m1-m3-unknown-v2`。

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

proposedの教材はtutor_message、teaching_strategy、mandatory_elements、teaching_contractを持つ。契約項目はtarget_claim_id、addressed_claim_ids、refutation_mode、corrected_claim、mechanism_explanation、contrast_example、transfer_check、target_addressed。

M1は反駁、M3はカテゴリー比較、unknownは基礎説明。transfer_checkは教材内の適用確認であり必須。本文との証拠一致、対象主張、未観察誤概念の創作、内部ラベル、正答漏えい、直前解説混入を検証する。600〜800文字、700文字前後を維持する。初回＋最大2回同backendで再生成し、失敗は503。Mockへ切り替えない。

正答要約/誤答解説も共通入力を使い、現在の問題・選択内容・表示済み教材を追加する。不正解の現在選択には従来どおり選ばれた誤答本文だけを使う。履歴は現在回答より前の確定分とし、二重掲載しない。proposedだけ診断と教授方針を追加し、固定採点をAI解説で変えない。

確認問題は両群ともshared-diagnosis-route-v1の規則を使い、unknownはenrichment、M1/M3はconceptual_change。同じ状態・回答・ターンなら同じ問題/variant。controlのモデルへこの段階は渡さない。次教材の先行生成では、現在の固定採点・選択・時刻を履歴へ副作用なしに投影し、回答確定後だけ公開する。解説失敗時は生成物を破棄する。

## 監査

AICallLogの既存JSON内に実送信thread/start、turn/start全文、SchemaとSHA-256、モデル・推論設定、RAG条件/chunk本文hash、版、試行・検証、生応答を保存する。interaction-history-v1の件数とSHA-256、出題規則版、モデル入力投影も記録する。controlのinstruction_routeはshared_history_general、proposedはshared_history_diagnostic。認証情報を保存しない。Mock入力を実送信として扱わない。TutorTurnにも版・履歴指紋・契約・検証を保存する。
