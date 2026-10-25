# 通常版・易しい版の運用と入力契約

## 両版に共通の用語注釈

現行実験仕様版15では両版・両群の教材と回答後解説に同じ固定辞書を適用する。注釈処理はexplanation_level、生成契約v7を変更しない。通常版学習バンクの更新は下記の保存と出題で説明する。注釈は本文とは別枠で、正答情報や個別診断で選ばない。[辞書全文と保存](24_learning_glossary.md)。

## 目的と比較の範囲

AI・技術の予備知識が少ない参加者にも設問を読めるように、身近な場面と短い選択肢を使う易しい版を別に用意する。版9では通常版事前テスト6選択肢と訂正情報を改訂し、旧通常版をアーカイブする。易しい版の本文は変更しない。易しい版は問題とAI説明条件の両方が異なるため、版間の成績差を問題難易度だけの効果とは解釈しない。実験群と統制群の比較は同じ問題版内で行う。初心者への読みやすさ、平行形式の難易度同等性、M3分類の妥当性を機械検査で実証したとは扱わず、研究者の内容確認・予備調査を別途行う。

## 管理画面

1. 「新規参加者に適用する問題版」で通常版／易しい版を選ぶ。既定値は通常版。
2. 選択肢配置は別にデバッグ配置／ランダム配置を選ぶ。4通りを使用できる。実験収集時はランダム配置を使う。「わからない」は常に末尾J。
3. 新しい参加者IDで開始する。開始時の問題版と配置を記録し、以後の設定変更・再起動・再送で変えない。
4. 「集計する問題版」は上記の設定とは独立して選ぶ。初期表示は通常版。群集計、対象人数、6仮説、仮説CSVは選択版に限定する。被験者一覧・生ログは両版を表示し、問題版を併記する。

旧版14以下の試用は新規版へ付け替えず閲覧専用にする。更新前からの進行中試用をそのまま継続する運用ではない。旧記録・保存済み評価・AIログは再計算しない。

## 保存と出題

仕様版15では通常版の学習確認をv8へ更新する。v7からの変更はmulti_agent・learning_round_v2の場面・設問・9選択肢であり、この通常版V2だけ案1・案2を改行表示する。易しい版V2を含む他問題の表示は変えない。V1・LLM知識を含む残り8確認問題、易しい版v4、テストバンクは維持する。旧v3・v5・v6・v7を履歴用に保持し、snapshot優先・保存版で復元する。[今回の全文と表示条件](28_multi_agent_round_two_revision.md)・[V1と曖昧さの留意点](27_multi_agent_choice_revision.md)。

| 項目 | 通常版 | 易しい版 |
| --- | --- | --- |
| question_set_mode | standard | easy |
| テストYAML | `backend/app/seed/content/standard/learning_content.yml` | `backend/app/seed/content/easy/learning_content_easy.yml` |
| assessment_bank_version | scenario-actions-v4 | scenario-actions-easy-v1 |
| 学習YAML | `backend/app/seed/content/standard/learning_questions_v8.yml` | `backend/app/seed/content/easy/learning_questions_v4_easy.yml` |
| learning_content_version | 8 | 4 |
| 固有問題数 | テスト9・学習確認9 | テスト9・学習確認9 |
| 追加AI入力 | なし | explanation_level=beginner |

RuntimeSetting（ID=1）とParticipantへnullableなquestion_set_modeを追加する。既存行はNULLのまま通常版として読み、補完しない。新規登録だけ選択した版と対応する学習版を保存する。無効な版や学習版の不整合はエラーにして、他版を代用しない。

各版にpretest 3問、retest 6問、内部final_test 3行をseedする。final_testはretest_v1を共用するため固有問題は9問である。両版合計は24 active DB行・18固有テスト問題。版付きconstruct_keyと別問題IDで通常版・易しい版を同時保持し、旧Question/QuestionOptionは上書きしない。

参加者の版を、出題・回答ID検証・採点・教授対象・結果レビュー・履歴復元・同期生成・先行生成で共通に参照する。他版の問題IDは拒否する。履歴は表示時snapshotを優先し、不足部分は当時の問題IDまたは固定された学習版で復元する。

