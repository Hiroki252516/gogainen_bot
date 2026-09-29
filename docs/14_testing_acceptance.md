# Testing Acceptance

## Backend

- A/Bの有効な参加コードがない参加者作成は拒否され、Aは内部`proposed`、Bは内部`control`へ変換される。正常作成時は`assignment_method=admin_code`を保存し、参加者向けレスポンスに`group_condition`を含めない。同意なしの参加者作成も拒否され、同意画面から同意した場合だけ`pretest`へ進む。`survey`送信で`participant_surveys`が1件保存され、`current_step=finish`、`completion_reason=completed`になる。送信再実行でアンケートが重複しない。
- 同意画面の参加者作成が15秒以内に完了しない場合はタイムアウトエラーを表示し、「開始しています...」のまま操作不能にならない。DB接続障害はAPIの503と利用者向けエラーとして確認できる。
- YAMLにactive termが `llm_knowledge`、`multi_agent`、`memory_process` の3件だけ存在する。
- pretest・retest・final_testはA〜Jの10選択肢で、各variant内の正解、M1、M3、unknownを3/3/3/1にする。全21variantを通じてA〜Iの各ラベルが正解・M1・M3を各7回ずつ担い、設問はシナリオに基づく判断形式になる。学習確認v1は旧固定配置、学習確認v2はvariant別metadata配置で、各問の配分は3/3/3/1、全30問を通じて各ラベルが正解・M1・M3を各10回担う。`l0_check`と`transfer`はこの配分の対象外である。
- pretest・final_testは各用語1問、retestは各用語5variant、learning確認はstage・用語ごとに5variantになる。
- テスト系と学習確認v2は提示問題の正解metadataに該当する3選択肢だけを重複なくすべて選んだ場合に正解となる。学習確認v1はA/B/C完全一致だけが正解。J単独だけがunknownで、M3がM1より優先される。
- retestはv1〜v5を使い、6回目以降はv5を再利用する。
- テスト問題の21variantに選択肢本文の重複がなく、選択肢長の極端な差や正誤の露骨な表現手掛かりを内容レビューで確認する。
- 新規参加者の学習確認v2は3用語×2学習段階×5場面variantの全30問を検証し、各段階・用語の5問が適用・予測・比較・境界判断・事例診断を含む。長さの極端な差や固定テスト文との一致を拒否し、設問・選択肢に表面的な正誤の手掛かりがないことを内容レビューで確認する。
- 既存参加者（版列NULLを含む）は学習確認v1、新規参加者はv2を使い、提示済みターンの版で回答を採点する。テスト系はvariant別の選択肢metadataで採点し、正誤結果の表示・非公開情報のprojectionを維持する。
- learning確認は各版でv1〜v5を使い、6回目以降はv5を再利用する。
- RAGは用語別の指定sectionだけを検索し、LangGraphチャンクを返さない。
- 同じ用語・同じ構成要素についてcontrolとproposedのRAG query、allowed section、chunk ID、chunk本文が一致し、検索に学習段階・診断・履歴を使わない。
- 教材生成のcontrol有効promptは、参加者ID・群名・固定問題・選択肢・正答・診断・学習段階・履歴を含まず、学習者の回答や履歴だけを変えたmetamorphic testでも同一になる。
- controlの`generate_tutoring_turn`は`control-fixed-v1`の固定系列を使い、事前テスト、`LearnerState`、過去回答、誤概念を変えても同じ用語・同じturn_indexの教材、variant、問題文、選択肢になる。controlの不正解後も`next_learning_stage`は固定系列を示し、診断値は教材選択へ使わない。
- 両群の教材生成に固定問題・選択肢・正答を含めない。表示と採点はYAML/backendが担い、生成Schemaに問題・選択肢用fieldを含めない。
- controlの正答要約・誤答解説は同じprojectionを使い、学習段階・診断・履歴・識別子を除きつつ、現在の問題・選択内容・表示済み教材・共通RAGを保つ。一般的な誤解の説明・訂正は許容する。
- controlとproposedのRAG本文・検索条件は共通であり、proposedだけにtaxonomy・履歴・足場掛け情報が入る。
- `teaching_targets`が3用語のM1/M3選択肢すべてに存在し、M1のE選択時に選択肢本文、`llm_knowledge:pretest:E`、研究者確認済みの「プロンプトだけでは重みを更新しない」という訂正がproposed payloadへ入る。
- proposedの`pretest_target(s)`、`taxonomy_version`、`prompt_contract_version`が`AICallLog.request_payload`へ保存され、`TutorTurn.diagnosis_json`にも契約と検証結果が保存される。controlにはtaxonomy、誤答主張、診断履歴、learner state、learning stage、過去回答を入れない。
- `TutorTurn.diagnosis_json`と`AICallLog.request_payload.generation_audit`に`instruction_route`、`fixed_sequence_key`、用語・session/turn・variant、`actual_ai_input`が保存される。controlの`actual_ai_input`に識別子、群名、stage、診断、pretest、履歴がなく、Codex実行時は`effective_request`にも同じ監査情報がある。
- Codex app-serverが返した補正前のJSON文字列が`AICallLog.raw_text`に保存され、`response_payload`には補正後の利用値が保存される。参加者ログAPIとCSVの`value_json`から両方を比較できる。
- M1/M3/unknownの`teaching_contract`がclaim ID、方略、訂正、仕組み、対比例、転移確認を満たし、本文と一致する。欠落・不正claim・誤った方略は同じbackendで初回を含む最大3試行（再生成は最大2回）後に503となる。
- M1/M3が混在する事前テスト、事前targetのない学習中M1/M3、staleなM1/M3 targetを含むunknownで、claimの混在・捏造・503が発生しない。日本語に隣接した内部ラベルと改行を含む証拠文も検証する。
- AI入力と出力に固定確認問題・選択肢・正答を含めず、生成教材へ直前フィードバックを転載しない。RAGの検索条件は段階・診断に依存せず両群で同一である。
- Codex成功・失敗ログの`effective_request`から実送信prompt、Schema、model、effort、prompt/taxonomy版、RAG query/section/chunk ID/本文hash、試行番号、送信状態を追跡でき、認証情報を含まない。送信前失敗は未送信と区別でき、Mock logにはCodex実送信監査がない。
- 提案群の教材再生成を行った場合、各`AICallLog.response_payload.generation_validation`に試行単位の契約・安全性検証結果を残し、最終`TutorTurn.diagnosis_json`にも総試行数と最終検証を保存する。
- 教材文字数・段落数・箇条書き数を記録し、本文700文字前後（600〜800文字）を両群共通の許容範囲として検証する。範囲外の場合は同じAI backendで初回を含む最大3試行（再生成は最大2回）とし、再生成時は前回の実測文字数をAIへの調整指示へ含め、最終検証結果をAIログとTutorTurnへ保存する。
- app-server payloadが `gpt-5.6-luna` / `medium` を使う。
- 正答時は `generate_correct_answer_summary`、誤答時は `explain_selected_distractor` が呼ばれ、解説生成の目的とpayloadが `AICallLog` に記録される。
- `/api/participants/{participant_id}/learning-targets` が、既存の未達対象 `targets`、互換用 `pretest_results`、直近の `test_results`（周回名、問題文、本人が選んだ選択肢本文、正誤）を返す。`test_results` に正答、期待解答、選択肢ごとの正誤、M分類などの内部診断値を含めない。
- 学習ターン生成の参加者向けレスポンスと冪等再取得が、問題文・公開選択肢・選択数制約だけを返し、`expected_answer`、正誤metadata、M分類、内部stage metadataを含めない。
- 解説生成に失敗した場合、固定採点結果や学習状態を部分確定せず、Mockへ自動フォールバックしない。
- 学習ギブアップAPIが開いている学習セッションを終了し、`current_step=retest`と`next_url=/retest`を返す。ギブアップした学習ターンは回答として保存しない。
- 実験ギブアップAPIが、`current_step=retest`または`final_test`では`current_step=survey`、`next_url=/survey`、学習対象確認中などそれ以外では`current_step=finish`、`next_url=/finish`を返し、`completed_at`、`completion_reason=give_up`を確定する。retestまたはfinal_testギブアップ後は問題の取得・回答保存・採点・学習セッション操作を409で拒否し、アンケート送信後に`current_step=finish`へ進む。アンケート送信後も`completion_reason=give_up`とギブアップ時の`completed_at`を保持する。学習ギブアップは`completion_reason`を変更せず、両操作を`AuditEvent`へ記録する。管理画面の参加者一覧・詳細とCSVで状態・回数・操作時刻を確認できる。
- 同じ`Idempotency-Key`・同じ本文の参加者向けPOST再送が保存済みレスポンスを返し、回答、アンケート、学習ターン、監査イベント、AI呼び出しを重複させない。
- 同じ`Idempotency-Key`で本文を変更した場合は`409 idempotency_key_conflict`、別キーで同じ周回の回答済み問題へ送信した場合は`409 answer_already_submitted`となり、元の回答を維持する。
- 学習ターン生成の初回と各「次の確認へ」が別の論理キーで管理され、次ターン取得中に戻って再開しても同じ教材・確認問題を二重生成せず、前ターン回答済みエラーにもならない。
- 初回`llm_knowledge`教材の保存後、後続の未達用語が`PRETEST_TERM_ORDER`順にv1先行生成され、独立turnとして`ready`になる。先行生成turnには回答が保存されず、参加者レスポンスの形式は増えない。
- 現在用語を不正解にしても後続の`ready`教材は変更されず、現在用語の次turnだけが既存の誤概念履歴を受け取る。次の用語では同じ待機`turn_id`が返り、教材生成AI呼び出しを重ねない。
- 先行生成中に次用語へ進んだ場合は待機結果を破棄して同期生成へ切り替え、先行生成失敗時は参加者を停止させず通常生成を行う。`codex_app_server`からMockへ自動フォールバックしない。
- 学習・実験ギブアップと再テスト後の新しい学習周回開始で未使用の先行生成が`discarded`となり、後続画面で再利用されない。未使用turnは回答履歴と学習負担の実績値へ算入しない。
- `TutorTurn.diagnosis_json`、`AICallLog`、管理者ログ、CSVの`value_json`で生成元、待機、再利用、失敗、破棄を追跡でき、control/proposedの入力分離と既存教材契約検証が維持される。
- テスト問題のGETレスポンスが`answer_status`と`submitted_answer`を返し、回答済み問題の画面では保存済みの選択肢を選択済み表示し、入力を変更できず、「次の問題へ」で実験を継続できる。409は実験終了として扱わない。
- 学習回答が十分と判定された用語は学習対象から外れ、残りの用語または再テストへ`next_url`で進む。完了済み用語の学習URLを再表示しても、学習セッション生成やAI呼び出しを行わず、現在の正規画面へ戻る。
- ブラウザの戻るボタン・マウスのサイドボタンで同意書、診断、回答済み問題、再テスト結果、完了済み学習画面へ戻っても、`current-step`ガードが古い画面からのPOSTを防ぎ、実験フェーズを飛ばさない。ガード確認はGETのみで、409は実験終了や中断として扱わない。
- 終了画面からブラウザの参加者情報を消去して新しい実験を開始でき、管理画面で削除した参加者のIDが残っていても新しい開始画面へ復旧できる。Dockerの再ビルドで未完了参加者を意図せず別参加者へ変更しない。
- 管理画面の評価サマリー・群集計・被験者ログ・ログCSV参照時に、3用語の採点済み事前テストがある参加者の評価サマリーが再計算ボタンなしで作成・更新される。事前テストだけの参加者は誤概念推移を「未分類」とし、再テスト済みのように扱わない。

