# Testing Acceptance

## Backend

- A/Bの有効な参加コードがない参加者作成は拒否され、Aは内部`proposed`、Bは内部`control`へ変換される。正常作成時は`assignment_method=admin_code`を保存し、参加者向けレスポンスに`group_condition`を含めない。同意なしの参加者作成も拒否され、同意画面から同意した場合だけ`pretest`へ進む。`survey`送信で`participant_surveys`が1件保存され、`current_step=finish`、`completion_reason=completed`になる。送信再実行でアンケートが重複しない。
- YAMLにactive termが `llm_knowledge`、`multi_agent`、`memory_process` の3件だけ存在する。
- pretest・retest・final_test・学習確認の固定複数選択問題がA〜Jの10選択肢で、A/B/C、M1、M3、unknownの配分が3/3/3/1になる。`l0_check`と`transfer`はこの配分の対象外である。
- pretest・final_testが各用語1問、retestが各用語4バリエーション、learning確認がstage・用語ごとに5バリエーションになる。
- A/B/C完全一致だけが正解、J単独だけがunknown、M3がM1より優先される。
- retestはv1〜v4を使い、5回目以降はv4を再利用する。
- learning確認はv1〜v5を使い、6回目以降はv5を再利用する。
- RAGは用語別の指定sectionだけを検索し、LangGraphチャンクを返さない。
- controlとproposedのRAG本文が共通で、proposedだけにtaxonomy・履歴・足場掛け情報が入る。
- app-server payloadが `gpt-5.6-luna` / `medium` を使う。
- 正答時は `generate_correct_answer_summary`、誤答時は `explain_selected_distractor` が呼ばれ、解説生成の目的とpayloadが `AICallLog` に記録される。
- `/api/participants/{participant_id}/learning-targets` が、既存の未達対象 `targets`、互換用 `pretest_results`、直近の `test_results`（周回名、問題文、本人が選んだ選択肢本文、正誤）を返す。`test_results` に正答、期待解答、選択肢ごとの正誤、M分類などの内部診断値を含めない。
- 解説生成に失敗した場合、固定採点結果や学習状態を部分確定せず、Mockへ自動フォールバックしない。
- 学習ギブアップAPIが開いている学習セッションを終了し、`current_step=retest`と`next_url=/retest`を返す。ギブアップした学習ターンは回答として保存しない。
- 実験ギブアップAPIが`current_step=finish`、`completed_at`、`completion_reason=give_up`を確定し、終了後の再テスト取得・回答保存・採点・学習セッション操作を409で拒否する。学習ギブアップは`completion_reason`を変更せず、両操作を`AuditEvent`へ記録する。管理画面の参加者一覧・詳細とCSVで状態・回数・操作時刻を確認できる。
- 管理画面の評価サマリー・群集計・被験者ログ・ログCSV参照時に、3用語の採点済み事前テストがある参加者の評価サマリーが再計算ボタンなしで作成・更新される。事前テストだけの参加者は誤概念推移を「未分類」とし、再テスト済みのように扱わない。

## Frontend

- `/start`で参加コードを入力し、同意書画面を経由してpretestへ進む。同意前や不正コードでは参加者を作成せず、被験者画面に群名・内部群の対応を表示しない。テスト終了後は仮アンケート画面を表示し、送信後に終了画面へ進む。
- pretest/retest/final-testで3用語が表示される。
- 10択複数選択UIで、3つまたはJ単独以外は送信できない。
- 学習画面にM1〜M4、unknown、LangGraph、内部教授方略を表示しない。
- 学習本文、問題、結果表示がモバイル幅で重ならない。
- 学習問題への回答後も問題文と選択肢を同じ画面に残し、その下に正解・不正解とフィードバックを表示する。回答済みの選択肢は変更できない。
- 学習セッション初回読み込み中に、スピナー、経過秒数、4つの安全な進捗状態が表示され、読み込み完了後に消える。
- 初回読み込みAPIが失敗した場合、進捗表示が停止し、既存のエラーメッセージだけが表示される。
- 「次の確認へ」の取得中も直前の正誤・解説を残した進捗カードが表示され、経過秒数と4つの安全な処理状態を示す。取得完了後に新しい確認問題へ置き換わり、取得エラー時は進捗表示が停止する。
- `/learning-targets` でテスト・再テストの周回名、3用語の問題文、本人が選んだ選択肢本文、正解・不正解・未回答が表示され、正答そのものは表示されない。不正解用語だけが学習開始対象として扱われる。
- 回答送信中にスピナー、経過秒数、4つの安全な処理状態、`分析中...` ボタンが表示される。
- 正答時は緑色の正誤カードとMarkdown要点解説、誤答時は赤色の正誤カードとMarkdown見直し解説が表示される。
- 解説表示後もAPIの `item_results` フィールドと次の確認への遷移が維持される。現行の固定複数選択フローでは `item_results` は空配列であり、個別結果の表示は値がある場合に限る。
- AIの内部思考過程、M1〜M4、誤概念taxonomyが被験者画面に表示されない。
- 旧stage名や旧Transformerの新規導線に依存しない。
- 学習画面のギブアップ操作は再テストへ遷移し、再テスト画面と再テスト結果確認画面のギブアップ操作は終了画面へ遷移する。確認ダイアログを表示し、事前テストには表示しない。
- ギブアップボタンは「次へ」などの回答操作から離れた画面下部の右寄せ領域に表示される。
- 管理画面の誤概念推移では`regressed`を「誤概念」と表示し、学習回答に「学習十分」「学習不十分」の集計カードを表示しない。

## Regression

この文書の項目は現行MVPの受入観点と将来機能の回帰観点を含む。M2/M4固定問題、遅延再テスト、手動診断修正とその監査、完全な転移評価は現行MVPの必須受入条件ではなく、将来対応として別途検証する。参加者削除、学習・実験ギブアップとそれらの監査記録は現行MVPの受入対象である。

- `AI_BACKEND=mock` で固定問題・遷移・RAG契約テストが通る。
- `AI_BACKEND=codex_app_server` でMockへ自動フォールバックしない。
- 既存の単一選択API互換、DB列、CSV列、過去ログを壊さない。

## Commands

```bash
cd backend && .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
docker compose build backend frontend
docker compose up -d --force-recreate backend frontend
```
