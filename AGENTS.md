# Repository Instructions for Codex

## 用語注釈の不変条件

- 実験仕様版21は教材・回答後解説に共通固定辞書learning-glossary-v1を表示する。問題・選択肢・テストは対象外。辞書の正本・全文・確認元はdocs/24を参照する。
- 注釈は表示用JSONとして保存し、AI入力・生成本文・共通回答履歴に混ぜない。600〜800文字・教授契約版v7は変更しない。再表示はsnapshotを使い、旧教材へ後付けしない。登録語しか扱わず、AIで未知語を補わない。

このリポジトリは、卒業研究用AIチューターのアプリケーションリポジトリです。目標仕様は実験計画書に合わせたdocs、現行挙動はコード・YAML・入力型・テストを基準にしてください。実行時の現行実験仕様版は21です。目標を実装済みと扱わないでください。

## Authoritative Documents

- `docs/00_project_summary.md` から順に `docs/19_experiment_operation_runbook.md` までを必ず読む。
- `docs/20_experiment_plan_alignment.md` を読み、目標仕様・現行実装・未対応・要確認を区別する。
- `docs/99_sources_and_notes.md` は現行計画書の出典と設計判断の根拠として扱う。旧PPTX・旧案はhistory資料であり現行要件ではない。
- 実装依頼時の初期指示は `prompt.md` を使う。

## Research Invariants

- 通常版llm_knowledge・learning_round_v1のD（M1）とH（M3）の本文だけを指定文へ変更する。Dは入力した資料で正答できたことを重み更新の証拠とみなす誤り、Hは追加訓練を文書の検索・参照機能の代わりとみなす誤りとして、既存判定を維持する。場面・設問・2段落表示、同じ問題の残り8選択肢と残り8確認問題、全テスト・訂正情報・易しい版・教授プロンプト・注釈・採点・配置・回数上限は維持する。新規だけ仕様版21・通常版学習13（易しい版4）と現行protocolを保存する。旧学習v12を保持し、旧仕様版20以下は閲覧専用で記録を付け替えない。同期生成・先行生成は保存版に統一し、履歴はsnapshot優先・当時の学習版で復元する。通常版テストscenario-actions-v6とDB問題IDは変更しない。公開API・DB構造・AI生成契約は変更しない。今回の本文と分類理由はdocs/34、前回の再テストはdocs/33、以前のLLM改訂はdocs/32。

- 通常版事前の版9〜11の改訂・訂正情報、仕様版19のLLM改訂と仕様版20のマルチエージェント・記憶再テスト4問を維持する。仕様版21はLLM確認V1のD/Hだけを学習v13へ変更し、テストはscenario-actions-v6のまま。旧テストv1〜v5のアーカイブと全学習バンクを保持し、旧仕様版6〜20の結果は当時のバンクで復元する。
- 両版の全テスト・学習確認で、選択肢の文字数下限・文長比・文字数差による拒否はしない。非空・重複・役割数・教授対象の検査を維持する。教材600〜800文字の検査とは区別し、文長均一や難易度同等を保証しない。

- 問題版は管理設定standard/easyを登録時に固定する。通常版YAMLは保持し、易しい版は別バンク（テストscenario-actions-easy-v1、学習確認v4）でseedする。各版にテスト9固有問・確認9問。版が欠落しても他版にフォールバックしない。
- 易しい版だけ共通入力explanation_level=beginnerを3生成タスクへ渡す。両群に同じ平易化指示を適用し、診断情報の群別allowlist・教授契約は維持する。問題版と配置モードは独立。群集計・6仮説CSVは版別に限定し、生ログは両版を保持する。詳細はdocs/22。