各問の役割は正解3・M1誤答3・M3誤答3・unknown 1。表示順と採点を分離し、内部選択肢IDとメタデータで完全選択・M3優先を判定する。参加者向けAPIへ正答・分類は返さない。配置アルゴリズムは各版内で再現可能・役割ラベル数を均衡させる。

事前込み最大3テスト、事前後最大2回、満点時早期終了、未達終了、学習確認1用語・1セッション最大3回答は変更しない。学習確認3セッション目も保存するが現行経路では到達しない。同一セッションの再回答では問題を変えない。

## 平易化指示と群別分離

教材生成・正答要約・誤答解説の共通allowlistへ、易しい版だけexplanation_level=beginnerを追加する。通常版にはキーも追加指示も入れない。実装はbackend/app/ai/interaction_history.pyとtutoring_prompt.py。追加する指示は以下であり、両群共通である。

> 対象はAIや技術の知識が少ない学習者である。短い文を使い、一文には一つの話題だけを置く。
>
> 必要な専門語は初めて使う箇所で短く説明し、不要な専門語や抽象的な言い回しは日常の言葉へ置き換える。
>
> 学校、店、旅行、メモなど身近な具体例で説明する。比喩だけで説明を終えず、実際の仕組みとの違いも守る。
>
> 平易にするために正確さや指定された教授内容を省かない。教材の文字数条件、正答を直接示さない条件など既存ルールも守る。
>
> 平易化するのは説明の本文である。本文の証拠文を返す指定がある場合は、完成した本文から一致する箇所を抜き出し、言い換えたり入力資料の文を代用したりしない。

用語説明・構成要素・RAGの取得条件は共通で、通常版と同じ。明示的な診断、誤答対象・訂正情報、taxonomy、タイプ別教授方針は従来どおり実験群だけに渡す。統制群の回答履歴からの自然な訂正は許容する。未回答問題と正答キーを教材生成へ渡さない。

600〜800文字、自由な###小見出し、実験群の必須教授要素・teaching_contract・本文証拠・transfer_check、正答漏えい防止、最大3試行・不合格停止・Mockへの非フォールバックを維持する。Mockは自動検査用であり、初心者に対する有効性の証拠ではない。

## APIと集計

- GET /api/admin/question-set: modeとapplies_to=new_participants_only。キャッシュ禁止。
- PUT /api/admin/question-set: mode=standard|easy。余分なキー・不正値は422。アクセス制御は既存のまま。
- GET /api/admin/evaluation-summary、GET /api/admin/logs/overview: query question_set_mode=standard|easy（既定standard）。集計だけを指定版へ限定し、生ログ一覧は全版を維持。
- GET /api/admin/export/hypothesis_metrics.csv、hypothesis_group_summary.csv: 同じqueryで指定版に限定。版別ファイルへ出力し、details_jsonに版を保存する。統合CSV固定ヘッダは変更しない。

保存する参加者・回答履歴・教材監査JSONにも問題版を記録する。AI実送信への追加キーはexplanation_levelだけであり、管理用の版名を統制群の診断情報として送らない。仮説の評価式は変更せず、対象者・欠測・分母を選択版内で数える。

## 版と検査

実験仕様版15、protocol experiment-plan-2026-10-25-multi-agent-round2-v1、生成契約tutoring-teaching-contract-v7-easy-level。taxonomyはm1-m3-unknown-v3、共通履歴interaction-history-v1、共通出題shared-diagnosis-route-v1を維持する。

通常版・易しい版の全テスト・学習確認で、選択肢の20文字下限・最大/最小文長比1.8・文字数差32の検査を撤廃した。非空・重複・選択肢数・役割数・教授対象の検査は維持する。文長の均一性は保証せず、長さが回答の手掛かりとなり得る。教材本文の600〜800文字検査は別の条件として維持する。各誤答の個別分類理由と事前テストの教授対象は別途保持する。易しい版の内容は[問題全文](23_easy_question_bank.md)、通常版の6選択肢の改訂と旧バンク保全は[21](21_assessment_action_questions.md)を参照する。
