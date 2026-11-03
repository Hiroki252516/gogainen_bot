# 設問1のみ出題する設定（2026-11-03）

## 現行条件

管理画面の「設問1のみ出題」は初期値OFF。ONでは新規参加者に各用語の設問1だけを出題する。対象3用語、6択単一選択、M1/M3/unknownの分類、テスト回数上限は維持する。

| 設定 | 事前・再テスト1/2・内部final_test | 用語ページ | 学習確認 |
| --- | --- | --- | --- |
| OFF | 設問1・2、計6問 | 2設問をまとめて保存 | 誤答設問の保存snapshot |
| ON | 設問1だけ、計3問 | 1設問を保存 | 誤答した設問1の保存snapshot |

内部final_testはRETEST1を共用する。設問2・3のYAML・ID・選択肢・旧snapshotは保持する。ONの参加者による設問2への直接回答は409で拒否する。教材対象は実際の誤答から決める。「設問ごとの答え合わせ」がONなら、出題した1設問または2設問の選択内容・正誤を同じ画面内で示す。正答・解説・内部分類は表示しない。

## 保存・API・互換性

- RuntimeSetting.first_question_only、Participant.first_question_onlyをnullable booleanとして追加する。設定未保存・旧NULLはOFFとして読むが、既存行を補完しない。
- 管理GET/PUT `/api/admin/first-question-only` は `enabled: boolean` と `applies_to: new_standard_participants_only` を返す。管理認証を必須とし、PUTは厳密なbooleanだけを受理する。GETはno-store。
- 新規登録時に参加者へ設定を固定する。後から管理スイッチを変えても登録済み参加者の問題数は変わらない。
- 用語ページPOSTのanswersは入力型上1〜2件。受理する件数・問題ID・回次は参加者snapshotで検証する。一括保存・ページ時間・冪等再送・再読み込み後の再送復元を維持する。
- 仕様版35・protocol・split-actions-v5を維持し、登録条件で区別する。旧版の閲覧専用条件を変更しない。

## 指標とログ

仮説の式・比較回次・欠測の扱いは維持し、完答と分母を出題条件に合わせる。仮説1の正答率は3問または6問。仮説4は同じ用語・設問番号を対応づける。仮説6の満点は対象3問または6問が重複なく採点済みで全問正解の場合とする。非出題の設問2を誤答・欠測に数えない。

指標版は `six-hypotheses-v4-question-selection`。管理の群集計・6仮説集計は3問条件と6問条件を分離する。混在時の6仮説APIは統合集計を返さず、`strata` 内に条件別集計を返す。同じ条件内でcontrol/proposedを比較する。条件間の難易度同等性・学習効果は保証しない。

参加者一覧・個別ログ・指標JSONでfirst_question_onlyを確認できる。固定CSVヘッダを維持し、統合ログCSVの参加者value_json、6仮説CSV/Excelの各行details_jsonに条件を記録する。details_jsonにはquestions_per_testも3または6で保存する。現行版の指標キャッシュは必要時に新指標版として追加し、旧版の評価・snapshotは再計算しない。

## 検証

登録時固定、認証・厳密入力、設問2拒否、保存・再送、答え合わせ、事前満点からfinal_test、学習確認snapshot、再テスト2回、満点判定、条件別CSVとDBの追加移行を検証する。画面側は1/2設問の表示・再送復元を確認する。結果は[14](14_testing_acceptance.md)に記録する。受入検証は実験開始承認と別に扱う。
