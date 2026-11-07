# 実験フロー

## 目標と現行経路

計画書の手順は、事前テスト、必要な用語の学習、再テスト、未達用語の再学習、満点または中断後のアンケートという流れ。6仮説の測定上の回数・対象経路は[01](01_research_requirements.md)と[12](12_evaluation_metrics.md)に定め、画面表示の変更で評価式は変更しない。

現行コードは仕様版41 / `experiment-plan-2026-11-07-split-actions-v6-q1-only-v1`。新規参加者は同意後に事前アンケートv2を完了し、PRETESTへ進む。通常版はsplit-actions-v6で、設問1のみ出題を登録時に固定し、各用語の設問1を出題する。教材は教材内解説モードに固定し、辞書v4を意味参照として使い本文内で説明する。教材生成は両群共通の指示・入力を土台にし、提案群だけに診断・タイプ別教授指示を加える。仕様版40以下・旧protocolは閲覧専用とし、結果は履歴バンクで復元する。詳細は[AI指示](10_ai_prompt_contracts.md)、[教材モード](41_learning_glossary_material_mode.md)、[事前アンケート](49_presurvey_baseline.md)、[選択肢条件](47_split_assessment_added_choices.md)。

新規登録・出題・学習・集計は通常版だけを扱い、問題バンクの切替経路はない。旧条件の保存データ削除は通常の起動・seedから分離し、[専用削除手順](../backend/scripts/purge_easy_mode_data.py)で明示実行する。

## 現行フロー（仕様版41）

1. start → consentで参加コードA/Bを受け取り、新しい参加者を作成する。
2. presurveyで用語事前知識6項目と普段のAI利用2項目へ回答し、必須8項目を保存してからpretestへ進む。未回答のまま事前テストは開始できない。
3. pretestで登録時snapshotに従い通常版の設問へ回答し、全設問の完了後に固定採点する。事前テストの全体結果表示は管理設定に従う。
4. 学習対象があればlearning_targetsから用語順に学習する。学習対象がなければ内部final_testへ進む。
5. 学習はAI教材＋固定確認問題。1用語・1セッションあたりの回答上限は既存仕様に従う。正解または上限到達後に次の対象へ進み、不正解の用語は未達のまま残る。
6. 全対象の学習後、retestで登録時snapshotに従い通常版の設問へ回答する。採点済みバッチは未回答を含めて1回とし、全問未回答は採点しない。初回未達は既存の再学習経路へ進み、最終回未達は未達のままsurveyへ進む。満点ならsurveyへ進む。
7. 事前テストで満点だった参加者は内部final_testへ進む。final_testの採点結果に応じ、満点ならsurvey、不正解・未回答があれば既存の学習後retest_v2へ進む。
8. survey（事後アンケート）保存後にfinish。

事前アンケートはphase=presurvey、事後アンケートはphase=posttestで別々に記録する。事後はシステム評価2項目・教材評価6項目（表示者のみ必須）・任意自由記述とし、仮説5はposttestだけを参照する。[画面仕様](09_frontend_ux_flow.md)、[評価定義](12_evaluation_metrics.md)、[保存契約](49_presurvey_baseline.md)を参照する。

事前後の問題variantは採点回次に対応して全用語共通に選ぶ。用語別の回答件数から回次を推測しない。学習後回数retest_cycles_completedはfinal_testを含めず、上限用のpost_pretest_tests_completedには採点済みfinal_testを加える。テスト回答中はチャット・ヒント・即時正解を表示しない。既存結果画面では従来どおり正誤を表示する。

学習ギブアップはretestへ進む。retest/final_testの実験ギブアップはsurveyへ進む。採点・ギブアップ・再送・先行生成は仕様版の確認後に実行する。学習確認の出題規則は両群共通で、unknownはenrichment、M1/M3はconceptual_change。同じ状態・回答・ターンなら同じ問題とvariantを使う。

仕様版39以下、旧protocol_id、NULL・未対応版の記録は閲覧専用で保全する。新規開始は同意を取り直して新しいIDを作成する。現行コードは新規参加者へ仕様版41を保存し、設問1のみ出題を登録時に固定する。教材内解説では辞書v4を意味参照として生成入力に含め、本文では逐語転載せず文脈に合わせて言い換える。教材の右側注釈欄は表示しない。教材生成の統制群には群別の自然言語方略指示を送らず、提案群だけに診断・教授指示を追加する。旧版の保存済み教材・注釈snapshotは変更しない。[事前アンケート](49_presurvey_baseline.md)、[教材モード](41_learning_glossary_material_mode.md)、[文字数契約](42_learning_glossary_material_length.md)、[辞書と言い換え](43_glossary_definition_paraphrase.md)、[PRETEST履歴](44_pretest_content_revision.md)、[RAG注釈](49_rag_glossary.md)。通常版ペア確認の契約は[40](40_question_pair_answer_review.md)に記録する。