## Frontend

- 参加者向け画面のヘッダーで「管理画面」を押すと、実験画面から移動する確認と「実験データは削除されない」旨を表示し、キャンセル時は遷移しない。管理画面自身からの同リンクでは確認を表示しない。
- `/start`で参加コードを入力し、同意書画面を経由してpretestへ進む。同意前や不正コードでは参加者を作成せず、被験者画面に群名・内部群の対応を表示しない。テスト終了後は仮アンケート画面を表示し、送信後に終了画面へ進む。
- 管理画面の「実験開始画面へ戻る」は参加者情報をブラウザから外して`/start`を表示し、サーバーの実験データは削除しない。「実験途中に戻る」は保存済み参加者の`current-step`から正規の続き画面へ戻る。
- pretest/retest/final-testで3用語が表示される。
- pretest/retest/final-testの各問題は「問１：用語名」とし、用語名を太字にして問題文をその下に表示する。見出しの書体とサイズは問題文に揃える。現在位置は「1 / 3」「2 / 3」の形式で表示される。
- 学習画面では確認問題の現在位置を「1 / 3」「2 / 3」の形式で表示する。設問見出しの変更は適用しない。
- 10択複数選択UIで、3つまたはJ単独以外は送信できない。
- 学習画面に学習段階、段階に応じた研究者向け説明、M1〜M4、unknown、LangGraph、内部教授方略を表示しない。
- 学習本文、問題、結果表示がモバイル幅で重ならない。
- 学習問題への回答後も問題文と選択肢を同じ画面に残し、その下に正解・不正解とフィードバックを表示する。回答済みの選択肢は変更できない。
- 学習セッション初回読み込み中に、スピナー、経過秒数、4つの安全な進捗状態が表示され、読み込み完了後に消える。
- 初回読み込みAPIが失敗した場合、進捗表示が停止し、既存のエラーメッセージだけが表示される。
- 「次の確認へ」の取得中も直前の正誤・解説を残した進捗カードが表示され、経過秒数と4つの安全な処理状態を示す。取得完了後に新しい確認問題へ置き換わり、取得エラー時は進捗表示が停止する。
- `/learning-targets` でテスト・再テストの周回名と3用語の確認結果を表示する。各結果は「問１：用語名」とし、用語名を太字にして問題文をその下に表示する。見出しの書体とサイズは問題文に揃える。本人が選んだ選択肢本文と正解・不正解・未回答も表示し、正答そのものは表示しない。学習対象かどうか、学習段階、対象選定理由などの情報は参加者画面に表示されず、不正解用語だけが学習開始対象として内部的に扱われる。
- `/learning-targets` の結果表示では、正解の判定文を緑、不正解の判定文を赤で表示する。
- アンケートの必須回答欄には「必須選択」と見える表示があり、任意項目と区別できる。
- 回答送信中にスピナー、経過秒数、4つの安全な処理状態、`分析中...` ボタンが表示される。
- 正答時は緑色の正誤カードとMarkdown要点解説、誤答時は赤色の正誤カードとMarkdown見直し解説が表示される。
- 解説表示後もAPIの `item_results` フィールドと次の確認への遷移が維持される。現行の固定複数選択フローでは `item_results` は空配列であり、個別結果の表示は値がある場合に限る。
- AIの内部思考過程、M1〜M4、誤概念taxonomyが被験者画面に表示されない。
- 旧stage名や旧Transformerの新規導線に依存しない。
- ブラウザ履歴から過去フェーズへ戻った場合、現在の正規画面へ履歴を増やさずに置き換え、同意・診断・採点・学習開始のPOSTを重複実行しない。
- 学習画面のギブアップ操作は再テストへ遷移し、再テスト画面・`final_test`画面のギブアップ操作はアンケートへ遷移して送信後に終了画面へ進む。再テスト結果確認画面・学習対象確認画面のギブアップ操作は終了画面へ遷移する。確認ダイアログを表示し、事前テストには表示しない。
- ギブアップボタンは「次へ」などの回答操作から離れた画面下部の右寄せ領域に表示される。
- 管理画面の誤概念推移では`regressed`を「誤概念」と表示し、学習回答に「学習十分」「学習不十分」の集計カードを表示しない。