- 研究仮説は計画書の6つ。番号はdocs/01・12・17で統一し、比較回次・集計単位・欠測の未指定部分を独断で決めない。
- 目標は大学生40名/各群20名、原則無作為割付。low設定・経験4有無・一般4/教材6の1〜10段階・必須自由記述・6仮説の記述集計は実装済み。自動割付・人数上限は対象外。式・対象はdocs/12・20の承認済み定義を守る。
- 共通説明とunknownは意味や仕組みを扱う。unknownの証拠はmandatory_elements.definitionとteaching_contract.mechanism_explanation/transfer_check。旧6項目を必須に戻さない。
- 比較対象は「AIあり/なし」ではなく、「通常AIチューター」と「ログ適応型AIチューター」。
- 現行分類はM1/M3/unknownのみ。両群へ同じ用語の全フェーズの採点済み回答履歴を渡す。提案群だけに明示的な診断・対象主張・taxonomy・タイプ別教授方針を追加する。方略はbackendで固定する。
- 確認問題の診断連動規則は両群共通。統制群のLLMへ分類・診断由来段階を渡さず、共通履歴内にも診断情報を混ぜない。統制群の自然な誤り訂正は許容する。
- 被験者画面に内部分類、群名、教授方略を直接表示しない。
- テスト回答中はチャット・ヒント・即時正解を表示せず、回答送信後の結果確認では正誤を表示する。
- 学習確認は1用語・1セッションあたり最大3回答。事前テスト後のテストはfinal_testも含め最大2回、事前込み最大3回。未回答を含む採点済みバッチを1回とし、全問未回答は採点しない。1回目未達は学習、2回目未達は未達のままアンケートへ進める。満点ならいつでもアンケートへ進める。
- テストはscenario-actions-v6の9固有問題で、activeキーはpretest_v1、retest_v1/v2。final_testはretest_v1を共用し、その後は全用語をretest_v2へ進める。用語別回答件数で選ばない。通常版・易しい版・アーカイブのYAMLは`backend/app/seed/content/standard/`、`easy/`、`archive/`に分ける。旧問題・retest_v3はarchive/learning_content_pre_issue156.yml、さらに古い問題はarchive/learning_questions_v2_unused.ymlへ保全する。seedは版付きconstruct_keyで旧本文・選択肢を上書きしない。学習確認v13の9問は維持するが、3セッション目は新規経路で到達しない。
- 選択肢配置は管理画面のDB保存設定で切り替える。既定値は `debug_fixed` で、新規参加者だけに適用する。実験データ収集前に `randomized` へ変更し、正答位置の手掛かりがないことを確認する。判定は表示ラベルでなく選択肢ID・内部メタデータで行う。
- 新規だけ仕様版21とprotocol_id=experiment-plan-2026-10-26-llm-round1-dh-v1を保存し、`retest_cycles_completed=0`で開始する。この列は学習後retestだけを数え、共通上限用のpost_pretest_tests_completedは採点済みfinal_testを加えて導出する。DB列は追加しない。既存版20以下を含む旧protocol_id/NULL・未対応版は閲覧専用。旧行の版・進行・回答・評価・回数を更新/削除せず、補修も版とprotocol_idで限定する。
- 両群の教材の小見出し・数・順序・まとめ方はAIが決める。冒頭の##用語名と非空の###セクションだけを要求し、実験群の必須教授内容・transfer_checkは本文内証拠で検証する。固定見出しから証拠文を自動補正しない。
- 教材内のtransfer_checkは維持するが、独立した追加テスト・旧支援量・自由回答処理を戻さない。
- 現行MVP対象用語は `llm_knowledge`、`multi_agent`、`memory_process` の3項目とする。

## AI Backend Rules

- OpenAI APIキーを要求しない。
- OpenAI SDKで通常APIを直接呼ばない。
- AI呼び出しは必ず `AIBackend` インターフェース経由にする。
- AIタスクは教材生成・正答要約・誤答解説だけ。採点・分類・状態更新・方略決定はbackendで行う。
- 通常実行では `CodexAppServerBackend` を使い、ユーザーのChatGPT/Codexログイン済みapp-serverへ接続する。
- アプリ既定のAI設定は `gpt-6-luna / low`。管理画面では `gpt-6.1-sol` / `gpt-6-luna` と low/medium/highを一時切替でき、両群・進行中参加者の次回呼び出しから適用する。DBには保存せずbackend再起動でCODEX_MODEL/CODEX_REASONING_EFFORTへ戻す。研究計画書原本のgpt-5.6-luna記載は変更せず、アプリ設定との差を明示する。同一参加者内での実験中切替はモデル混在を生むため、収集時は設定を固定する。
- `MockAIBackend` は自動テスト・障害切り分け専用にし、通常実験データへ混ぜない。
- `AI_BACKEND=codex_app_server` ではMockへ自動フォールバックしない。
- ChatGPT/Codex認証情報、アクセストークン、APIキーをDBに保存しない。

## Implementation Priorities

1. 研究ログの完全性
2. Codex app-server経由の実AI応答
3. 実験フローの正確性
4. 評価指標とCSV出力
5. MockAIBackendでのテスト再現性
6. UIの見た目

## Editing Policy

- 仕様整理の依頼ではMarkdownだけを編集する。
- 文書更新だけでプロンプト・Schema・環境設定・API・DB・実行版を変更しない。実装開始は別途明示的な依頼を必要とする。
- 目標プロンプトの引用と現行コードの送信原文を区別する。既存ログを新6仮説の確定済み評価値として扱わない。
- 実装開始の依頼では、仕様にない独自判断を最小限にし、判断した内容はREADMEまたは該当docsに追記する。
- 要確認事項はdocs/20で管理し、決定されていない分析方法・新しいunknownの検査項目を実装者が補完しない。その他の運用はdocs/19・99を参照する。
