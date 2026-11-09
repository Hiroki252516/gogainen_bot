# 用語ごとの設問答え合わせ（仕様版28）

## 2026-11-03の条件拡張

「設問1のみ出題」がONの参加者は、その用語の設問1を保存後に答え合わせを表示し、設問1のAttemptへ確認時刻を保存する。OFF/旧NULLは従来どおり設問1・2を保存後に表示し、設問2へ確認時刻を保存する。以下の2設問前提の記述にはこの条件を優先する。詳細は[48](48_first_question_only.md)。

> 状態: 仕様版28で導入した過去の設問ペア答え合わせ契約。仕様版43の現行出題は各モードの設問1のみで、登録時snapshotに応じて問題バンクを選ぶ。現在のバンク・出題・復元契約は[50](50_basic_understanding_question_mode.md)を参照する。PRETEST問題文の更新は版32の履歴[44](44_pretest_content_revision.md)、版33の差分[45](45_pretest_memory_distractors.md)、仕様版27の採用時記録 [39](39_split_assessment.md) は当時の根拠として保持する。受入検証状況は[14](14_testing_acceptance.md)を参照。

## 対象と表示

仕様版28では通常版テストへ用語ごとの設問ペア答え合わせを追加した。現行の通常版`split-actions-v5`でも、PRETEST、RETEST、内部 final_test に同じ確認を適用する。PRETEST本文の履歴と版別バンクは[44](44_pretest_content_revision.md)・[45](45_pretest_memory_distractors.md)を参照する。用語は既存順で処理し、同じ用語の設問1・2が両方保存された後に限って、その2問の確認を表示する。設問1だけの回答では結果を返さない。

答え合わせは、回答中のテスト画面内に表示する。URL・ページを切り替えず、画面内の「続行」で次の用語へ進む。最後の用語の「続行」後は既存のテスト完了・採点・結果確認・学習またはアンケートへの遷移を行う。答え合わせ自体ではフェーズ採点や学習状態を更新しない。

各設問に表示するのは設問番号、本人が選択した選択肢の表示ラベルと本文、正誤だけとする。正答選択肢、解説、M1/M3/unknown等の内部分類、群名、教授方略は返さない。テストの6設問が完了してから行う既存の採点・診断・進行判定は維持する。

## 管理設定と適用範囲

管理画面に「設問ごとの答え合わせ」設定を追加する。初期値はON。既存の「事前テストの結果表示」と独立した設定で、新規参加者だけに登録時点で固定する。開始済み参加者の設定は変更しない。

PRETESTのペア確認後の全体結果画面は、当初は「事前テストの結果表示」だけで決めていた。2026-10-31のissue-233以降、管理画面の「テスト結果の表示」はPRETESTに加えてRETEST・内部final_testにも適用する。設問ごとの答え合わせ設定と全体結果表示設定は独立し、全体結果OFFでもペア確認自体は維持する。新規参加者の登録時に結果表示snapshotを固定し、既存参加者の再テストsnapshotがNULLなら表示する。API・保存・遷移の現行契約は[08](08_backend_api_spec.md)と[09](09_frontend_ux_flow.md)を参照する。

## API契約

- GET/PUT **/api/admin/question-review-display** は管理認証下で、{ enabled: true/false, applies_to: "new_standard_participants_only" }を読み書きする。enabledは厳密なbooleanとし、文字列・数値をbooleanとして受け入れない。
- 既存のPRETEST、RETEST、final_test取得APIは、ペア確認設定が有効な仕様版28の参加者について、未確認ペアがある場合だけ pending_question_review を返す。設問1・2双方の保存済み回答があり、設問2の確認時刻がNULLであることを返却条件とする。完全でないペア、確認済みペア、設定OFF、旧版には返さない。
- pending_question_review は phase、term_slug、term_label、results の形とする。results は question_number（1または2）、selected_option（label、body）、is_correct（boolean）の2要素を持つ配列とする。正答キー、未選択選択肢、解説、診断・分類・群・方略の情報は含めない。
- POST **/api/participants/{id}/question-review-acknowledgements** は phase（pretest / retest / final_test）と term_slug を受け取り、対象ペアを確認済みにする。不完全なペアは状態競合として拒否し、Attemptを変更しない。重複送信は冪等とし、確認時刻を重複作成せず現在の正規進行位置を返す。
- 続行による確認状態の保存先は、その用語の設問2に対応するAttempt.question_review_acknowledged_at。画面を再読み込みしたときは、未確認なら同じペアを復元し、確認済みなら再表示しない。

## 保存・互換性

仕様版28では新規登録だけ protocol_id=experiment-plan-2026-10-30-question-review-v1 を保存する。RuntimeSetting.show_question_reviews と Participant.show_question_reviews をnullableで追加し、Attempt.question_review_acknowledged_at もnullableで追加する。管理設定の初期値はtrue。新規参加者は登録時のtrue/falseをsnapshotへ保存する。既存行には値を補完しない。

仕様版27以下、旧protocol_id、NULL・未対応版は既存方針どおり閲覧専用とし、進行・回答・評価・回数・設定snapshotを更新しない。過去の結果・問題・画面snapshotは書き換えない。仕様版27の通常版設問分割・問題本文・選択肢・採点規則・回数上限・教授内容・AI契約・6仮説の式は変更しない。正誤の表示条件だけを新しい参加者設定として記録し、異なる表示条件が混在する場合は研究条件として識別する。Participants CSVと参加者ログにはshow_question_reviewsを保持し、確認時刻は既存のvalue_json形式で記録する。仕様版43では統合ログCSVに`test_content_mode`列を追加し、他の従来列は維持する。

## 受け入れ条件（実装済み・検証待ち）

1. 設問1だけが保存された状態では確認データがなく、同じ用語の設問1・2が双方保存された後だけ未確認ペアが表示される。
2. 確認画面への表示・その中の続行でURLとページを変えず、続行後に次の用語の設問へ進む。最後のペアの続行では既存のフェーズ完了処理へ進む。
3. ペア確認ON/OFFと既存PRETEST全体結果表示ON/OFFの全組合せを確認する。RETESTと内部 final_test、仕様版27以下も対象範囲どおりである。
4. 未確認ペアを表示中に再読み込みすると保存済みの表示内容が復元し、続行済みのペアは再表示されない。確認記録の再送は冪等で、不完全ペアへの確認記録は拒否される。
5. 採点は引き続き6設問の完了後にだけ行い、学習遷移・テスト回数上限・評価式を変えない。返却値に正答キー・解説・分類情報が含まれないことを確認する。
6. 管理APIが厳密なbooleanを検査し、ON/OFFのsnapshotが新規登録時だけ固定され、旧行を補完しないことを確認する。

この文書は採用仕様と受入条件を記録する。コード実装は完了しているが受入検証は未実施であり、研究条件の妥当性や実験開始の承認を示すものではない。