## Regression

この文書の項目は現行MVPの受入観点と将来機能の回帰観点を含む。M2/M4固定問題、遅延再テスト、手動診断修正とその監査、完全な転移評価は現行MVPの必須受入条件ではなく、将来対応として別途検証する。参加者削除、学習・実験ギブアップとそれらの監査記録は現行MVPの受入対象である。

- `AI_BACKEND=mock` で固定問題・遷移・RAG契約テストが通る。
- `AI_BACKEND=codex_app_server` でMockへ自動フォールバックしない。
- `AI_BACKEND=codex_app_server`でM1、M3、unknownの代表ケースをブラウザから生成し、participant logの`AICallLog` payloadと`tutor_turns.diagnosis_json`で対象claim・契約・版を確認する。
- 教材契約回帰として、全M1/M3選択肢の研究者確認済みtarget、M1/M3のtarget混在防止、unknownへのstale target非混入、target未観測時の汎用契約、日本語・改行を含む証拠検証、空のpretestバリアントを検証する。
- 既存の単一選択API互換、DB列、CSV列、過去ログを壊さない。
- `Idempotency-Key`なしの既存API呼び出しが動作し、既存の重複データを削除しない。

## 学習ターン先行生成

- 不正解かつ残り挑戦回数がある回答で、解説AIと次教材AIが同時に開始され、解説レスポンスが次教材の完了を待たずに返る。
- 次教材生成中に「次の確認へ」を押すと既存の`ContinueProgress`で待機し、完了後に未回答`TutorTurn`を1件だけ返す。生成済みの場合は追加AI呼び出しを行わず再利用する。
- 次教材生成失敗時は回答APIが成功し、次ターン取得で同期生成へフォールバックする。解説生成失敗時は現在の回答・学習状態・次教材が確定しない。
- 正解、挑戦回数上限到達、セッション完了、ギブアップでは不要な先行生成を行わない。ギブアップ中のタスクは中止され、終了済みセッションにターンを保存しない。
- ブラウザ再読み込み、戻る操作、同じ`Idempotency-Key`での再送時に同じ未回答ターンを再利用し、教材と`TutorTurn`を重複生成しない。

## Commands

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
docker compose build backend frontend
docker compose up -d --force-recreate backend frontend
```
