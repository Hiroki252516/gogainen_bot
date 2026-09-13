# Experiment Flow

## 対象と問題形式

新規セッションの対象は `llm_knowledge`、`multi_agent`、`memory_process` の3用語である。LangGraphおよび旧Transformer用語は新規フローから除外する。

pretest、retest、final_testと学習確認の固定複数選択問題は10択である。`l0_check`は自由回答、`transfer`は互換・補助の別形式であり、この選択肢ルールの対象外である。

- A〜C: 正解選択肢
- D〜F: M1選択肢
- G〜I: M3選択肢
- J: 「わからない」

A/B/Cの3つだけを選択した場合だけ正解とする。Jは単独選択の場合だけ有効であり、他の選択肢との同時選択は不正解である。不正解分類は `M3 > M1 > unknown` の順に決定する。

## フロー

1. 管理者から伝えられたA/Bコードを`/start`で入力し、`/consent`の仮同意書に同意して参加者を作成する。backendがAを`proposed`、Bを`control`へ変換する。同意前には`pretest`へ進めない。
2. `pretest`: 参加者向けには「テスト」と表示し、3用語を各1問出題する。正誤、ヒント、教材は表示しない。
3. 診断・学習対象選択: 正解済み用語を除き、誤答・unknownの用語を学習対象にする。
4. `learning`: 用語ごとに教材を生成し、確認問題を出題する。`enrichment`（豊富化）と`conceptual_change`（概念変化）の各学習段階に5バリエーションを持ち、6回目以降は5問目を再利用する。`scaffolding_level`のL3/L2は内部互換・ログ値であり、参加者向けの別段階ではない。
5. `retest`: 各用語を `retest_v1`〜`retest_v4` で出題する。5回目以降は `retest_v4` を再利用する。テスト中はヒントと即時正解表示を行わない。
6. 再テストの3用語を各1問ずつ採点し、1問でも不正解または未回答がある場合、backendは `current_step=learning_targets` とする。不正解・未回答用語を優先度順に学習対象へ戻し、最初の用語の学習URLを返す。追加の学習・再テスト周回はクライアントまたは研究者が再導線を開始して行う。サーバーが4〜6を自動反復する機能は未実装である。
7. 再テストの3用語が各1件あり、すべて正解の場合だけ、backendは `current_step=survey` として追加の確認を省略する。採点対象が不足するなど満点を確認できない場合も `learning_targets` に留める。
8. `final_test` は初回テストで学習対象がない場合に使う内部フェーズで、参加者向けには「再テスト1」と表示する。3用語を各1問出題し、全問正解ならアンケートへ進み、不正解または未回答があれば`learning_targets`へ戻り、最初の学習URLを返す。次の再テスト周回はクライアントまたは研究者が再導線を開始する。
9. `survey`: 通常完了時は仮アンケートを`participant_surveys`へ保存し、保存後に`current_step=finish`、`completion_reason=completed`を確定する。`retest`または`final_test`中のギブアップから来た場合は`completion_reason=give_up`とギブアップ時の`completed_at`を保持したまま`current_step=finish`へ進める。

学習セッション中の「学習をギブアップして再テストへ」は、回答を追加保存せず、開いている`TutorSession`を終了して`current_step=retest`へ進める。再テスト画面または`final_test`画面の「実験をギブアップして終了」は、`current_step=survey`、`completed_at`、`completion_reason=give_up`を確定してアンケートへ進める。学習対象確認画面からの同操作は`current_step=finish`へ進める。いずれも対象となる問題取得・回答・採点を受け付けず、アンケート送信後は`current_step=finish`へ進むが、ギブアップ時の`completion_reason`と`completed_at`は保持する。どちらの操作も`audit_events`へ参加者操作として記録する。

回答ログの `attempts.test_round` は、初回 `pretest` を `test`、最初の学習後確認を `retest_1`、次の確認を `retest_2` として保存する。`phase` は問題種別・既存API互換の内部値として残す。

L0確認・転移問題は互換・補助フェーズとして残すが、現行の主到達評価は `final_test` である。再テスト3用語が全問正解の場合だけ、再テスト満点を最終到達率相当として代用する。完全な転移評価、遅延再テスト、周回別の自動評価は将来対応である。DB上の旧問題・旧ログは削除しない。
