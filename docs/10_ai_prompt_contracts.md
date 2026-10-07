# 現行AI契約

契約版は `tutoring-teaching-contract-v3-current-spec`、taxonomy版は `m1-m3-unknown-v2`。

タスクはgenerate_tutoring_turn、generate_correct_answer_summary、explain_selected_distractorの3つだけ。分類・採点・状態更新・方略決定はbackendが行う。

## 入力と方略

両群に共通用語・構成要素と共通RAGを渡し、教材生成に固定問題・選択肢・正答を渡さない。参加者ID/群名はルーティングとログ照合専用でpromptから除く。

controlは一般説明で個人の診断・状態・履歴を入力しない。proposedだけにactive_misconception_type、learner_state、pretest_target(s)、diagnostic_evidence、session_misconception_history、現行taxonomyを渡す。

backend指定方略はcontrol→general_explanation、M1→belief_revision、M3→category_reorientation、unknown→foundational_explanation。Schemaのteaching_strategy enumは当該1つに固定し、不一致を拒否する。

## 出力検証

proposedの教材はtutor_message、teaching_strategy、mandatory_elements、teaching_contractを持つ。契約項目はtarget_claim_id、addressed_claim_ids、refutation_mode、corrected_claim、mechanism_explanation、contrast_example、transfer_check、target_addressed。

M1は反駁、M3はカテゴリー比較、unknownは基礎説明。transfer_checkは教材内の適用確認であり必須。本文との証拠一致、対象主張、未観察誤概念の創作、内部ラベル、正答漏えい、直前解説混入を検証する。600〜800文字、700文字前後を維持する。初回＋最大2回同backendで再生成し、失敗は503。Mockへ切り替えない。

正答要約/誤答解説は現在の問題・選択内容・表示済み教材・共通RAGを利用する。controlの個人診断/履歴は除き、proposedは説明具体化に使える。固定採点をAI解説で変えない。

## 監査

AICallLogの既存JSON内に実送信thread/start、turn/start全文、SchemaとSHA-256、モデル・推論設定、RAG条件/chunk本文hash、版、試行・検証、生応答を保存する。認証情報を保存しない。Mock入力を実送信として扱わない。TutorTurnにも版・契約・検証を保存する。
