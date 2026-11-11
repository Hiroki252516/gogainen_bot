# 受け入れ条件と検証記録

## 2026-11-11 事後アンケート教材量の設問文更新（仕様版50・fix/issue-329）

- 新規参加者の事後アンケートを`posttest-5point-v2`へ更新し、設問文を「今回の教材の量はどの程度でしたか」に変更した。回答選択肢、`amount_appropriateness`、5段階の回答形式、教材量をH5対象外として分布のみ集計する契約は維持する。
- 仕様版を50、protocolを`experiment-plan-2026-11-11-posttest-material-amount-wording-v1`へ更新した。仕様版49以前の参加者・回答は読み取り専用で保全し、変換・上書きしない。
- `backend/tests/test_plan_aligned_protocol.py`: `44 passed`、`backend/tests/test_current_experiment_spec.py`: `76 passed`（計2件のDeprecationWarning）。仕様版49の旧回答・読取専用性、v1の新規送信拒否、H5の現行版限定、登録時の仕様版・protocolを確認した。
- Frontend `npm test`と`npm run build`（TypeScriptを含む）が成功した。テストでは事後画面の新設問文と管理画面の教材量分布ラベルを確認した。
- `git -c core.whitespace=cr-at-eol diff --check`が成功した。実ブラウザでの画面確認は未実施。研究上の承認を意味しない。

## 2026-11-10 H5集計分母の整合性修正（PR #322 review follow-up）

- H5の群別`eligible_count`を教材閲覧者から4項目すべて評価不能の人数を除いた数に修正した。`missing_count`は適用対象者と数値回答者数の差とし、未閲覧・全項目評価不能を未回答へ混ぜない。
- 閲覧済み・回答済み、閲覧済み・未回答、4項目すべて評価不能、未閲覧を混在させた回帰テストで分母、欠測、対象外およびCSV詳細値を確認した。
- Backend関連テストは`45 passed`（警告1件）。`git diff --check`が成功した。

## 2026-11-10 事後アンケート5段階化（仕様版49・feature/issue-316）

- 新規参加者向け事後アンケートを`posttest-5point-v1`として追加し、現行のシステム2項目・教材6項目を維持した。5段階評価と項目別の「評価できない」を保存・復元し、未閲覧者の教材評価`null`と評価不能・未回答を区別する。旧版の回答と集計は変更しない。
- H5は教材の内容理解・読みやすさ・日本語表現・正しい理解への役立ち度の数値回答平均とし、評価不能を除外した有効回答数を記録する。難易度・分量の分布は別出力し、H5には含めない。
- Backend全体テストは隔離環境で`1709 passed`（警告6件）。Frontend `npm test`と`npm run build`（TypeScript検査を含む）が成功した。
- 別ポートの隔離Mock環境で1440px・390px、教材閲覧・未閲覧の4通りをブラウザ確認した。必須評価、評価不能、任意記述、送信・復元、横はみ出しがないことを確認した。
- `git diff --check`が成功した。研究DB、localhost:3000、実AIは使用せず、コミット・pushは行っていない。尺度の妥当性および研究上の承認は確認していない。

## 2026-11-10 事前アンケートの見聞き経験・理解度分離（仕様版48・feature/issue-315-true）

- 新規参加者の同意後、事前テスト前にモード別版の事前アンケートを必須化した。通常2モードは`presurvey-baseline-v3`、4用語版は`presurvey-four-topic-baseline-v2`を使う。
- 各6用語の見聞き経験を「ある／ない／覚えていない」で取得し、「ある」の場合だけ4段階理解度を必須表示する。「ない／覚えていない」は理解度をnullで保存する。直近30日AI利用頻度と3項目のAI活用自己評価（5段階・評価できない）を取得する。定義や正答説明は提示しない。
- 旧事前アンケート回答を移行せず、事後アンケート・仮説式は変更しない。回答は`phase=presurvey`と版を付けて既存ParticipantSurveyへ保存し、ログ・CSV/Excelで区別する。仕様版47以下は閲覧専用で保全する。
- Backend全体テストは`1706 passed`、警告5件（既存のNumPy/joblib・SQLite日時adapter DeprecationWarning）。変更関連テストはBackendの既存テスト一式に含めて確認した。
- Frontend `npm test`と`npm run build`（TypeScript検査を含む）が成功した。
- 専用のPlaywrightブラウザテストおよびPC・スマートフォンの実ブラウザ表示確認は未実施。環境にPlaywrightがなく、専用テストは隔離Mock backendとブラウザ依存の準備が必要なため、画面検証を完了した扱いにはしない。
- 研究DB、localhost:3000、実AI、コミット・pushは使用・実施していない。尺度の妥当性、回想誤差、回答負担、問題モード間の比較可能性、研究上の承認は未確認。

## 2026-11-10 事前テスト満点時の早期終了（仕様版47・feature/issue-315）

- 新規参加者の仕様を47 / `experiment-plan-2026-11-10-pretest-perfect-early-exit-v1`へ更新した。3つの問題モードすべてで事前テスト全問正解なら、保存済み結果表示snapshotに応じて結果確認後または直接surveyへ進み、学習・内部`final_test`・再テストは開始しない。未達時の学習・モード別再テスト経路と既存結果表示設定は維持する。
- 早期終了ルートを`pretest_perfect_early_exit`として区別し、H1/H2/H6に値を補完しない。登録者数、早期終了者数、指標の`eligible_count`・対象外数を分け、モード別集計とCSV/XLSXで確認できるようにした。H3〜H5の既存対象外判定は維持する。
- Backend全体テストは`1703 passed`（488.43秒、既存DeprecationWarning 6件）。仕様・早期終了を扱う重点テストは`12 passed`。
- Frontend `npm test`と`npm run build`（TypeScript検査を含む）が成功した。実ブラウザの画面確認は実施していない。
- 受入記録を含めた`git diff --check`が成功した。研究DB、localhost:3000、実AI、コミット・pushは使用・実施していない。早期終了の研究上の承認や測定特性は確認していない。

## 2026-11-09 4用語版の固定2回フロー（仕様版45・fix/issue-300・履歴）

- 新規参加者を仕様版45 / `experiment-plan-2026-11-09-four-topic-two-retest-rounds-v1`へ固定した。4用語版だけ事前テスト後・再テスト1後の満点時にも学習へ進み、対象がない場合は4用語すべてを通常学習対象とする。再テスト2採点後は正誤にかかわらずsurveyへ進む。他モードの早期満点終了、2回の再テスト上限、問題バンク・採点・DB構造は変更しない。
- 隔離DBの統合テストで、事前テスト・再テスト1・再テスト2の満点／誤答ケースを組み合わせ、誤答がある回は誤答用語だけ、満点回は4用語すべてを対象とすることを確認した。各対象の通常`tutor-sessions`作成、final_test拒否、3回目のテスト拒否、再テスト2後のsurvey遷移を確認した。仕様版44の通常バンク復元と保存snapshotを変更しないことも確認した。
- 対象Backendテスト`83 passed`。Backend全体`1751 passed`（591.76秒、警告6件）。Frontendテスト一式とNext.js production build/TypeScript検査も通過した。
- Playwright依存がFrontendにないため、実ブラウザでのPC・スマートフォン画面遷移確認は未実施。研究DB・既存3000番環境・実AIは使用していない。
- 文書追記後の`git diff --check`も成功した。

## 2026-11-09 4用語版を未設定時の既定値にする（仕様版45・fix/issue-309・履歴）

- 仕様版45 / `experiment-plan-2026-11-09-four-topic-foundation-default-v1`を新規参加者へ適用する。未設定時の既定値を`four_topic_fundamentals`にし、管理画面の3モード切替は維持する。
- RuntimeSettingに`application`または`basic_understanding`などの保存値がある場合は尊重し、設定値の自動書換え・DB移行を行わない。新規Participantには登録時選択値をsnapshotする。
- 仕様版44以下は読み取り専用。保存済み`test_content_mode`から当時の問題バンクを復元し、問題・回答・snapshotを変更しない。
- 未設定時の管理API応答、新規Participantのモード・仕様版・protocol・4用語事前アンケート・4問の出題をBackendテストで確認する。保存済み各モードの切替・snapshotと、仕様版44各モードのバンク復元も確認する。
- 関連Backendテスト8ファイルは隔離SQLiteで`188 passed`。管理API未設定時の4用語版、仕様版45 Participant snapshot、4問出題、保存済み3モードのsnapshot、仕様版44の3バンク復元・読み取り専用を含む。
- Frontend `npm test`、Next.js production build/TypeScript検査が成功した。Backendに既存のDeprecationWarningが2件ある。
- `git diff --check`が成功した。研究DB、3000番環境、実AIは使用していない。

## 2026-11-09 main統合：4用語版既定と固定2回フロー（仕様版46）

- 仕様版45には「現行版既定・4用語版のみ固定2回フロー」と「RuntimeSetting未設定時に4用語版を既定」の二つのprotocolがあるため、両条件を仕様版46 / `experiment-plan-2026-11-09-four-topic-default-two-retests-v1`に統合した。新規登録では保存済み問題モードを尊重し、未設定時は4用語版とする。
- 仕様版46は4用語版を満点でも2回の再テストまで進行させ、満点時は4用語すべてを学習対象にする。他モードの満点時早期終了を維持する。仕様版45以下は閲覧専用とし、各protocol・保存済みモード・問題snapshotの復元を維持する。
- PR #312のレビューに伴い、仕様版46を履歴バンク表から除外した。現行バンクはParticipantの保存済み`test_content_mode`から解決し、snapshot欠落・不正値は別バンクへフォールバックせず503にする。仕様版45以下のprotocol別・版別復元は維持した。従来の6テストは現行版が履歴表にないことを検証する形へ戻し、現在のsnapshot欠落エラーも追加した。
- 4用語版の固定学習対象設定前に既存割当の対象フラグを解除し、対象集合を順序に依存せず検証する回帰ケースを追加した。関連Backendテスト730件と、最終変更を含む重点テスト7件が通過した。
- Backend全体は`1758 passed, 1 failed`。失敗は今回変更していない`tests/test_tutoring_prompt_yaml.py::test_rendered_prompt_matches_expected_contract_hashes`で、固定期待hashとレンダリングpromptの不一致。Frontendは変更していない。`git diff --check`は成功。研究DB・3000番環境・実AIは使用していない。

## 2026-11-09 4用語版の選択肢別正誤表示（fix/issue-303）

- 4用語版の回答後確認応答では選択済み選択肢だけにID・個別正誤を含め、設問全体の正誤は従来どおり別に保持する。出題中の問題データ、採点、保存、学習対象、進行は変更しない。
- 画面は選択済みの各選択肢を個別に色分けし、設問全体の判定を別表示する。未選択選択肢の正誤は表示しない。単一選択モードは従来の設問判定を使う。
- C・E・Hを選ぶ回帰ケースではCのみ個別正解、E/Hは個別不正解、設問全体は不正解とする。全正解3択とJ単独も含めて確認する。
- この表示修正は進行中参加者にも適用する。DB、仕様版、protocol、保存済み回答は変更しない。
- Backend全体`1746 passed`、関連Backendテスト`9 passed`、Frontendテスト、Next.js production build、`git diff --check`が成功した。
- PlaywrightがFrontend環境にないため、隔離Mockでの実ブラウザ・PC／スマートフォン目視確認は未実施。画面検証を完了した扱いにはしない。

## 2026-11-09 4用語版問題モード（仕様版44・feature/issue-297）

- 新規参加者用に`four_topic_fundamentals`を追加し、従来の`application`・`basic_understanding`と登録snapshot・設定既定値を分離した。対象語はTransformer、LLMの学習段階、マルチエージェント、記憶プロセス。
- 添付問題の本文と選択肢を独立問題バンクへ追加した。事前・再テスト1/2・内部final_testの同一本文、3択/J単独、配置、誤答確認snapshot、複数選択UIを検証する。
- TransformerとLLM学習段階のRAG節指定、4用語用presurvey、4問分母のモード別仮説集計、ログ・CSV/XLSXを検証する。
- Backend全体は隔離SQLiteで`1744 passed`。Frontendテスト、Next.js production build/TypeScript検査、`git -c core.whitespace=cr-at-eol diff --check`も通過した。
- 隔離SQLiteの`/api/health`は`200 OK`、別ポート`3101`の管理画面HTMLも`200 OK`。ブラウザ自動操作環境がないため、実画面の視覚確認は未実施。
- PR #298レビュー対応として、仕様版43で`test_content_mode`がNULLの記録は旧既定バンク`split-actions-v5`で復元し、仕様版44のNULLはエラーとして拒否することを確認した。関連Backendテストは`17 passed`。
- 問題の反復による練習効果、問題モード間の難易度・測定特性・回次同等性、研究上の承認は実証・確認していない。

## 2026-11-08 基礎理解版問題モード（仕様版43・feature/issue-295）

- 管理画面の問題モードを新規参加者の登録時にsnapshotし、`application`と`basic_understanding`で問題取得・回答保存・復元・仮説集計を分離した。旧仕様版42以下の記録とNULLモードの履歴解釈を保持する。
- 基礎理解版の問題バンクは3回次×3用語の9問を持ち、各問題に正解1・M1誤答2・M3誤答2・unknown1を格納する。現行の設問1のみ出題条件に従い、各テストではモードごとの3問を出題する。研究者向け分類理由は参加者用問題バンクに含めない。
- Backend全テストは隔離SQLiteで`1743 passed`。FrontendテストとNext.js production build/TypeScript検査、`git diff --check`も通過した。Frontend smoke testの管理画面期待値は、内部バンクIDではなく実際の表示名を検証するよう更新した。
- 基礎理解版が易しいこと、現行版との難易度・測定特性・回次間の同等性、および研究上の承認は検証・確認していない。実験開始前の研究者確認が必要。
- 研究DB・localhost:3000・実AIは使用していない。ブラウザでの参加者一連の実操作は未実施。

## 2026-11-07 Codex Fast mode切替（feature/issue-293）

- 管理APIに厳密なBooleanのFast mode更新を追加した。初期値はOFFで、プロセス内の一時設定として保持し、再起動後はOFFへ戻す。Mock backendでは状態をONにできず、HTTP 409で拒否する。
- app-serverのモックtransportで、ON時の`turn/start`に`serviceTierForTurn: "fast"`、OFF時に`"default"`を渡し、設定値と実際のtierが監査payloadに記録されることを確認した。要求値を受け付けられない場合にdefaultへフォールバックしない。
- 隔離SQLite・別ポートのheadless Chromeで管理画面を操作し、初期OFF、ON/OFF保存、保存失敗時の状態維持とエラー表示を確認した。AI接続先は到達不能なローカルURLとし、AI呼び出しは行っていない。
- Backend全テスト`1740 passed`、FrontendテストとNext.js production build/TypeScript検査、`git diff --check`が成功した。既存のDeprecationWarningが6件ある。
- 研究DB、localhost:3000、実AI、DB schema、実験仕様版は変更・使用していない。

## 2026-11-07 管理画面のGPT-6 Astra・推論レベル追加

- 許可値に`gpt-6-astra`、`xhigh`、`max`を加え、既定の`gpt-6-luna / low`とプロセス内だけの一時設定は維持した。認証付き管理APIで許可値一覧、全選択値の更新、不正値の422を確認した。
- モックapp-server transportで、現在選択可能な全モデルと`xhigh`/`max`の組み合わせがthread/start、turn/start、監査payloadへ同一値で伝わることを確認した。実AI app-serverへの接続・アカウント別の利用可否は検証していない。
- backend全1728テスト、frontendテスト、Next.js production build/TypeScript検査、git diff --checkに合格。既存のDeprecationWarningが6件ある。
- DB、実験仕様版・protocol、既定モデル・推論レベル、研究DB、実AI、3000番環境は変更・使用していない。

## 2026-11-07 仕様版41固定設定・統制群プロンプト統合（履歴）

- 仕様版40には固定設定化と統制群共通プロンプト化の別protocolが存在したため、両変更を統合する仕様版41 / `experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`を追加する。両仕様版40 protocolは履歴・閲覧専用とし、既存参加者の問題・回答・教材・snapshotは変更しない。
- 新規参加者のテスト条件（結果非表示・設問レビューON・設問1のみ）と教材内解説固定は維持し、教材生成では統制群の群別自然言語方略指示を除く。提案群の診断・教授指示は維持する。
- このマージ後のテスト結果は以下に追記する。研究DB・localhost:3000・実AIは使わず、コミット・pushは行わない。
- 解決後のBackend全テストは隔離SQLiteで`1718 passed`。関連する仕様版・教材モード・用語注釈・選択肢根拠のテスト`208 passed`も確認した。Frontendの`npm test`と`npm run build`（TypeScript検査を含む）が通過した。
- 競合マーカーは残っておらず、`git diff --check`と`git diff --cached --check`が通過した。研究DB・localhost:3000・実AIは使用していない。マージコミットは作成していない。

## 2026-11-07 管理画面の固定設定化（仕様版40・fix/issue-280の履歴）

- 新規参加者は`experiment-plan-2026-11-07-fixed-admin-settings-v1`へ登録し、テスト全体の結果確認なし、設問ごとの答え合わせあり、各用語の設問1のみ（計3問）に固定する。教材モードは従来どおり`integrated_material`。
- 旧RuntimeSetting値に依存せずParticipant snapshotを作る。3つの設定操作UI、教材モード表示、設定GET/PUT API、集計条件セレクターを削除する。参加者一覧・個別ログの旧設定値表示も除く。
- DB列、participant log API、CSV、過去の問題・回答・snapshotは保持する。仕様版39以下は閲覧専用とし、新しい設定を既存参加者へ遡及しない。
- Backend全体テストは隔離DBで`1714 passed`。Frontendの`npm test`と本番ビルドは成功した。
- Playwrightの隔離Mockブラウザで、管理画面・参加者一覧・個別ログに対象設定がないこと、旧設定APIのGET/PUTが404となること、新規Participantの固定値、3問の進行、各問の答え合わせ、全体結果画面を省略した学習遷移を確認した。390px幅でも横はみ出しがない。
- `git diff --check`は成功。隔離ブラウザ起動時にrewrite先を直す前、既定の`:8000`へ管理ログインとAI状態照会だけが通ったためMock以外の応答を検知して登録前に中断した。研究DB操作・参加者登録・AI生成呼び出しはなく、以降は別ポートの隔離Mock環境だけで確認した。localhost:3000と実験開始環境は使用していない。

## 2026-11-07 仕様版41教材文字数・統制群プロンプト統合（履歴）

- 仕様版40の二つの変更を別protocolの履歴として保ち、仕様版41 / `experiment-plan-2026-11-07-learning-material-target-800-control-shared-prompt-v1`へ統合した。当時の教材本文は800文字程度を目安とし、上下限による合否判定・長さを理由にした再生成を行わず、統制群への群別自然言語方略指示を除いた。
- 仕様版41以下の参加者は仕様版42への更新後、閲覧専用。旧仕様版のいずれのprotocolも現行版として扱わず、既存教材・回答・snapshot・監査記録は変更しない。結果復元は仕様版39〜41で通常版問題バンク`split-actions-v5`を使い、仕様版41の`split-actions-v6-q1-only-v1` protocolに限りprotocol IDでV6を選ぶ。
- 教材生成prompt、仕様版・protocol、旧問題版復元、用語辞書・教材snapshot、学習確認、回答履歴、必須教授要素に関するBackendテスト8ファイルは合計`196 passed`（164件と32件の2回に分けて実行）。DeprecationWarning 2件。
- `git diff --check`と競合マーカーの残存確認は通過した。
- Frontendテスト・buildとブラウザ確認は、Frontendコードを変更していないため未実施。研究DB・localhost:3000・実AIは使用していない。マージコミットは作成しない。

## 2026-11-07 origin/main統合（仕様版42）

- 仕様版41に存在した固定管理設定と教材生成条件の別protocol履歴を保持したまま、仕様版42 / `experiment-plan-2026-11-07-fixed-admin-settings-learning-material-target-800-control-shared-prompt-v1`を現行とする。新規参加者は全体結果非表示、設問ごとの答え合わせON、各用語の設問1のみ（計3問）、教材内解説に固定する。
- 教材本文は800文字程度を目安とし、長さによる合否判定・再生成は行わない。統制群に群別自然言語方略指示を加えず、提案群の診断・教授指示を維持する。prompt YAML設定とその読み込み処理を取り込む。
- 仕様版41以下は閲覧専用。旧問題・回答・教材・snapshot・監査記録は書き換えない。仕様版41のmainline二protocolは問題バンクv5、`split-actions-v6-q1-only-v1` protocolはV6で結果を復元する。今回の競合解消ではテストを実行していないため、以下の件数はorigin/main統合時点の検証記録である。
- Backend全体テストは隔離SQLiteで`1721 passed`。prompt設定・教材文字数・用語モード・問題履歴・固定テスト条件に関する重点テスト10ファイルも`217 passed`。最初の重点実行では固定条件テスト1件が統合前の仕様版41 protocolを期待して失敗したため、現行仕様版42 protocolへ期待値を更新して再実行した。
- `git diff --check`と`git diff --cached --check`、競合マーカーの残存確認は通過した。PRにFrontendコードの差分はないため、Frontendテスト・buildとブラウザ確認は未実施。

## 2026-11-09 現行仕様書の実装照合（docs/issue-307、仕様版44時点の履歴）

- 作業時点の仕様版44 / `experiment-plan-2026-11-09-four-topic-foundation-v1`、現行YAML、Backend/FrontendコードにREADME、AGENTS.md、運用・API・画面・評価・プロンプト・データ仕様を照合した。
- 3問題モードと登録時snapshot、モード別アンケート・仮説集計、設問別回答確認と全体結果非表示、用語ページ単位の時間、CSV/XLSX出力を当時の現行説明へ反映した。仕様版43以下、仕様版25〜48の採用記録、docs/historyは履歴として保持し、現行仕様と混同し得る文書には適用範囲の注記を置いた。
- その時点ではMarkdown文書だけを変更し、アプリコード・実験条件・保存データは変更していない。Backend/Frontendの動作テストは文書のみの変更のため実施対象外。Markdownのローカルリンク先検査と`git diff --check`は成功し、検査で見つけた存在しない仕様版34文書への参照を実在するv4期待値fixtureへ修正した。
- 研究DB・localhost:3000・実AIは使用していない。マージコミットは作成しない。

## 統合前の仕様版40記録：目標800文字（fix/issue-278）

- 別ブランチでは新規参加者を仕様版40 / `experiment-plan-2026-11-07-learning-material-target-800-v1`へ更新し、教材本文は800文字程度を目安とした。上下限の合否判定・長さのみを理由とした再生成を廃止し、構造・教授内容などの検証を維持した。新規の生成監査には実文字数と目標だけを記録する。
- 当時の検証ではBackend全テストが隔離SQLiteで`1712 passed`。教材本文80文字・2000文字が文字数を理由に再生成されず、構造・教授契約違反では再試行する関連テスト144件も通過した。Frontend全7スクリプトとbuild、`git diff --check`も通過した。
- このprotocolは統合後の現行protocolではない。記録は当時の実行結果として保持し、API・DBスキーマ等の現行条件とは区別する。

## 統合前の仕様版40記録：統制群の共通プロンプト（fix/issue-279）

- 別ブランチでは仕様版40 / `experiment-plan-2026-11-07-control-shared-prompt-v1`を適用し、統制群から通常教授方略を説明する3つの自然言語指示を取り除いた。共通ルール・入力、提案群の診断・タイプ別教授指示、出力Schema enumとBackend検証は維持し、統制群の内部`teaching_strategy`を`general_explanation`に固定した。
- 当時の検証では仕様版40の登録・出題、旧3文の除去と提案群指示を含む重点テスト104件、Backend全体1716件が通過した。Frontendは未実施、`git diff --check`は通過した。
- これら二つの仕様版40記録は別protocolのブランチ検証であり、同時に有効だった条件ではない。統合時に仕様版41へ上げ、両変更を新protocolへまとめた。研究DB・localhost:3000・実AI・コミット・pushは当時の検証でも使用していない。

## 2026-11-06 教材内解説の標準化（仕様版39・fix/issue-273）

- 新規参加者へ仕様版39 / `experiment-plan-2026-11-06-learning-glossary-integrated-default-v1`を適用し、保存済みRuntimeSetting値に関係なく`integrated_material`を記録する。管理画面のモード切替と管理用GET/PUT APIを削除する。RuntimeSettingの旧列、参加者の履歴値、ログ・CSV、既存教材とglossary snapshotは維持する。
- 仕様版38以下は既存方針どおり閲覧専用とし、仕様版38の通常版問題・結果は`split-actions-v5`で復元する。教材生成の意味参照、文字数条件、右側教材注釈欄の非表示、回答後解説・テスト注釈は維持する。
- Backend全テストは隔離SQLiteで`1704 passed`。教材モード関連を含む5ファイルの重点テストは`89 passed`。仕様版38の問題snapshot復元、閲覧専用判定、旧modeログ保持、新規登録のRuntimeSetting値3条件（注釈欄のみ／教材内解説／NULL）を確認した。
- Frontendの`npm test`全スクリプトと`npm run build`（TypeScriptを含む）が通過した。管理画面に切替UI/API参照がなく、過去ログ用のmode表示が残ることを確認した。Playwrightランタイムが利用できないため、隔離ブラウザでの画面確認は未実施。`git diff --check`も通過した。
- 研究DB・通常のlocalhost:3000環境・実AI・GitHub Actions・コミット・pushは使用しない。自動検証は用語説明の意味的正確さや学習効果を実証しない。

## 2026-11-06 易しいモードの実行停止と削除手順

- 新規登録・出題・学習・集計から問題版分岐を除き、通常版だけを使用する。Participant/RuntimeSettingの旧モード列と専用問題資産を削除処理で除去するまで、アプリ起動を匿名エラーで停止する。旧問題版APIは404、旧フィルター付き集計要求は422とし、通常版の履歴バンク・回答snapshot復元を維持する。
- Backend全テストは使い捨てSQLiteで1701 passed。API、purge、履歴復元に関連する現行テスト12件も、集計CSV・XLSXの旧フィルター拒否を含めて通過した。Frontendの全テストスクリプトとproduction build（TypeScriptを含む）も通過し、`git diff --check`は通過。
- Playwrightランタイムが利用できないため、隔離ブラウザの目視確認は未実施。管理画面の廃止UIとAPI挙動はFrontend smoke/API統合テストで確認した。
- purgeスクリプトの合成隔離DBで、easy参加者関連行・対応表・CSV・専用問題の削除、通常参加者データの不変、中断後の再試行、識別子を含まない集計監査要約、列削除、ローカルパスのsymlink拒否を確認した。
- 研究DBと実対応表へのdry-run/削除は実行していない。明示的な研究環境接続設定がないため、運用担当者がアプリ停止とバックアップ方針を確認したうえで専用スクリプトを実行する必要がある。ローカル`.local`成果物の削除も実行していない。
- 研究DB、通常のlocalhost:3000環境、実AI、GitHub Actions、コミット・pushは使用していない。自動テストは研究上の妥当性や学習効果を実証しない。

## 2026-11-05 origin/mainとの統合（仕様版38）

- 仕様版36がRAG辞書追加と事前アンケートv1で重複していたため、事前アンケートv2と辞書v4を合わせた仕様版38 / `experiment-plan-2026-11-05-presurvey-baseline-v2-rag-glossary-v1`を現行版とした。仕様版36の両protocolと仕様版37は閲覧専用とし、当該版の通常版テスト結果は`split-actions-v5`で復元する。現行問題バンク・辞書、保存済み回答・snapshotは変更しない。
- Backend全テストは`1768 passed, 107 skipped`。統合対象6ファイルは`188 passed`。Frontendの`npm test`全スクリプトと`npm run build`（TypeScriptを含む）が通過した。
- 競合ファイルをすべて解決し、`git -c core.whitespace=cr-at-eol diff --check`も通過。ブラウザでの目視確認は未実施。
- 研究DB、既存localhost:3000環境、実AIは使用していない。マージコミットは作成していない。

## 2026-11-04 RAG用語注釈の追加（仕様版36・fix/issue-268、統合前履歴）

- 新規参加者は仕様版36 / `experiment-plan-2026-11-04-rag-glossary-v1`、共通辞書v4で開始する。v3と既存snapshotは変更せず、仕様版35以下を閲覧専用とする。仕様版35の結果復元には`split-actions-v5`を使う。
- YAML比較でv3が不変、v4がv3へRAG（検索拡張生成）entryだけを追加し、定義・別表記・出典を辞書v1から引き継ぐことを確認した。
- Backend全体は隔離SQLiteで1765 passed・107 skipped。用語注釈、snapshot保存・再表示、辞書v1〜v4比較、仕様版35のv5復元と閲覧専用、仕様版36登録を含む関連テスト85件も通過した。
- Frontendの7テストスクリプトとproduction build（TypeScript検査を含む）、`git diff --check`が通過した。
- 研究DB、既存3000番環境、実AIは使用していない。語義の教育的妥当性・学習効果は自動テストで実証していない。
## 2026-11-04 事前知識4段階化（仕様版37・feature/issue-265）

- 事前アンケートの6用語を「知らない／聞いたことがある／意味を知っている／説明できる」の4択に変更し、`unknown`・`heard_of`・`knows_meaning`・`can_explain`として保存する。新規参加者には`presurvey-baseline-v2`を適用し、既存の仕様版36以下のBoolean回答は変換せず閲覧専用で保持する。
- 対象Backendテスト6ファイルで118 passed・100 skipped。`frontend`の`npm test`と`npm run build`が成功し、4カテゴリの送信値、事後アンケートからの項目除外、仕様版36記録の保全を確認した。
- Playwrightによる隔離ブラウザの視覚確認は未実施。研究DB・localhost:3000・実AIは使用していない。
- `git -c core.whitespace=cr-at-eol diff --check`通過。

## 2026-11-04 事前アンケート追加（仕様版36・feature/issue-265、履歴）

- 新規参加者は同意後に事前アンケート8項目を必須回答し、保存後に事前テストへ進む。欠落拒否、再送、事前テスト開始ガード、事前/事後の別phase・版でのログとCSV出力、仮説5が事後アンケートだけを参照することを確認する。
- Backend全テストは1765 passed・107 skipped、失敗なし。既存DeprecationWarning 2件。事前知識の必須項目、posttest v1/v2互換、仕様版35以下の記録保全も含む。
- Frontend `npm test`の全スクリプトと`npm run build`（TypeScriptを含む）が成功。smoke testは事前アンケート画面・同意後の遷移・事後フォームからの移動項目除外を確認する。
- 隔離ブラウザ確認はPlaywrightランタイムが環境にないため未実施。`frontend/tests/presurvey-browser.mjs`は隔離Mock環境用に追加済み。PC/スマートフォンの視覚的確認は残課題。
- `git diff --check`通過。研究DB・localhost:3000・実AIは使用していない。仕様版36は新規参加者だけに適用し、既存回答・保存済み評価は変換しない。アプリ内同意文書の変更は研究倫理上の承認を意味しない。

## 2026-11-03 設問1のみ出題する管理設定

- [48](48_first_question_only.md)の設定を追加。初期値OFF、登録時固定。ONは各用語の設問1だけ計3問、OFF/旧NULLは設問1・2の計6問。事前・再テスト1/2・内部final_test、学習確認、答え合わせ、満点・指標分母を対応させる。
- 新機能のBackend 9件が通過。厳密入力・認証、設定の保存、登録後の設定切替、設問2の直接回答拒否、保存と再送、答え合わせON/OFF、final_test、学習確認snapshot、再テスト2回、指標分母・条件別CSVを確認した。隔離SQLiteで新列追加を2回実行し、旧NULL・既存設定・問題本文とIDを保持して再seedできることも確認した。
- Backend全5分割は1761 passed・107 skipped・1 failed。失敗はtest_question_sets.pyの履歴復元確認が配列先頭の時刻順を前提にしていたもの。同ケースは独立実行で通過した。同ファイルの事前回答・学習回答の検査を記録内容・種別で特定する形へ変更し、時刻順への依存を除いた。履歴生成コードや保存時刻は変更していない。最終の同ファイル全41件と新機能9件は50 passed。修正後の全5分割再実行は行っていない。
- Frontend全7スクリプトとproduction build（TypeScriptを含む）が通過。1/2設問の用語ページ分割、保存待ち回答の再読み込み復元、重複・別ページ回答の拒否を確認した。
- 隔離ブラウザで管理スイッチをON/OFFし、ONで登録した参加者がOFFへの変更後も3問、OFF登録者は6問であることを確認した。PC 1440px・スマホ390pxで設問1だけの表示、横はみ出しがないこと、3用語の回答・答え合わせ・学習確認を確認し、画面例を目視した。
- Mockと実AI（Codex app-server、gpt-6-luna/low）の両方でブラウザ経路が通過した。実AIの教材生成成功ログと、保存した設問1による学習確認を確認した。通常の研究DB・ポート3000は使わず、今回作成した隔離DBと合成参加者だけを使用した。
- git diff --checkが通過。研究条件の妥当性、3問/6問の難易度同等性、実験開始承認は本検証とは別に扱う。


## 2026-11-03 PR #261：mainの選択肢修正に対する期待値整合

- PR #261のCI run 41598659750ではBackend tests (2/5)で2件が失敗した。原因はmainのPR #260の文面修正後も、v5本文をv4期待値と比較していたこと。アンケート処理の失敗ではない。
- PR #260のコミット507ea4ace68ac38ad71c64d1d823d1ded51b1ab8から、実際の56本文（A=3・B=27・D=26）の変更だけを期待値fixtureへ記録した。v4原型・初期追加案・56本文からv5全27問を再構成し、問題本文・選択肢・ラベル・役割の完全一致と設問3の非出題を検査する。seed後と再seed後のactive本文は最新v5期待値で照合し、v1〜v4復元・保存snapshot保全を維持する。
- 修正前のCI失敗2件を隔離DBで再現し、修正後はtest_pretest_content_revision.pyの5件が通過した。
- 文面期待値の修正後、Backend tests (2/5)は370 passed・1 failed。追加失敗はtest_initial_perfect_confirms_only_failed_final_item[M3-llm_knowledge-debug_fixed-B]で、誤答があるのにno failed split questions to confirmとなった。
- latest_failed_attemptsが回答時刻・UUID順で回次を選んでいたため、同時刻・時計逆転時に過去の回次を参照する。保存test_roundの順序を優先する修正を加えた。実SQLiteの6再現ケースは修正前すべて失敗、修正後はデータガード・本文/seed・実APIの失敗2経路と合わせて56 passed。回次の欠落・variant不整合は引き続き拒否する。
- 最終のBackend全5分割は1754 passed・107 skipped、失敗0件。Frontend全7テストスクリプトとproduction build（TypeScript検査を含む）も通過した。隔離DBで移行・再seed・保存値保全を含めて検証し、git diff --checkが通過した。実行コードの変更は学習確認元の回次選択のみで、問題YAML・採点基準・保存snapshot・DB列は変更しない。
- 研究DB・実AI・通常ポート3000は使用していない。コミット・push・GitHubへのコメント投稿は行っていない。

## 2026-11-03 アンケートの用語事前知識・自由記述任意化

- ユーザー指定の6用語を「知っていた／知らない」で必須回答とし、一般4・教材6項目の1〜10段階を維持する。AI自己評価は「使いこなせているか」とし、自由記述を任意にする。教材未表示者は教材6項目を従来どおり自動対象外とする。
- アンケート版はposttest-10point-v2。新規入力はprior_term_knowledgeとself_rated_ai_proficiencyへ保存し、v1のexperiences/self_rated_ai_knowledgeを上書き・変換しない。教材評定はv1/v2の保存値を読み出す。実験仕様版35・protocol・採点・6仮説の式・DB列は変更しない。
- 全表示項目の欠落拒否、全6語のfalse回答、評定範囲、コメントの省略/null/空欄/空白、旧フォーム拒否、旧アンケート保全、APIの保存・冪等性・統合CSVを確認する。

実施結果:

- アンケート関連のBackendテスト32件が通過。旧版の教材評定読み出しと保存値の不変、隔離DBの追加移行/seed保全を含む。
- Backend全体の5分割実行は1747 passed・107 skipped・1 failed。失敗はtest_llm_confirmation_retest_revision.pyのtest_natural_two_learning_rounds_feedback_history_and_retests[J-unknown-GHI-randomized-B]で、split_api_support.py:126の確認問題snapshot一致検査だった。アンケート処理を呼ばないケースであり、同ケースを独立DBで再実行すると通過し、アンケート関連32件と合わせて33 passed。全体実行時との差が生じた原因は未確定として残す。
- Frontendの全7テストスクリプトとproduction build（TypeScript検査を含む）が通過。
- frontend/tests/survey-browser.mjsで、隔離Mock DB・production buildの実画面を1440px/390px×教材表示あり/なしの4条件で確認した。未選択を送信できず、コメント空欄のまま終了へ進み、知識6項目のtrue/falseと評定が管理ログに保存される。横はみ出しがなく、記憶プロセスの長い説明も画面内に収まる。テストはSURVEY_VERIFY_ISOLATED=1、SURVEY_UI_BASE_URL、SURVEY_PLAYWRIGHT_MODULEを明示して使う。
- 研究DB・通常ポート3000・実AIは使用せず、使い捨ての隔離DBとMockで検証した。質問文・主観評価の研究上の妥当性や実験開始承認を意味しない。

## 2026-11-03 通常版テストへのM1・M3選択肢追加（仕様版35・fix/issue-255）

- 新規通常版参加者は仕様版35 / `experiment-plan-2026-11-03-split-added-choices-v1`・`split-actions-v5`で開始し、仕様版34以下の参加者・問題・回答・snapshotは閲覧専用で保全する。版27〜31=v1、32=v2、33=v3、34=v4の復元対応を維持する。
- 全27問のv4既存本文を保ち、追加したM1/M3本文をfixtureと照合する。6択の役割・デバッグラベル・unknown F固定、設問3の非出題、6設問の採点、既存のM3/unknown優先を確認する。
- 両群・両配置で回答・採点・学習確認snapshotを検証し、設問1・2だけが出題対象であること、確認問題が出題時の本文・選択肢を復元することを確認する。seed再実行後もv1〜v4の問題ID・本文・選択肢・回答snapshotを変更しない。
- Backend全テスト、Frontendテスト・build、デスクトップ・モバイルの画面確認、`git diff --check`を実施する。隔離DBを使用し、研究DB・localhost:3000・実AIは使用しない。分類理由は作問仮説であり、教育的妥当性・難易度同等性・学習効果を自動検査で実証しない。

実施結果:

- Backend全テストは1735 passed、107 skipped、失敗なし。既存DeprecationWarning 2件。
- Frontend `npm test`の全7スクリプトと`npm run build`（TypeScriptを含む）が成功。
- 隔離Mock DB・ブラウザでPC幅1440px/スマートフォン幅390px、両群、debug_fixed/randomizedの全8組合せを確認。事前・再テストの用語ごと2設問表示、再読み込み後の未完了ページ再開、回答後レビューの6択、3用語の学習確認を検証した。
- `git diff --check`通過。研究DB・localhost:3000・実AIは未使用。コミット・pushはしていない。分類妥当性・難易度同等性・学習効果は自動検査で実証していない。

## 2026-11-01 通常版テスト選択肢の文構造整形（仕様版34・fix/issue-247）

- 新規参加者を仕様版34 / `experiment-plan-2026-11-01-split-choice-wording-v1`・`split-actions-v4`で開始し、仕様版33以下は閲覧専用として旧問題・回答・snapshotを保全する。
- 比較表のPRETEST・RETEST1/2、3用語×設問1〜3の正解/M1/M3選択肢、計81本文が期待値fixtureと一致し、「わからない」・問題場面・設問・選択肢構造・役割・ラベル・順序・正誤分類は維持する。設問3はデータのみ保持し出題・採点しない。
- 仕様版27〜31はv1、32はv2、33はv3、34はv4で結果を復元する。内部final_testはRETEST1を使い、誤答PRETEST設問の学習確認では回答時snapshotを再利用する。再seed後も旧問題・回答・snapshotを変更しない。
- 関連Backendテスト、Frontendテスト・build、`git diff --check`を実施する。隔離DBのみを使用し、研究DB・localhost:3000・実AIは使わない。自動検査は文面の教育的妥当性・難易度同等性・学習効果を実証しない。

実施結果:

- 仕様版34の現行値、v1〜v4の版対応、期待値fixtureとv4 YAMLの全81本文・構造差分、設問3の非出題、仕様版32/33/34の隔離SQLite復元・snapshot保全を含む関連Backendテスト11ファイルが480 passed。失敗なし。既存DeprecationWarning 2件。
- Frontend `npm test`の全7スクリプトが成功し、`npm run build`はTypeScriptを含め成功。表示コードの変更がないためブラウザ確認は未実施。
- `git diff --check`通過。研究DB・localhost:3000・実AIは未使用。コミット・pushはしていない。文章の妥当性・難易度同等性・学習効果は自動検査で実証していない。

## 2026-11-01 通常版PRETEST選択肢文面改訂（仕様版33・fix/pretest）

- 新規参加者を仕様版33 / `experiment-plan-2026-11-01-pretest-content-revision-v2`で開始し、仕様版32以下は閲覧専用として既存問題・回答・snapshotを保全する。
- `split-actions-v3`は、前回改訂の記憶プロセスPRETEST設問1 M1（B）・設問2 M1（B）とM3（C）に加え、LLM設問1・2正解A、マルチエージェント設問1正解A、記憶プロセス設問1 M3（C）・設問2正解Aの本文を更新する。マルチエージェント設問2正解Aは指定文面のまま維持する。statusを`active_standard_split_v3`とし、正誤分類、ラベル、順序、場面、問題形式、RETEST1/2・内部final_testは維持する。
- 仕様版27〜31はv1、32はv2で結果を復元し、33はv3を使う。誤答PRETEST設問の学習確認は回答時snapshotを使う。DB構造・API・採点は変更しない。
- Backend全テスト、Frontendテスト/build、隔離DBで版・seed・回答snapshot・再seed保全を検証し、`git diff --check`を実施する。研究DB、localhost:3000、実AIは使わない。機械検査は選択肢の妥当性や学習効果を実証しない。

初回の実施結果: Backend全テスト 1730 passed / 107 skipped（警告2件）。この全件実行はレビュー指摘反映前の状態で実施した。今回のレビュー対応後は、下記の再検証結果を追記する。参加者画面の表示コードは変更していないため、ブラウザ確認は対象外。研究DB・localhost:3000・実AIは未使用。

レビュー対応後の再検証: PRETESTバンク差分・status・v1/v2保全・仕様版32/33のseed・snapshot復元を含む関連Backendテスト9ファイルで205 passed。Frontendは変更していないため再実行していない。`git diff --check`成功。

## 2026-11-01 通常版PRETEST文面改訂（仕様版32・fix/pretest）

- 新規参加者を仕様版32 / `experiment-plan-2026-11-01-pretest-content-revision-v1`で開始し、仕様版31以下は閲覧専用として旧問題・回答・snapshotを保全する。
- `split-actions-v2`が`split-actions-v1`を基に指定されたPRETEST文面だけを更新し、正誤・選択肢分類・表示順・6設問の採点を維持することを検証する。RETEST1/2の問題・選択肢は旧バンクと一致させる。
- 誤答したPRETEST設問の学習確認には回答時の保存snapshotが使われ、旧参加者の結果は旧バンクで復元されることを隔離DBで確認する。再seed後も旧データとsnapshotが変わらないことを確認する。
- 関連Backendテスト、Frontendテスト・build、`git diff --check`を実施する。研究DB、localhost:3000、実AIは使用しない。自動検査は文章の妥当性や難易度同等性、学習効果を証明するものではない。

実施結果:

- Backend全1,729件が通過、107件skip、失敗・errorは0件。PRETEST改訂を含む重点テスト88件も通過した。新旧YAMLを比較し、指定箇所以外の問題内容、選択肢分類・順序・正答、RETEST1/2の一致を確認した。隔離SQLiteで仕様版32のv2 seedと仕様版31のv1復元を確認し、既存回答・問題snapshotの保全を検証した。
- Frontendの`npm test`は全項目合格。`npm run build`もTypeScript検査を含め成功した。画面実装は変更していないため、参加者画面のブラウザ確認は行っていない。
- `git diff --check`通過。検証に研究DB・localhost:3000・実AI・既存参加者環境は使用せず、コミット・pushも行っていない。文章の妥当性、分類の研究的妥当性、難易度同等性、学習効果は自動検査で実証していない。

## 2026-10-31 辞書定義更新と言い換え指示（仕様版31・issue-230）

- 新規参加者を仕様版31 / `experiment-plan-2026-10-31-glossary-definition-paraphrase-v1`で登録し、仕様版30以下は既存記録・教材・snapshotを保全して閲覧専用とする。DB列とAPI返却形式は変更しない。
- learning_glossary_v2.ymlが変更されていないこと、v3が16語を維持し、指定4語だけ定義を更新してその他の定義・別表記・出典・除外規則を引き継ぐことを検証する。
- 教材内解説の生成入力は両群共通の辞書参照を保ち、定義文を逐語転記せず文脈に合わせて言い換え、意味を保ち、未登録の性質を追加しない指示を含むことを確認する。提案群固有の診断情報が統制群へ混入しないことを確認する。
- 既存v2 snapshotは保存済み定義で返り、新規v3注釈は更新後定義で生成されることを確認する。教材本文の文字数契約、注釈欄のみの初期値、教材解説モードの登録時固定は維持する。
- Backend/Frontend関連テスト、Frontend build、`git diff --check`を実施する。実AIによる説明の自然さ・意味的正確さ、初心者の理解や学習効果はこの機械検査で実証しない。

実施結果:

- `learning_glossary_v2.yml`はgit diff上で無変更。辞書テストでv1→v2の履歴内容とv2→v3の差分を比較し、16語・他項目・別表記・出典・除外語の維持と、指定4定義だけの更新を確認した。保存済みv2 snapshotをv3へ置き換えず返すテストと、v3による新規テスト注釈を確認した。
- 教材生成promptのテストで、両群共通の辞書参照、逐語転載を避ける文脈に沿った言い換え、意味保持・未登録の性質を加えない指示、モード別文字数条件を確認した。
- 用語辞書・教材生成・test glossary・shared interaction history関連のBackendテストは87 passed / 100 skipped。仕様版、閲覧専用、split出題、履歴保護の関連Backendテストは254 passed。失敗はなく、既存の非推奨警告が発生した。
- Frontend `npm test`とNext.js production build（TypeScript検査を含む）が通過。`git diff --check`も通過した。画面表示ロジックに変更がないため、実アプリのブラウザ確認は行っていない。
- 隔離テストDBとMockを使用し、研究DB・localhost:3000・実AI・コミット・pushは使用していない。文面の意味的正確さや学習効果は実証していない。

## 2026-10-31 教材内解説モードの文字数拡張（issue-237）

- 教材内解説は目標1000・600〜1200文字、注釈欄のみは目標700・600〜800文字とし、prompt、生成後検証、範囲外再生成、Mock生成、監査指標を同じモード別契約へ合わせる。
- 境界テストで各モードの下限・上限を含む範囲内判定と、範囲外の再生成指示を確認する。教材内解説1201文字の再生成試行で目標・上下限が引き継がれることを確認する。
- 仕様版30の新規登録と仕様版29以下の閲覧専用化を隔離テストで確認する。DB列・公開API・保存済み教材は変更しない。
- Backend全体テストは実装コードの状態で1,720 passed・107 skipped。`test_material_length_contract.py`と`test_current_experiment_spec.py`は77 passed、実際の参加者snapshot・教材保存・AI監査ログを確認する`test_learning_glossary.py`は26 passed（各実行2 warnings）。易しい版の過去フローを対象とする既存テストは停止方針によりskipされる。
- 検証はBackendのテスト用DBで実施した。DB列・公開API・保存済み教材は変更していない。実AIの意味的正確性や学習効果はこの機械検査で実証しない。

## 2026-10-31 テスト遷移ボタンの表示統一（issue-232）

- 通常版テストの用語別ページ操作を学習画面と同じ`.corner-primary`へ統一し、右下固定パネル、ボタンサイズ、狭い画面の安全領域対応を共通化する。ラベル・無効化条件・回答送信と遷移処理は変更しない。
- Frontendの`npm test`とproduction build（TypeScript検査を含む）が通過した。smoke testは用語別ページ操作が共通スタイルを使い、旧専用クラスが残っていないことを確認する。
- Chrome headlessで実際の`globals.css`を使う隔離fixtureを確認した。1440・768・390・320pxの各幅で白い固定パネル、18px文字、56px最小高、スクロール中の位置維持、画面内への収まり、横はみ出しなしを確認した。
- 実アプリのMock APIブラウザーフローはPlaywright依存がこの環境にないため未実行。`split-assessment-browser.mjs`には実画面の固定スタイル・スクロール位置の確認を追加し、`node --check`で構文を検証する。API・回答・遷移コードは変更していない。
- `git -c core.whitespace=cr-at-eol diff --check`通過。ブラウザfixtureは隔離Chromeで実行し、研究DB・localhost:3000・実AI・コミット・pushは使用していない。

## 仕様版29 教材の用語解説モード（実施済み）

- 管理APIは認証を要求し、初期値・厳密なmode値・保存後の再取得を確認する。管理画面は取得/保存中に操作を無効化し、失敗時は最後に保存済みの選択を保つ。
- 新規参加者の登録時にmodeを固定し、後から管理設定を変えても既存参加者へ遡及しない。既存NULLはNULLのまま保持し、実行時だけ注釈欄モードとして扱う。参加者一覧・個別ログ・participants CSVで値を確認する。
- annotation_onlyでは辞書参照をAI入力へ渡さず、現行の教材用注釈欄を表示する。integrated_materialでは同じ辞書情報を両群へ渡し、教材本文で使う登録語を説明する指示を含め、教材用注釈欄のみ隠す。
- proposed専用の診断・taxonomyはcontrolへ渡さず、回答後解説・テスト注釈・snapshotは両modeで維持する。教材本文の600〜800文字検証を維持する。
- 旧版参加者の教材本文・snapshot・評価が更新されず、仕様版28以下を閲覧専用とする。隔離DBのschema補修を複数回実行し、旧行を補完しない。
- Backend対象テスト、Frontendテスト・production build、隔離ブラウザの両mode表示、`git diff --check`を実施する。研究DB・localhost:3000・実AIは使用しない。

実施結果:

- Backend全1,705件が通過、107件skip、失敗・errorは0件。うち教材用語モードの重点テストを含む。初期値、厳密なmode値、管理認証、schema補修後の旧NULL保全、設定永続化、新規登録時snapshot、設定変更の非遡及、両群共通の辞書参照とproposed専用診断情報の分離を確認した。
- Frontendの`npm test`は全項目合格。隔離コピーで`next build --webpack`を実行し、production build・TypeScript検査・静的ページ生成に合格した。標準Turbopack buildは隔離コピーの外部`node_modules` symlinkを拒否したため、Webpack buildで検証した。
- Chromeブラウザ検証は両群×両mode×1440px/390pxの8条件で成功した。注釈欄のみではPCの教材欄、スマートフォンの開閉パネルに辞書項目が表示され、教材内解説では教材用注釈欄とボタンが表示されない。両modeで回答後解説の注釈を維持し、横方向のはみ出しがないことを確認した。
- 合成参加者の登録後に管理modeを反転しても、個別ログに登録時modeが保存され続けることを全条件で確認した。初期設定は注釈欄のみ。ブラウザ検証用スクリプトは`frontend/tests/learning-material-glossary-mode-browser.mjs`。
- 検証には隔離SQLite `/tmp/gogainen-issue227-run.7cDVJH/app.db`、Mock backend 8117番、隔離frontend 3117番を使用した。画面・操作と出力契約の検証であり、AIが作る個々の用語説明の意味的正確さや学習効果を実証するものではない。研究DB・3000番・実AI・コミット・pushは使用していない。

## 2026-11-06 旧問題モードのコード・資産削除

- 通常版固定の登録・出題・学習・集計から版分岐、管理UI、版設定API、専用問題資産を除去する。旧モードを指定した集計要求は422で拒否し、旧切替APIは公開しない。
- 研究DBの削除は起動・seedから分離する。dry-runを既定とし、研究環境・PostgreSQL・明示した識別対応表・停止済みアプリ・対象DB名の再確認がそろわない実行は拒否する。参加者識別情報を実行ログと監査要約へ出さない。
- 隔離データで削除対象の関連記録・問題と通常版記録の非変更、中断後の再試行、対応表の別処理、匿名件数要約、旧列削除を確認する。
- ローカル `.local` 内の記録は参加者識別子に結び付くファイルだけを対象とし、他の参加者記録を保つ。既定SQLiteや開発環境からの削除は拒否する。
- 実研究DBに接続した削除は実施していない。研究者がアプリ停止、機関バックアップ、対象DB・対応表の確認を行い、明示的に専用スクリプトを起動するまで研究記録は変更しない。

## 仕様版28の受入条件（当時の検証待ち・履歴）

答え合わせ機能はコードに実装済みだが、仕様版28の以下の受入条件は当時実行確認していない。仕様版28以下は現在閲覧専用である。既存の仕様版27までの検証記録とは区別する。

- 設問1だけ保存された時点ではペア結果を返さず、同じ用語の設問1・2が両方保存された場合だけ未確認結果を表示する。確認は設問がある同じ用語ページ内で行い、画面/URL遷移しない。選択済みの選択肢だけを正解なら緑、不正解なら赤にし、未選択選択肢に正誤を表示しない。
- 答え合わせON/OFFと既存PRETEST全体結果表示ON/OFFの全組合せを検証する。ペア結果の後に全体結果を表示する条件、全体結果を省略する条件、ペア結果を出さない条件をそれぞれ確認する。
- 通常版PRETEST・RETEST・内部final_testと仕様版27以下を検証し、適用範囲を守る。易しい版については現在の稼働経路ではなく、停止・閲覧専用・ログ保全を検証する。
- 未確認ペア表示中の再読み込みで保存値から復元し、確認済みペアは再表示しない。確認APIの再送は冪等で、不完全ペアの確認要求は拒否する。
- 全6設問の完了後にだけ既存のバッチ採点・診断・状態遷移が行われる。学習遷移・回数上限・評価式が変わらない。
- 答え合わせ用応答に正答キー・正答選択肢・解説・分類・群・方略が含まれず、本人の選択ラベル/本文と正誤だけが含まれる。
- 管理APIで厳密なbooleanを検証し、設定値は通常版の新規登録だけsnapshotされる。旧行を補完せず、易しい版は対象外とする。

## 2026-10-30 Backend CIの5 shard化（issue-222）

- GitHub ActionsのBackendテストをファイル単位の3ジョブから5ジョブへ拡張した。決定的な件数均等化、独立runner上のDB、全shard成功を要求する集約jobは維持し、同一runner内のpytest並列化は行わない。
- shard専用Backendテスト4件が通過した。隔離一時DBで全1,892件を収集して5分割し、各shardは379・378・377・379・379件で非空、テストIDの重複・欠落はなかった。ここでは全テストの実行時間は測定していない。
- `git diff --check`通過。実行時間の短縮幅は、PR上で新しいGitHub Actionsの結果を取得後、直近の約5分の実行と比較して評価する。コミット・push・手動workflow_dispatchは行っていない。

## 2026-10-30 ギブアップ操作をヘッダーへ移動（issue-224）

- 再テスト・内部final_test、学習セッション、再テスト結果確認のギブアップ操作を、管理画面リンクの左隣にあるヘッダー操作エリアへ移した。通常フローのためスクロールに追従せず、ヘッダーとともに画面外へ移動する。表示条件、確認、送信中無効化、エラー時の再試行、遷移先は維持し、本文のsticky行は除去した。
- Frontendのnpm testとNext.js production build（TypeScript検査を含む）が通過した。隔離MockのPlaywrightで事前テスト・結果確認・学習・再テスト1・その結果確認・再テスト2・管理画面を1920、1440、1100、1099、768、760、390、320pxで確認し、内部final_testを1440/390pxで確認した。ギブアップの表示条件、管理画面リンクの左隣配置、通常スクロール、欄外・注釈・右下操作との非重複、キーボードフォーカス、横はみ出しなしを検証した。
- 390pxでは確認ダイアログのキャンセル、送信中の無効化、長文エラーの折り返し、失敗後の再有効化と再試行を確認した。注釈欄の表示・開閉と長い欄の内部スクロールも回帰確認し、PCとスマートフォンのスクリーンショットを目視した。
- CRLF形式のsmokeテストに合わせて`git -c core.whitespace=cr-at-eol diff --check`通過。隔離SQLite・合成参加者・Mock API 8041番/Frontend 3041番を使用し、研究DB・3000番環境・実AI・既存参加者記録は対象外。コミット・pushは行っていない。

## 2026-10-30 画面遷移ボタンの拡大（issue-212）

- 画面下部に固定する主要操作ボタンを文字18px・最小高56pxへ拡大し、長いラベルは狭い画面で折り返す。適用は`.corner-primary`内に限定し、他のボタン、パネル位置、操作処理は変更しない。
- Frontendのnpm testとNext.js production buildが成功。隔離Chromeで実際の共通CSSと固定操作コンテナを用い、1440・768・390・320pxを確認した。ボタンは全幅で18px・高さ56px以上、長いラベルは狭い幅で折り返し、画面外へのはみ出しと横スクロールはなかった。
- `git diff --check`通過。ブラウザ確認はCSS検証用の合成画面で実施し、研究DB・localhost:3000・実AIは使用していない。

## 2026-10-30 学習確認問題の全誤答表示（issue-211）

- 学習セッションの単一選択式・複数選択式確認問題で、回答前は正誤色を出さず、回答後は全正解を緑、未選択を含む全誤答を赤で表示する。正誤ラベル、選択状態、採点・APIは変更しない。事前・再テストの結果表示は対象外。
- Frontendテスト5件とNext.js production build（TypeScript検査を含む）が通過した。判定クラスの単体テストで回答前・正答・誤答・未定義判定を確認した。
- Playwrightの隔離Mockブラウザーで設問別確認を8条件（両群×両配置×1440px/390px）実行し、正答1択の緑、選択済み・未選択の誤答3択の赤、回答前に正誤色が出ないこと、横はみ出しなしを確認した。別の合成API応答テストでも複数選択式を1440px/390pxで実行し、選択済み・未選択の誤答すべてが、無効化状態でも赤く表示されることを確認した。
- `git diff --check`通過。ブラウザー検証は一時SQLite・Mock API 8046番/Frontend 3045番とPlaywrightの合成応答だけを使用し、研究DB・localhost:3000・実AI・既存参加者記録は対象外。

## 2026-10-30 学習確認問題の共通場面重複表示修正

- 通常版の複数設問確認問題で、同じ場面説明が各設問の本文に含まれるため画面上で繰り返される表示を修正する。本文の先頭にある共通場面が一致し、「設問1：」「設問2：」境界を特定できる場合だけ、表示時に共通場面を一度表示し、各設問の見出し・問い・選択肢はそのまま残す。単問・不一致・境界不明は保存本文をそのまま表示する。
- API、保存本文、snapshot、問題・選択肢、選択・採点・回答後フィードバック、テスト画面、結果画面、易しい版は変更しない。進行中の参加者にも表示だけ適用する。
- Frontendテストは全件通過した。新しい純粋関数テストで、2段落の共通場面、単問、場面不一致、境界欠落・不正な設問番号、入力不変を確認した。隔離コピー上のNext.js本番buildもTypeScript検査を含め通過した。
- 隔離SQLiteのMock環境でブラウザを8条件（両群×debug_fixed/randomized×1440px/390px）実行し、3用語すべてで場面1回・設問本文2件・各4択、選択の独立性、全問回答後の送信と結果表示、再テストへの遷移を確認した。desktop/mobileの画面を目視し、横はみ出しはなかった。
- `git diff --check`通過。研究DB・localhost:3000・実AI・保存済み本文は使用・変更していない。

## 2026-10-30 ギブアップ操作の固定行化（issue-209）

- 再テスト・内部final_test、学習、再テスト結果確認のギブアップ操作を画面右上固定から本文先頭の追従行へ移した。学習では教材・確認問題の列にまたがり、注釈欄とは分離する。管理画面リンク・処理条件・遷移は維持する。
- Frontendのnpm testとNext.js production buildが成功。隔離Mock環境で事前テスト・結果確認・学習・再テスト1・その結果確認・再テスト2・管理画面を1920、1440、1100、1099、768、760、390、320pxで確認し、内部final_testは1440/390pxで確認した。スクロール追従、管理リンク・注釈欄・右下操作との非重複、キーボードフォーカス、横はみ出しなしを検証した。
- モバイル結果画面ではギブアップのキャンセル、送信中の無効化、長い失敗メッセージ、再有効化と再試行を確認。注釈ブラウザ検査は6幅で再実行し、長い注釈欄の内部スクロールも1440/390pxで維持されることを確認した。スクリーンショットを保存しdesktop/mobileを目視した。
- `git diff --check`通過。画面は隔離SQLite・合成参加者・Mock API 8041番/Frontend 3041番だけを使用し、研究DB・3000番環境・実AI・既存参加者記録は対象外。

## 2026-10-29 PR #205のレビュー対応

- 非表示経路でも診断時に学習対象一覧を保存し、旧診断再送応答に一覧がない場合はAPI取得する。同じ参加者の途中再開では保存済みの全体一覧を保持し、別参加者・破損キャッシュは引き継がない。
- 学習待ちなのに対象が空の場合は503（learning_navigation_unavailable）で停止する。Frontendも自己参照・欠落・不正な遷移先では移動しない。対象抽出とskip_reviewの条件は既存仕様を維持する。
- 両群・両配置で3用語を順次学習して再テストへ進む4ケースと、不整合時の停止を追加した。重点73件、Frontendのキャッシュ保存順・保持/置換・遷移先検査と既存テスト、本番buildが通過した。今回は新たなブラウザ画面確認は行っていない。PRタイトルを「事前テスト後」に訂正した。研究DB・3000番環境・実AI・コミット・pushは対象外。
- Python 3.12.15のBackend全1,881件が通過（405.19秒）。既存の非推奨警告2件のみ。git diff --checkも通過した。

## 2026-10-29 事前結果表示設定（issue-204）

- 初期値は表示あり。DB設定を新規登録時に固定し、非表示では事前結果画面を飛ばす。既存NULLは表示ありとして扱い、補完しない。再テスト・内部final_testの結果表示と仕様版28の採点は維持する。
- Python 3.12の既存全1,859件と追加18件が通過した。両問題版・両群・配置・満点/未達、設定の非遡及、再送、結果非公開、追加テスト結果表示、認証・厳密boolean、繰り返し列追加・再起動時の旧行保全を確認した。既存の非推奨警告のみ。Frontendテスト・コピー上の本番build、git diff --checkも通過した。
- 別ポート3124/8124の隔離Mock・合成データで1440px/390pxの管理トグルと、事前回答後および直接URLから結果画面を飛ばす動作を確認した。研究DB・3000番環境・実AI・コミット・pushは使用していない。

## 2026-10-31 結果表示設定の再テスト適用（issue-233）

- 管理設定は事前テスト・再テスト1/2・内部final_testへ適用する。新規参加者の`show_pretest_results`と`show_retest_results`は登録時に同値で固定し、既存参加者の再テスト用NULLは表示ありとして保持する。
- 採点応答の`review_required`、冪等再送、結果画面直接取得・再開時の遷移、非表示時の結果配列非公開を両群・両配置・再テスト1/2・final_testで確認する。採点・保存済み正誤は変更しない。
- `backend/.venv/bin/pytest -q tests/test_pretest_display.py`: 23 passed。Backend全体: 1,714 passed、107 skipped。Frontend `npm test`と`npm run build`も通過した。
- 隔離テストで両群・両配置の再テスト1/2、final_testについて表示ON/OFF、登録時設定の固定、既存NULLの表示維持、結果配列の非公開、現在位置と冪等再送を確認した。DB列追加の再実行とNULL保持も確認した。
- ブラウザでの手動画面確認は未実施。smokeテストとAPI/画面遷移テストで確認し、研究DB・localhost:3000・実AI・コミット・pushは使用していない。
- `frontend/next-env.d.ts`はproduction buildが生成した参照先変更を戻し、CRLFのsmokeテストを考慮して`git -c core.whitespace=cr-at-eol diff --check`で差分の空白を検査する。

## 2026-10-29 PR #203の回次・Mock入力検証

- 通常版の学習対象抽出で、採点済み回答のtest_roundを参照先の設問版と照合する。欠落・空値・不一致は503（split_test_round_unavailable）で停止する。問題ごとのattempt_indexから回次を推測せず、再テスト1・2の誤答を混在させない。起動時の回次補修も易しい版だけに限定し、通常版の欠落値は書き換えない。[保存・学習範囲の扱い](39_split_assessment.md)。
- Mockのlearning_scope付きM1/M3入力は、pretest_targetsの型と各claim_id・observed_claimを本文生成前に検査し、不正な項目を黙って除外しない。正常な複数誤答・M3優先、統制群・unknownの診断対象を使わない動作、文字数・教授契約を維持する。
- 新規71件と既存の保存情報・履歴テストを合わせた133件が通過した。回次欠落・不一致、両群でのAI非呼び出し・記録不変・同じキーでの再試行、起動時の非書換えと易しい版の補修、Mock入力の破損と正常契約を検証した。Frontendのnpm testとコピー上の本番buildも通過し、元のFrontend・3000番環境の生成物は変更していない。
- Python 3.12.15 / requirements.txtでBackend全1,859件が通過した（377.74秒）。失敗・エラー・スキップは0件。既存のStarlette/NumPyの非推奨警告が2件ある。git diff --checkも通過した。検証は隔離SQLite・合成データ・Mockのみで、問題・採点・実験仕様版27・DB構造は変更しない。研究DB・実AI・コミット・pushは対象外とし、GitHubのCIはpush後に別途確認する。

## 2026-10-29 PR #203のBackend CI対応

- 通常版の既存APIテストを6設問・4択・誤答設問の確認出題へ移行した。過去の改訂本文・旧バンク・履歴復元の検証を維持し、現行フローの共通ヘルパーで群・配置・M1/M3/unknown・冪等性・表示snapshotを検証する。3問・10択の回帰テストは保持する易しい版へ明示的に限定した。[現行契約](39_split_assessment.md)。
- 通常版の不完全な6設問の採点拒否、設問単位の指標fixture、仕様版26の閲覧専用、事前満点後に不正解だったfinal_testの1設問だけを初回確認へ再出題する24条件を追加・更新した。先行生成は通常版・易しい版の両方を検証する。旧版の復元テストは必要な旧問題を明示的に用意し、新規DBに旧バンクがあることを仮定しない。
- 実装側では、不正キーに対する選択肢配置解析の例外、用語欠落を回答不足より先に検出する採点前503、Mock教材の同じ説明の重複による文字数超過を修正した。600〜800文字・本文証拠・採点規則・公開API構造・実験仕様版27・DB構造・問題本文は変更しない。
- Python 3.12.15 / requirements.txtでCIと同じ3分割実行を行い、597件・595件・596件の計1,788件が通過した。JUnitのテストIDを照合し、重複・失敗・エラー・スキップは0件だった。一括実行も全1,788件が通過した（473.18秒）。既存Starlette anyio別名とNumPy shapeの非推奨警告が2件ある。Frontendのnpm testと独立distDirでの本番build、git diff --checkも通過した。buildによる型設定ファイルの自動変更は元に戻した。
- 以下の失敗記録は当時の結果として保持する。今回の検証はローカルの隔離SQLite・合成データ・Mockのみであり、GitHubのCI成功確認にはpush後の実行が必要。研究DB・3000番環境の再起動・実AI・コミット・pushは対象外。

## 2026-10-29 PR #203の保存情報検証

- 確認回答前に保存済みsource_specと表示snapshotを検査し、欠落・破損時は503で停止する。現行バンクへフォールバックせず、AI呼び出し・採点・回答や学習状態の更新をしない。問題の参照先・variant_key・訂正情報案の不整合も明示的な503とする。[保存・指標の扱い](39_split_assessment.md)。
- 指標・結果・学習対象の問題取得は回答が参照するIDに限定して一括取得する。無関係な旧問題は解析せず、参照先が不正な回答を黙って除外しない。strategy_forは既にimport済みであり、未定義との指摘による追加変更は不要だった。
- 隔離SQLite/Mockで追加43件と既存39件の計82件が通過した。保存情報の欠落・破損、エラー時の記録保全・AI非呼び出し、対象に限定した取得とクエリ件数、通常の設問分割フローを検証した。既存NumPy shapeのDeprecationWarningが1件ある。Frontendのnpm testとgit diff --checkも通過した。問題・実験仕様版・DB構造・Frontendの変更はない。
- Backend全体の既存テスト移行は別途未完了であり、下記の全体テスト失敗が解消されたとは扱わない。研究DB・3000番環境・実AI・コミット・pushは対象外。

## 2026-10-29 仕様版27・設問分割の接続

- 通常版の6設問・4択、直前誤答に限定した用語別の教材と確認問題、unknown/M3優先、易しい版との分離を接続した。[仕様と未完了事項](39_split_assessment.md)。
- 追加テストは39件通過。両群・両配置・3用語、通常/事前満点経路、6問の分母、易しい版の形式保持、旧版の操作拒否を確認した。隔離Mock環境で1440px・390pxの画面から事前テスト、3用語の確認問題、再テストへの遷移を確認した。Frontendテスト・ビルドも通過した。
- Backend全体の実行では531件通過・1162件失敗。既存の版26、3問・10択や旧教材入力契約を前提としたテストの移行が未完了であり、追加テストの成功だけで受け入れ完了としない。研究DB・3000番環境・実AI・コミット・pushは対象外。

## 2026-10-29 注釈の表示位置

- テスト・教材の注釈を、1100px以上では右側の追従欄、それ未満では開閉パネルに変更した。回答後解説の位置と注釈データは変更しない。進行中の参加者にも表示変更が適用されるため、実験途中での適用は条件変更として記録する。
- 隔離Mock環境で事前・再テスト、教材・回答後解説を1920、1100、1099、768、390、320pxで確認した。固定ボタンとの非重複、パネルのキーボード操作・フォーカス復帰、長い注釈の欄内スクロールを確認した。通常版・易しい版、両群・両配置でテストの384表示と空注釈、教材の正誤・空注釈も確認した。研究DB・3000番環境・実AIは使用していない。

## 2026-10-28 ページ表示幅の拡張

- 共通ページと管理ロックボタン領域の最大幅を1080pxから1440pxへ変更した。狭い画面の左右16pxの余白、管理パスワードダイアログの最大420px、学習画面の760px以下の1列表示は維持する。問題・採点・API・実験条件は変更しない。
- frontendのnpm test・npm run build、git diff --checkを実施した。隔離Mock環境で事前テスト・結果確認・学習画面・再テスト・管理画面を1920、1440、768、760、390、320pxの6幅で確認し、共通幅、ロックボタンの位置、学習画面の列配置、横はみ出しを検証した。desktop/mobileのスクリーンショットも確認した。
- 確認には別ポートのfrontend 3040 / backend 8040と隔離された合成データを使用した。研究DB・3000番環境・実AIは使用せず、Backend全テストは今回実行していない。

## 2026-10-28 注釈変更と管理認証のマージ整合確認

- README・本書・出典資料の競合は、用語注釈v2と管理パスワード認証の記載を両方保持して統合した。現行の実験仕様版26・protocol・辞書と既存の管理認証処理は変更しない。過去の検証記録は採用時の内容として保持する。
- 注釈用の追加APIテストも既存のAuthenticatedTestClientを使い、ブラウザ検証は設定変更前に管理ログインを行う。認証を無効化せず、管理認証・教材/解説注釈・テスト注釈・V2問題の重点241件が通過した。既存NumPy shapeの非推奨警告が1件あり、失敗ではない。Frontendのnpm test・npm run build、ブラウザ検証スクリプトの構文確認も通過した。Backend全体・実ブラウザ・実AIの再実行は今回行っていない。
- 研究DB・3000番環境・既存参加者記録・モデル設定には触れず、マージコミットとpushは行わない。buildが生成したnext-env.d.tsの変更行だけを戻す。

## 2026-10-28 PR #189 管理認証のレビュー対応

- 管理画面ロック時は、logout通信を待たずに管理データを隠す。通信失敗・5秒のタイムアウト時はサーバー側の解除が未確認であることを表示し、解除の再試行成功までパスワード再入力を不可とする。離脱時も解除を再試行する。Cookie削除のSecure属性を発行時のHTTPS判定に合わせた。セッション切れの401は管理APIに加えseed・管理用評価再計算でもロックへ通知する。
- AI接続状態の取得失敗はログインエラーと分けて表示する。レビューの「setLoginErrorが未定義」という指摘は、既存stateの宣言があるため該当しなかった。
- 隔離SQLite/Mockで管理認証・対応表・配置の45件が成功。HTTP/HTTPSのCookie削除・失効、対象APIの401と認証外APIの挙動を確認した。frontendのnpm test・本番buildが成功し、実ブラウザでAI状態の500、logout応答待ち中の即時ロック、通信失敗時の警告、再試行後のサーバー側失効と既存の認証・CSV・画面遷移を確認した。
- 研究DB・3000番環境・実AI・既存参加者データには触れない。ローカルのセッション失効とサーバー側の解除成功は別であり、通信断で認証解除が確認できない場合は実験端末を渡す前に再試行する。実験開始条件の同意情報確定・実AI確認・選択肢配置などは別途残る。

## 2026-10-27 管理画面のパスワード認証

- ユーザー指定のabcをbackendで照合し、管理画面の入場時に伏せ字入力のポップアップを表示する。READMEへパスワードを記載し、ADMIN_PASSWORDをComposeと設定例へ追加した。認証前は管理画面の子コンポーネントをmountせず、管理データを取得しない。
- 全管理API・CSV・分離対応表・seed・管理用評価再計算を認証対象にした。HttpOnly/SameSite=Strict Cookieと30分の単一プロセス内セッション、HTTPS時のSecure、Origin照合、no-store、パスワード入力エラーの非反映を確認した。ロック・離脱・期限失効後の拒否、再入場・再読み込み時の再入力を検証した。既存APIテストは認証を無効化せず、実際にログインする共通TestClientへ変更した。
- 認証・対応表・配置の重点43件が成功。backend全体1573件も通過した（1455.34秒、既存のDeprecationWarningが2件）。全体検証用コピーの作成後に追加したlocalhost/127.0.0.1互換性は、最終版の認証12件の再実行で確認した。
- frontendのnpm test・npm run buildが成功。3036番frontend / 8036番backendの隔離Mockで、匿名・誤入力・正しいパスワード、キャンセル、管理リンク/直接URL、再読み込み、セッション失効、CSV取得、ロック、離脱時の認証解除を実ブラウザで確認した。1440×1000 / 390×844のポップアップ画像を目視し、横はみ出し・pageerrorがない。既存の問題版切替・版別集計・CSVリンクのブラウザテストも成功。設定取得完了前にボタン状態を判定していたテストの待機を修正した。
- 検証DB・対応表・出力は一時Docker領域だけを使用した。研究DB・3000番環境の更新/再起動、実AI呼び出し、既存データ削除、コミット・pushは行っていない。問題・採点・教授条件・実験仕様版25・protocol_id・DB構造は変更しない。配布環境の匿名アクセス拒否、同意等の他の開始前条件は別途確認する。以前の「管理認証未実装」は当時の検証記録であり、現行仕様は[15](15_security_privacy.md)を参照する。

## 2026-10-27 仕様版26・注釈対象の限定とテストへの追加

- 指定9語を現行辞書から除外し、残る16語の定義・出典を維持したlearning-glossary-v2を追加した。旧learning_glossary_v1.ymlと全問題バンク・AI実装は無変更。除外された複合語からプロンプト・エージェントだけを誤抽出せず、独立出現時は表示する。別表記・大小文字・装飾・出現順・重複排除・空一覧・不正辞書と除外語競合を検証した。[対象語・保存・測定上の注意](24_learning_glossary.md)。
- 新規だけ仕様版26 / experiment-plan-2026-10-27-test-glossary-v2を使用し、仕様版25以下は閲覧専用。テスト用nullable JSON列Attempt.glossary_snapshotを追加し、旧行へ補完しない。隔離SQLiteで不足列追加・起動/seed再実行・旧仕様版25の行不変と24 active問題を確認した。旧版25の結果復元はscenario-actions-v9を使い、保存済み辞書v1の注釈は除外し直さず保持する。配布先PostgreSQLの実行確認とは区別する。
- 事前・再・内部final_testの各問題は用語見出し・本文・全選択肢から抽出し、選択に関係なく補足する。出題GETは回答を作らず、回答時に保存し、回答済み再取得・冪等再送は保存値を返す。管理ログ/統合CSVのvalue_jsonに同じsnapshotを出し、固定ヘッダは維持する。参加者APIは公開用の辞書版・用語・説明だけを返し、正答・分類・指紋・出典を追加しない。AI入力・共通履歴にも注釈を混ぜない。
- Backend全1612件が通過した（591.28秒、既存NumPy shapeのDeprecationWarningが1件）。その後追加した旧v25の注釈・結果バンク保全の1件を含む重点48件も通過した。Frontendのnpm testとnpm run buildは成功。機械検査を初心者への理解しやすさ・効果の実証とは扱わない。
- 隔離Mockのbackend 8036 / frontend 3036で、テストのブラウザ32条件（幅1440/390×両問題版×両群×両配置×通常/事前満点経路、各事前・再テストを含む384問題表示）と空一覧1条件を確認した。選択肢の下の注釈・再読込/回答後再取得・3択/J単独・最大3テスト・未達終了・結果確認で注釈を出さないことを確認し、desktop/mobileのスクリーンショットを目視した。横はみ出し・選択肢との重なりはなかった。
- 教材と正誤解説もブラウザ16条件（幅1440/390×両問題版×両群×正誤）と空一覧1条件で確認した。確認問題自体への注釈は追加しない。確認用backend再起動の前後で未回答用語一覧と回答済みsnapshotが一致した。辞書全文16項目と仕様書の説明が一致し、ローカルリンクとgit diff --checkを確認した。追加3ファイルの空白検査も通過した。
- 確認環境は/var/folders/m1/_n59q3n56_35v0nf05l_5m9r0000gn/T/gogainen-glossary-v26-16vv92wnの合成データのみ。研究DB・3000番環境・Word・別仕様リポジトリ・モデル設定・実AI呼び出し・既存データ削除・コミット・pushは対象外。buildが生成したnext-env.d.tsの行だけを戻した。テスト時にも用語の意味を参照できる追加支援として、旧条件の得点と現行集計を混ぜない。

## 2026-10-27 仕様版25・確認問題と再テストV2の5問改訂

- 通常版LLM知識・記憶プロセスの確認V2と3用語の再テストV2、計5問・45選択肢を指定文どおり採用した。LLM再テストは大学・教職員版を選び、企業・従業員案は採用しない。マルチ確認V2、V1・内部final_test、残り7確認問題・6テスト問題、事前の訂正情報・易しい版は維持する。構造化比較で対象5問とバンク版以外が不変であることを確認し、旧v8は変更前HEADとバイト単位で一致する。他の既存コンテンツ23ファイルと、問題全文資料の対象外6問の節も不変。[原文・分類理由・例外と保存契約](38_round_two_revision.md)。
- 新規だけ実験仕様版25 / experiment-plan-2026-10-27-round2-revision-v1、通常版学習15・テストscenario-actions-v9を保存する。旧学習v14・旧テストv8と旧記録は保持し、易しい版は学習4のまま。旧v8のSHA-256はc07ac0de45d78abba642107842bc14d510ace7751a369d9a12a171fb0141c9ed、旧学習v14は72d37e3ae983758718020ddac5e95ee51fa4e3aade63e4b1936d54f2a8428d0d。
- 種類構成は通常版学習15のLLM・記憶だけapplication/application/comparisonとし、マルチ・旧版・易しい版はapplication/prediction/comparisonを維持する。同文再使用はLLM確認V1/V2のE・Gと、LLM再テストV1/V2のFだけに限定した。本文変更・別ラベル・別用語・別variant・3問目へのコピー、同一問題内・指定外・旧版・易しい版の重複、確認問題への固定テスト文の転載を拒否するテストが通過した。従来の全問間同文禁止を期待するテストも承認内容に合わせて限定更新した。
- backend全1563件が通過した（471.04秒）。今回追加の重点テスト153件も成功し、Starlette anyio別名とNumPy shapeの既存DeprecationWarningが2件ある。通常経路の初回学習V1→再テストV1未達→学習V2→再テストV2と、事前満点経路の変更しないfinal_test V1→未達後の初回学習V1→再テストV2を両群・両配置で検証した。完全正解・M1/M3・M3優先・J単独、正誤解説・再回答・同期/先行生成・冪等性・履歴・結果レビュー、早期満点と最大3テストを確認した。
- 隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧v8の本文・判定情報・旧仕様版24の参加者/進行/回答/教材/保存評価/snapshotが不変で、新旧Question/QuestionOption IDが分離されることを確認した。旧v8＋易しい版は新v9追加後36行・active 24行、新DBも24 active行。保存snapshot優先、不足時の旧学習14とテストv8からの復元、読み取りでのsnapshot不変を検証した。旧仕様版24の操作・再送・worker・削除・補修・再計算を拒否し、現行集計から除外する。旧仕様版24にはテストv8の履歴対応を追加した。
- frontendのnpm testとnpm run buildは成功。backend 8035 / frontend 3035の隔離Mockでブラウザ152条件を完了した。改訂した確認V2の2用語を各24条件（幅1440/390×両群×両配置×事前unknown/M1/M3）、3用語の再テストを各32条件（幅1440/390×両群×両配置×通常版/易しい版×通常/事前満点経路、各条件でV1/V2）、事前テストを8条件で確認した。
- ブラウザでは原文・10選択肢の一致、確認LLMの2段落・記憶の3段落、再テストLLMの5段落・マルチの4段落・記憶の2段落を確認した。太字・重複する問題ラベルなし、長文の折り返し・非重複・横はみ出しなし、J単独・3択、正誤表示・解説・再回答と結果レビューを確認し、対象5問のdesktop/mobileスクリーンショットを目視した。問題・選択肢には注釈や正答/分類情報を追加していない。
- 隔離DBの新規参加者は全員仕様版25で、通常版200件が学習15、易しい版104件が学習4を保存した。activeは通常版scenario-actions-v9と易しい版scenario-actions-easy-v1の24行。採点・遷移・配置の実装、AI教授プロンプト・生成契約・モデル設定・共通RAG・用語注釈・DB構造・公開APIの構造は変更していない。
- 確認環境は/tmp/gogainen-round2-v25-yf_59uhmの合成データのみ。検証後の3035番は通常版・デバッグ配置へ戻した。研究DB・3000番環境の更新/再起動、Word・別仕様リポジトリ・実AI呼び出し・既存データ削除・コミット・pushは行っていない。buildが生成したnext-env.d.tsの変更行だけを戻し、Markdownリンクとgit diff --checkを確認した。練習効果の可能性を記載し、分類妥当性・独立性・難易度同等性・初心者への読みやすさを機械検査やMockで実証したとは扱わない。

## 2026-10-27 仕様版24・再テストV1の5選択肢改訂

- 通常版multi_agent・retest_v1のE/F（M1）とmemory_process・retest_v1のE（M1）・H/I（M3）を指定文どおり採用した。「営業／時間」の途中改行だけをつなぎ、場面・設問・判定・段落表示は維持する。旧v7との構造化差分は5選択肢とassessment_bank_versionだけで、残り7テスト問題・指定外の選択肢・事前の訂正情報・全確認問題・易しい版は不変。[原文・分類理由・保存と検証条件](37_multi_memory_retest_one_revision.md)。
- 新規だけ仕様版24 / experiment-plan-2026-10-27-multi-memory-retest1-v1と通常版テストscenario-actions-v8を使用する。学習は通常版14・易しい版4のまま。旧v7アーカイブのSHA-256は315455197bc0b5833dea365845dff6e41c1b47a28db4ad0dcc033545a105cfe4で、変更前HEADとのバイト単位一致を確認した。他の既存コンテンツ22ファイルと、問題全文資料の変更対象外7問の節も不変。旧v6/v7と学習v14の全文fixtureは採用時の履歴検証として保持した。
- backend全テストは1401 passed（384.14秒）、重点テスト424件も通過した。Starlette anyio別名とNumPy shapeの既存DeprecationWarningが2件ある。両群・両配置で通常経路と事前満点経路のV1共用、完全正解、改訂E/Fを含むM1・H/Iを含むM3・M3優先、J単独、冪等な回答/採点再送、表示時ラベル・本文の保存、結果レビュー・履歴、早期満点・2回目未達終了・事前込み最大3テストを確認した。採点前のAPIは正答・分類情報を返さない。
- 隔離SQLiteでseedと起動時補修を2回ずつ実行し、新旧問題ID・選択肢IDの分離と旧v7の本文・判定情報の保全を検証した。旧仕様版23の参加者・回答・教材・保存済み評価・snapshotは不変。操作・再送・worker・削除・補修・再計算を拒否し、現行集計から除外する。保存snapshot優先と、不足時の旧問題ID・v7からの復元も確認した。旧v7＋易しい版のDBは新v8追加後36行・active 24行、新DBも両版計24 active行となる。旧仕様版23にはテストv7の履歴対応を追加した。
- frontendのnpm testとnpm run buildは成功。隔離Mockのbackend 8034 / frontend 3034でブラウザ104条件を完了した。3用語の再テストを各32条件（幅1440/390×両群×両配置×通常版/易しい版×通常/事前満点経路、各条件でV1/V2）と、事前テスト8条件で確認した。
- ブラウザでは改訂文と10選択肢の一致、マルチエージェントV1の4段落・記憶V1の2段落表示、長文の折り返し・非重複・横はみ出しなし、J単独・3択、表示時ラベルと結果レビュー、再テスト2への進行と回数上限を確認した。desktop/mobileの対象2問のスクリーンショットを目視した。問題・選択肢への注釈や正答・分類情報は追加せず、表示コードも変更していない。仕様書21・37の全文とYAMLが一致することを照合した。
- 隔離DBの新規参加者は全員仕様版24で、通常版104件が学習14、易しい版104件が学習4を保存した。activeなテストはscenario-actions-v8とscenario-actions-easy-v1の計24行。学習バンク・教授プロンプト・AI生成契約・モデル設定・採点・遷移・DB構造・公開APIは変更していない。
- 確認環境は/tmp/gogainen-retests-v8-uo3p72iuの合成データのみ。検証後の3034番は通常版・デバッグ配置へ戻した。研究DB・3000番環境の更新/再起動、Word・別仕様リポジトリ・実AI呼び出し・既存データ削除・コミット・pushは行っていない。buildが生成したnext-env.d.tsの変更行だけを戻し、Markdownリンクとgit diff --checkを確認した。機械検査・Mockを分類妥当性・初心者への読みやすさ・難易度同等性の実証とは扱わない。

## 2026-10-27 仕様版23・LLM知識の再テストV1改訂

- 通常版llm_knowledge・retest_v1の場面説明とA/B/D/G/H/Iを指定文どおり採用した。場面4項目と設問の5段落表示とし、内部final_testも改訂後のV1を共用する。旧v6との構造化差分は場面説明・6選択肢・assessment_bank_versionだけで、設問・C/E/F/J・残り8テスト問題・事前の訂正情報は不変。[原文・分類理由・保存と検証条件](36_llm_retest_one_revision.md)。
- 新規だけ仕様版23 / experiment-plan-2026-10-27-llm-retest1-v1と通常版テストscenario-actions-v7を使用する。学習は通常版14・易しい版4を維持し、新しい学習YAMLは追加しない。旧v6アーカイブのSHA-256と変更前HEADとのバイト単位一致、他の既存コンテンツファイル21件の不変を確認した。旧v5/v6と学習v14の全文fixtureは採用時の履歴検証として保持した。
- backend全テストは1241 passed、既存のStarlette anyio別名とNumPy shapeのDeprecationWarningが2件。重点テスト397件も通過した。両群・両配置で通常経路と事前満点経路を進め、改訂V1とfinal_testの共用、完全正解、Dを含むM1、G/H/Iを含むM3・M3優先、J単独、冪等な回答/採点再送、表示時ラベル・本文の保存、結果レビュー・回答履歴、早期満点・2回目未達終了・事前込み最大3テストを確認した。採点前のAPIは正答・分類を返さない。
- 隔離SQLiteでseedと起動時補修を2回ずつ実行し、新旧問題ID・選択肢IDの分離と、旧v6の本文・判定情報の保全を検証した。旧仕様版22の参加者・回答・教材・保存済み評価・snapshotは不変で、操作・再送・worker・削除・補修・再計算を拒否し、現行集計から除外する。保存snapshot優先と、不足時の旧問題ID・v6からの復元も確認した。旧v6＋易しい版のDBは新v7追加後36行、activeは24行となり、新DBも両版計24 active行である。旧仕様版22の結果復元用にはテストv6の履歴対応を追加した。
- frontendのnpm testとnpm run buildは成功。隔離Mockのbackend 8033 / frontend 3033でブラウザ104条件を完了した。3用語の再テストをそれぞれ32条件（幅1440/390×両群×両配置×通常版/易しい版×通常/事前満点経路、各条件でV1/V2）と、事前テスト8条件で確認した。
- ブラウザでは指定文と選択肢の一致、LLM再テストV1の5段落表示、太字なし、長文の折り返し・非重複・横はみ出しなし、J単独・3択、表示時ラベルの保存と結果レビュー、再テスト2への進行と回数上限を確認した。desktop/mobileのスクリーンショットを目視した。問題・選択肢に注釈や正答・分類情報を追加せず、表示コードも変更していない。仕様書2か所に改訂全文が一致し、問題全文資料の他8問の節が変更前と同一であることも確認した。
- 隔離DBの新規参加者は全員仕様版23で、通常版104件が学習14、易しい版104件が学習4を保存した。activeなテストバンクはscenario-actions-v7とscenario-actions-easy-v1である。学習バンク・教授プロンプト・AI生成契約・モデル設定・採点・遷移の実装は変更していない。
- 確認環境は/tmp/gogainen-llm-retest1-v7-dxqj06odの合成データのみで、検証後の3033番は通常版・デバッグ配置へ戻す。研究DB・3000番環境の更新/再起動、Word・別仕様リポジトリ・実AI呼び出し・既存データ削除・コミット・pushは行っていない。buildが生成したnext-env.d.tsの変更行だけを戻し、Markdownリンクとgit diff --checkを確認した。機械検査・Mockを分類妥当性・初心者への読みやすさ・難易度同等性の実証とは扱わない。

## 2026-10-27 仕様版22・初回確認問題4か所の改訂

- 通常版multi_agent・learning_round_v1のG（M3）とmemory_process・learning_round_v1の場面説明後半・F（M1）・H（M3）を指定文どおり採用した。新学習v14と旧v13の構造化差分はこの4か所とバンク版だけである。記憶V1の3段落表示、対象2問の指定外部分と残り7確認問題、全テスト・事前の訂正情報・易しい版・教授契約・注釈・モデル設定・回数上限は不変。[原文・分類理由・保存と検証条件](35_multi_memory_round_one_revision.md)。
- 新規だけ仕様版22 / experiment-plan-2026-10-27-multi-memory-round1-v1と通常版学習14（易しい版4）を保存する。旧v13のSHA-256と、従来のコンテンツファイル21件のHEADとのバイト単位一致を確認した。旧仕様版21の操作・再送・worker・削除・補修・再計算拒否、集計除外、記録保全、snapshot優先・当時の学習版からの復元、新版欠落時の非フォールバックを検証した。
- backend全テストは1167 passed、既存のStarlette anyio別名とNumPy shapeのDeprecationWarningが2件。重点テスト323件も通過した。両群・両配置・unknown/M1/M3開始の通常経路で、改訂文の出題、完全正解、Fを含むM1、GまたはF/Hを含むM3優先、J単独・混在拒否、回答後解説、同一問題での再回答・冪等性・同期/先行生成・保存履歴を確認した。
- 隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧仕様版21の参加者・教材・回答・snapshotとテストDB問題・選択肢の不変を確認した。旧仕様版21のテスト復元対応はscenario-actions-v6を追加し、現行22は現行版用定義を使う。別の隔離メモリDBでも、両問題版・3用語・事前/再1/再2/内部final_testの計24ケースで旧仕様版21の結果用問題復元を確認した。公開API・DB構造は変更していない。
- frontendのnpm testとnpm run buildは成功。隔離Mockのbackend 8032 / frontend 3032でブラウザ104条件を完了した。通常版マルチエージェントV1・記憶V1、易しい版記憶V1、変更対象外の通常版LLM確認V1を各24条件（幅1440/390×両群×両配置×事前unknown/M1/M3）と、事前テスト8条件で確認した。
- ブラウザでは原文一致、記憶V1の3段落、長文の折り返し・非重複・横はみ出しなし、J単独・3択、正誤解説・再回答・事前結果レビューを確認した。混合回答はマルチエージェントで改訂G、記憶で改訂F/Hを含め、M3優先を応答JSONでも照合した。desktop/mobileのスクリーンショットを目視した。問題APIの選択肢はoption_id/label/body/exclusiveのみで、正答・分類情報を追加していない。表示コードは変更していない。
- 隔離DBの新規参加者は全員仕様版22で、通常版152件が学習14、易しい版56件が学習4を保存した。通常版の3用語ともinteractiveが24ターン、same_session_prefetchが16ターンあり、全て保存学習版14と一致した。activeなテストDB問題は両版計24行のままである。
- 確認環境は/tmp/gogainen-multi-memory-v14-1t1pnql7の合成データだけを使用し、検証後の3032番は通常版・デバッグ配置へ戻す。研究DB・3000番環境の更新/再起動、Word・別仕様リポジトリ・実AI呼び出し・既存データ削除・コミット・pushは行っていない。buildが生成したnext-env.d.tsの変更行だけを戻し、Markdownリンクとgit diff --checkも確認した。機械検査・Mockを分類妥当性・初心者への読みやすさ・難易度同等性の実証とは扱わない。

## 2026-10-26 仕様版21・LLM確認問題V1のD/H改訂

- 通常版llm_knowledge・learning_round_v1のD（M1）とH（M3）の2文を指定文どおり採用した。学習v13は旧v12からこの2文とバンク版だけが異なり、場面・設問・2段落表示、残り8選択肢・8確認問題・全テスト・訂正情報・易しい版・教授契約・注釈・回数上限は不変。[本文・分類理由・保存と検証条件](34_llm_round_one_dh_revision.md)。
- 新規だけ仕様版21 / experiment-plan-2026-10-26-llm-round1-dh-v1と通常版学習13（易しい版4）を保存する。旧v12のSHA-256、旧仕様版20の操作・再送・worker・削除・補修・再計算拒否と集計除外、記録保全、snapshot優先・当時のバンクでのD/H復元、新版欠落・不整合時の非フォールバックを確認した。旧仕様版20のテスト復元対応はscenario-actions-v6を追加し、現行テストv6・DB問題IDは変更していない。
- backend全テストは993 passed。Starlette anyio別名とNumPy shapeの既存DeprecationWarningが2件。両群・両配置・両学習段階で新D/Hの出題、完全正解・M1/M3・M3優先・J単独、正誤解説・同一問題の再回答・冪等性・履歴保存・同期/先行生成を検証した。隔離SQLiteでseed・起動時補修を再実行し、旧参加者・教材・回答・snapshotの不変を確認した。以前のv12全文検証も採用時の履歴検証として維持した。
- frontendのnpm testとnpm run buildは成功。隔離Mockのbackend 8031 / frontend 3031でブラウザ88条件を完了した。LLM確認V1/V2各24条件（幅1440/390×両群×両配置×事前unknown/M1/M3）、LLM再テスト32条件（幅1440/390×両群×両配置×両問題版×通常/事前満点経路、各条件でV1/V2）、事前テスト8条件を確認した。
- ブラウザで改訂文の一致、長文の折り返し・非重複・横はみ出しなし、J単独・3択・正誤解説・再回答を確認し、desktop/mobileのスクリーンショットを目視した。V1の混合誤答ではA/D/Hを選択し、今回の両選択肢を含む回答のM3優先判定を確認した。問題・選択肢の公開項目に正答・診断情報を追加していない。
- 隔離DBの通常版ターンは全て保存学習版13で、interactiveとsame_session_prefetchの両方を確認した。新規参加者は全員仕様版21で、通常版は学習13、易しい版は学習4だった。用語注釈・AI入力・生成契約・モデル設定・採点・フローは変更しない。
- 検証環境は/tmp/gogainen-llm-dh-v13-vytf0brvの独立した合成データのみ。確認用3031番環境は検証後に通常版・デバッグ配置へ戻す。研究DB・3000番環境の再起動/DB更新、Word・別仕様リポジトリ・実AI呼び出し・既存データ削除は行っていない。直前の変更を保持し、こちらからコミット・pushは行っていない。buildが生成したnext-env.d.tsの変更行だけを戻した。機械検査・Mockによる結果を分類妥当性・読みやすさ・難易度同等性の実証とは扱わない。

## 2026-10-26 仕様版20・マルチエージェントと記憶の再テスト改訂

- 通常版multi_agent/memory_processのretest_v1/v2、計4問の場面・設問・36選択肢を指定文どおり採用した。正解/M1/M3各3つとJを維持し、マルチエージェントV1と記憶V2は4段落、残る2問は2段落で表示する。記憶V2の段落内の途中改行だけをつなぎ、太字・装飾用Markdown・重複する場面/問題見出しを保存していない。[全文・分類理由・保存と検証条件](33_multi_memory_retest_revision.md)。
- 新規だけ仕様版20 / experiment-plan-2026-10-26-multi-memory-retests-v1と通常版テストscenario-actions-v6を保存する。学習は通常版12・易しい版4を維持し、新しい学習YAMLを追加しない。旧テストv5のSHA-256と変更前HEADとのバイト単位一致、残り5テスト問題・全9確認問題・訂正情報・易しい版・辞書の不変を確認した。前回のv5完全一致テストはアーカイブの採用時履歴検証として維持した。
- backend全テストは925 passed。Starlette anyio別名とNumPy shapeの既存DeprecationWarningが2件。両群・両配置で通常経路と事前満点経路を進め、改訂V1/V2とfinal_testによる各V1共用、完全正解・M1/M3・M3優先・J単独、冪等再送、表示時のラベル・本文の保存、結果レビュー・回答履歴、早期満点と上限未達終了・正答情報非公開を確認した。
- 隔離SQLiteでseedと起動時補修を再実行し、新旧IDの分離、旧Question/QuestionOption本文・判定の保持、旧仕様版19の参加者・回答・保存評価・snapshotの不変を検証した。snapshot優先・不足時の旧問題ID/旧v5からの復元、旧仕様版19の操作・再送・worker・削除・補修・再計算拒否と集計除外も確認した。
- frontendのnpm testとnpm run buildは成功。隔離Mockのbackend 8030 / frontend 3030でブラウザ104条件を完了した。再テストは3用語それぞれ32条件（幅1440/390×両群×両配置×両問題版×通常/事前満点経路、各条件でV1/V2）の96条件、事前テストの回帰8条件を確認した。LLM知識の既定値を維持した共通検証スクリプトにRETEST_TERM_SLUG=multi_agentまたはmemory_processを追加して使用した。
- ブラウザは本文・選択肢の一致、対象だけの改行表示・太字なし、長文の折り返し・非重複・横はみ出しなし、J単独・3択・保存ラベル・結果レビュー・2回上限を検証した。desktop/mobileのスクリーンショットも目視した。問題・選択肢・各テストに注釈や正答/分類情報は追加していない。隔離DBの新規参加者は全員仕様版20で、通常版104件が学習12、易しい版104件が学習4を保存し、activeなテストは両版で24行だった。
- 検証環境は/tmp/gogainen-retests-v6-4o8rqkzkの研究DBとは独立した合成データのみ。実AI呼び出し、3000番環境の再起動・DB更新、Word・別仕様リポジトリ、既存データ削除、コミット・pushは行っていない。buildが生成したnext-env.d.tsの変更行だけを元へ戻した。分類妥当性・初心者への読みやすさ・難易度同等性を機械検査だけで実証したとは扱わない。

## 2026-10-26 仕様版19・LLM知識の確認問題と再テストの改訂

- 通常版llm_knowledgeのlearning_round_v1/v2とretest_v1/v2の場面・設問・36選択肢を指定文どおり採用し、正解/M1/M3各3つとJ、application/predictionを維持した。確認V1/V2と再テストV1は2段落、再テストV2は4段落。残り7確認問題・7テスト問題、訂正情報・易しい版・旧学習バンクの不変を検証した。[全文・分類理由・保存と検証条件](32_llm_confirmation_retest_revision.md)。
- 新規だけ仕様版19 / experiment-plan-2026-10-26-llm-confirmation-retest-v1と通常版学習12・テストscenario-actions-v5（易しい版は学習4・テストeasy-v1）を保存する。旧学習v11とテストv4のSHA-256、v4アーカイブと変更前HEADのバイト単位一致を確認した。隔離SQLiteでseed・起動時補修を再実行し、別DB ID、旧問題・選択肢・参加者・回答・評価の保全、snapshot優先・旧バンクでの復元を確認した。
- backend全テストは836 passed。Starlette anyio別名とNumPy shapeの既存DeprecationWarningが2件。旧仕様版18を含む操作・再送・worker・削除・補修・再計算の拒否と集計除外、現行版の登録・問題取得・結果解決を確認した。通常経路の確認V1→再テストV1未達→確認V2→再テストV2と、事前満点後のfinal_testによるV1共用を両群・両配置で検証した。完全正解・M1/M3・M3優先・J単独、正誤解説・再回答・先行生成・冪等性・未達終了・正答情報非公開を確認した。
- frontendのnpm testとnpm run buildは成功。隔離Mockのbackend 8029 / frontend 3029でブラウザ112条件を完了した。LLM確認V1/V2各24条件（幅1440/390×両群×両配置×事前unknown/M1/M3）、再テスト32条件（幅1440/390×両群×両配置×両問題版×通常/事前満点経路、各条件でV1/V2）、事前テスト8条件、変更対象外の記憶V2の24条件を確認した。
- ブラウザは問題・選択肢の一致、改行・太字なし、折り返し・非重複・横はみ出しなし、J単独・3択・保存ラベル・結果確認・回数上限を検証し、desktop/mobileのスクリーンショットを目視した。再テストはfrontend/tests/llm-retest-revision-browser.mjsを使い、問題・選択肢・各テストに注釈や正答情報を追加していないことも確認した。保存した通常版ターンのinteractive/same_session_prefetchが学習版12を使うことを読み取り専用で確認した。
- 検証環境は/tmp/gogainen-llm-v12-gdhiof2eの研究DBとは独立した合成データだけ。実AI呼び出し、3000番環境の再起動・DB更新、Word・別仕様リポジトリ、既存データ削除、コミット・pushは行っていない。buildが生成したnext-env.d.tsの変更だけを元の行へ戻した。機械検査・Mockによって分類妥当性・初心者への読みやすさ・問題間の難易度同等性が実証されたとは扱わない。

## 2026-10-26 仕様版18・記憶プロセス確認問題V2の改訂

- 通常版学習バンクv11を追加し、memory_process・learning_round_v2の場面・設問・9選択肢を献立提案AIの指定文どおり採用した。scenario_type=prediction、正解/M1/M3各3つとJを維持する。旧v10のSHA-256と、記憶V1を含む残り8確認問題の不変を検証した。[全文・分類理由と検証条件](31_memory_round_two_revision.md)。
- 場面説明と設問を空行で区切る2段落にし、用語・variant番号2・献立提案AIの導入文と設問段落で今回の通常版V2だけにpreserve-linesを追加する。太字・Markdown装飾・重複する「問題：」は保存しない。記憶V1の3段落とマルチエージェントV2/V3の既存表示、易しい版・各テストの表示は維持する。公開API・DB列・教授プロンプト・AI生成契約・採点・配置・回数上限は変更しない。
- backend全748テスト、frontend smoke、本番build/TypeScriptに合格した。既存Starlette/NumPyのDeprecationWarningが2件ある。通常経路の事前→記憶V1学習→再テスト1未達→記憶V2学習で、両群・両配置・unknown/M1/M3開始の出題、完全正解、M1/M3判定とM3優先、J単独/混在拒否、回答後解説、同一V2での再回答、先行生成、冪等再送、保存履歴を検証した。追加した問題版切替の検証は終了時に元の管理設定を復元し、後続テストへ設定を残さない。
- 新規だけ実験仕様版18 / experiment-plan-2026-10-26-memory-round2-v1と通常版学習版11（易しい版4）を保存する。旧仕様版17の操作・再送・worker・削除・再計算拒否、集計除外、ログ/CSV閲覧と記録保全を確認した。隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧v10と旧参加者の不変、snapshot優先・保存版からの旧記憶V2復元、新版欠落・不整合時の非フォールバックを確認した。
- 旧版用のテストバンク対応表へ17を追加し、現行18は現行版用の定義を使う。旧版用辞書に18を追加せず、通常版・易しい版の登録・事前問題取得・結果用問題の解決が成功することを検証した。キャッシュ容量の任意改善は今回の変更に含めない。
- 隔離Mock API 8028番 / frontend 3028番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件を新しい通常版・記憶V2で実行した。合成セッションや直接DB操作を使わず通常経路で2回目の用語学習へ入り、2段落の表示、太字なし、本文・9選択肢とJの一致、選択・正誤解説・誤答後の続行、文字の収まり・非重複・横はみ出しなしを確認した。desktop/mobileのスクリーンショットを保存し、目視でも確認した。
- 同じ24条件を易しい版記憶V2、通常版・易しい版記憶V1、通常版マルチエージェントV1/V2/V3、LLM知識、易しい版マルチエージェントV2で実行し、計216条件に合格した。通常版記憶V1/V2とマルチエージェントV2/V3だけwhite-space: pre-wrap、他は従来のnormalである。通常出題しないマルチエージェントV3だけは既存の隔離用補助処理で検証用3回目セッションを用意し、通常進行の回数上限は変更しない。
- 隔離DBの記憶V2保存ログを読み取り専用で確認し、interactive生成24件とsame_session_prefetch生成16件がすべて学習版11を記録していた。同期・先行生成が同じ保存版・問題を参照することを確認した。
- 再実行はfrontend/tests/learning-confirmation-browser.mjsの従来の隔離用変数にLEARNING_TERM_SLUG=memory_process、LEARNING_VARIANT_INDEX=2を指定する。LEARNING_QUESTION_SET_MODE=easyでは改訂対象外の易しい版V2を検証する。旧YAML、各テストと訂正情報、AI実装・モデル設定の不変、Markdownリンクとgit diff --checkを確認した。研究DB・3000番・Word・別仕様リポジトリの変更、実AI呼び出し、既存データ削除、コミット・pushは行わない。機械検査・Mockだけで分類妥当性・初心者への理解しやすさを実証したとは扱わない。

## 2026-10-25 仕様版17・記憶プロセス確認問題V1の改訂

- 通常版学習バンクv10を追加し、memory_process・learning_round_v1の場面・設問・9選択肢を指定文どおり採用した。scenario_type=application、正解/M1/M3各3つとJを維持する。旧v9のSHA-256、残り8確認問題の不変を検証した。旧バンク・易しい版・各テスト・訂正情報・AI実装・モデル設定は変更しない。[全文・分類理由と検証条件](30_memory_confirmation_revision.md)。
- 大学・学生の説明、開発担当者の目的、設問を空行で区切る3段落にし、用語・variant番号1・本文の導入文と開発担当者の段落で今回の問題だけにpreserve-linesを追加する。太字・Markdown装飾・重複する「問題：」は保存しない。マルチエージェントV2/V3の表示は維持する。公開API・DB列・教授プロンプト・AI生成契約・採点・配置・回数上限は変更しない。
- backend全671テスト、frontend smoke、本番build/TypeScriptに合格した。既存Starlette/NumPyのDeprecationWarningが2件ある。通常の事前テスト→初回学習で、両群・両配置・unknown/M1/M3開始の出題・完全正解・M1/M3判定とM3優先・J単独/混在拒否・回答後解説・同一問題での再回答・先行生成・冪等再送・保存履歴を検証した。
- 新規だけ実験仕様版17 / experiment-plan-2026-10-25-memory-confirmation-v1と通常版学習版10（易しい版4）を保存する。旧仕様版16の操作・再送・worker・削除・再計算拒否、集計除外、ログ/CSV閲覧と記録保全を確認した。隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧v9と旧参加者の不変、snapshot優先・保存版からの旧記憶V1復元、新版欠落・不整合時の非フォールバックを確認した。
- 隔離Mock API 8027番 / frontend 3027番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件を通常版・記憶V1で実行した。通常経路で初回学習へ入り、3段落の表示、太字なし、本文・9選択肢とJの一致、選択・正誤解説・誤答後の続行、文字の収まり・非重複・横はみ出しなしを確認し、desktop/mobileのスクリーンショットを目視確認した。記憶V1には合成セッションや直接DB操作を使わない。
- 同じ24条件を易しい版の記憶V1、通常版マルチエージェントV1/V2/V3、LLM知識、易しい版マルチエージェントV2でも実行し、計168条件に合格した。今回の記憶V1と既存の通常版マルチエージェントV2/V3だけwhite-space: pre-wrap、他は従来のnormalである。通常出題しないV3だけは既存の隔離用補助処理で検証用3回目セッションを用意し、通常進行の上限は変更しない。
- 隔離DBの記憶V1保存ログを読み取り専用で確認し、interactive生成24件とsame_session_prefetch生成16件がすべて学習版10を記録していた。同期・先行生成で同じ保存版・問題を参照することを確認した。
- 再実行はfrontend/tests/learning-confirmation-browser.mjsの従来の隔離用変数にLEARNING_TERM_SLUG=memory_process、LEARNING_VARIANT_INDEX=1を指定する。LEARNING_QUESTION_SET_MODE=easyで改訂対象外の易しい版を検証する。Markdownリンクとgit diff --checkを確認した。研究DB・3000番・Word・別仕様リポジトリの変更、実AI呼び出し、既存データ削除、コミット・pushは行わない。機械検査・Mockだけで分類妥当性・初心者への理解しやすさを実証したとは扱わない。

## 2026-10-25 仕様版16・マルチエージェント確認問題V3の改訂

- 通常版学習バンクv9を追加し、multi_agent・learning_round_v3の場面・設問・9選択肢を学内Wi-Fi問い合わせの比較問題へ変更した。Hの文末だけ合意した表現へ補正し、scenario_type=comparison、正解/M1/M3各3つ・Jを維持する。旧v8のSHA-256、V1・V2を含む残り8確認問題の不変を検証した。[全文・分類理由と検証条件](29_multi_agent_round_three_revision.md)。
- 導入文・案1・案2・検索ツールの説明・設問を空行で区切り、V2と同じpreserve-linesをV3にも適用する。太字・Markdown装飾・重複する「問題：」は保存しない。公開API・DB列・教授プロンプト・AI生成契約・採点・配置・挑戦上限は変更しない。
- backend全596テスト、frontend smoke、本番build/TypeScriptに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。両群・両配置・両学習段階で、検証用の3回目セッションによる出題・完全正解・M1/M3判定とM3優先・J単独/混在拒否・回答後解説・再回答・同期/先行生成・冪等再送と保存履歴を検証した。通常経路は最大2周のまま未達でアンケートへ進み、V3へ進まないことも別途確認した。
- 新規だけ実験仕様版16 / experiment-plan-2026-10-25-multi-agent-round3-v1と学習版9（易しい版4）を保存する。旧仕様版15の操作・再送・worker・削除・再計算拒否、集計除外、ログ/CSV閲覧と記録保全を確認した。隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧v8と旧参加者の不変、snapshot優先・保存版からのV3復元、新版欠落・不整合時の非フォールバックを確認した。
- 隔離Mock API 8026番 / frontend 3026番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件をV3で確認した。APIで作成した隔離DBの未回答セッションだけをsession_index=3にし、本番用の検証APIや回数上限の変更は追加しない。5段落の表示、太字なし、本文・9選択肢とJの一致、選択・正誤解説・誤答後の続行、文字の収まり・非重複・横はみ出しなしを確認し、desktop/mobileのスクリーンショットを目視確認した。
- 同じ24条件を通常版V2・易しい版V2・通常版V1・LLM知識で実行し、V3を含む計120条件に合格した。通常版V2/V3だけwhite-space: pre-wrap、他は従来のnormalで、問題文の太字要素がないことを確認した。通常V1/V2は実際の進行経路を使い、V3の合成セッションと区別する。
- V3ブラウザ検証にはfrontend/tests/learning-confirmation-browser.mjsの従来の隔離用変数とLEARNING_TERM_SLUG=multi_agent、LEARNING_VARIANT_INDEX=3、LEARNING_FIXTURE_DB_URLを指定する。既存一時SQLiteと同じAPI参加者・未回答セッションであることを検証する。旧YAML、易しい版、各テスト・訂正情報、AI実装・モデル設定は不変。Markdownリンクとgit diff --checkを確認し、研究DB・3000番・Word・別仕様リポジトリの変更、実AI呼び出し、既存データ削除、コミット・pushは行わない。機械検査やMockだけで分類妥当性・読みやすさを実証したとは扱わない。

## 2026-10-25 仕様版15・マルチエージェント確認問題V2の改訂

- 通常版学習バンクv8を追加し、multi_agent・learning_round_v2の場面・設問・9選択肢を、単一AIと役割別AIの2案の比較問題へ変更した。原文一致、正解/M1/M3各3つ・J、variant_keyとscenario_type=predictionの維持、旧v7のSHA-256と残り8確認問題の不変を確認した。旧v3・v5・v6・v7、易しい版、各テストと訂正情報、教授プロンプト・生成契約・DB列・公開APIは変更しない。[全文・分類理由と表示条件](28_multi_agent_round_two_revision.md)。
- 導入文・案1・案2・設問を空行で区切り、太字・装飾用Markdown記号・重複する問題ラベルは付けない。用語・variant番号と本文の案1/案2段落で今回の問題だけを限定し、既存preserve-linesを使う。易しい版V2やV1・他用語は従来の表示のままである。
- backend全547テスト、frontend smoke、本番build/TypeScript、git diff --checkに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。通常の事前→学習V1→再テスト1未達→学習V2という経路で、両群・両配置・両学習段階の出題、完全正解、M1/M3判定とM3優先、J単独/混在拒否、回答後解説、同一V2での再回答、先行生成、冪等再送を検証した。
- 新規だけ実験仕様版15 / experiment-plan-2026-10-25-multi-agent-round2-v1、通常版の学習版8・易しい版4を保存する。旧仕様版14の操作・再送・worker・削除・再計算拒否、集計除外、ログ/CSVと記録保全を確認した。隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧v7が不変、snapshot優先・保存版からのV2復元、新版欠落・不整合時の非フォールバックを確認した。
- 隔離Mock API 8025番 / frontend 3025番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件を通常版V2で実施した。通常の進行経路で2回目の学習へ入り、案1・案2の改行、太字なし、本文・9選択肢とJの一致、選択・正誤解説・誤答後の続行、文字の収まり・非重複・横はみ出しなしを確認した。desktop/mobileの教材・問題・解説と長い選択肢を保存し、表示を目視確認した。
- 同じ24条件を易しい版V2・通常版V1・LLM知識でも実行し、計96条件に合格した。通常版V2だけwhite-space: pre-wrap、他の3条件は従来のnormalで、問題文の太字要素がないことをブラウザで検査した。
- 再実行はfrontend/tests/learning-confirmation-browser.mjsと従来の隔離用環境変数を使う。LEARNING_TERM_SLUG=multi_agent、LEARNING_VARIANT_INDEX=2が今回のV2。LEARNING_QUESTION_SET_MODE=easyで易しい版V2、未指定はstandard/round1/llm_knowledge。研究DB・3000番・Word・別仕様リポジトリの変更、実AI呼び出し、既存データ削除、コミット・pushは行わない。機械検査やMockを分類妥当性・読みやすさの実証とみなさない。

## 2026-10-25 仕様版14・マルチエージェント確認問題V1の9選択肢具体化

- 通常版学習バンクv7を追加し、multi_agent・learning_round_v1の9選択肢を指定文・指定順で採用した。欠落したM1先頭のリスト記号とYAML字下げのみを補正し、M1先頭Dも言い換えない。Dには適切な連携にも読める曖昧さが残るため、原文採用の合意と未検証性を[27](27_multi_agent_choice_revision.md)へ記録した。
- 旧v6のSHA-256、場面・設問・scenario_type、正解/M1/M3各3つ、J、残る8確認問題の不変を検証した。旧v3・v5・v6、易しい版v4、テスト問題・訂正情報、教授プロンプト・AI生成契約・注釈・API・DB列は変更しない。新版欠落・不整合時は他版へフォールバックしない。
- 新規参加者だけ実験仕様版14 / experiment-plan-2026-10-25-multi-agent-confirmation-v2、通常版の学習版7・易しい版4を保存する。旧仕様版13の操作・再送・worker・削除・再計算拒否、ログ閲覧・CSV出力と集計除外、保存済み記録の不変を確認した。隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧v6のsnapshot不足時は当時の版から復元し、保存snapshotがあれば優先することを検証した。
- backend全500テスト、frontend smoke、本番build/TypeScript、git diff --checkに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。両群×両配置×両学習段階で、完全正解、M1、M3優先（H・Iを含む混在回答）、J単独と混在拒否、回答後解説、同一問題での再回答、先行生成、冪等再送を検証した。
- 隔離Mock API 8024番 / frontend 3024番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件をマルチエージェントで、同じ24条件をLLM知識の回帰確認で実行した。問題・9選択肢とJの一致、公開項目の非漏えい、選択・正誤解説・誤答後の続行、選択肢内の文字の収まり・隣接要素の非重複・横はみ出しなしを確認した。desktop/mobileの問題・教材・解説と長い選択肢のスクリーンショットを保存し、目視確認した。
- 再実行はfrontend/tests/learning-confirmation-browser.mjsと従来の隔離用環境変数を使用する。LEARNING_TERM_SLUG=multi_agentが今回、未指定またはllm_knowledgeが回帰確認。研究DB・3000番・Word・別仕様リポジトリの変更、実AI呼び出し、既存データ削除、コミット・pushは対象外。機械検査とMockだけで初心者への読みやすさや分類妥当性を実証したとは扱わない。

## 2026-10-25 仕様版13・マルチエージェントの確認問題改訂

- 通常版学習バンクv6を追加し、multi_agent・learning_round_v1の場面・設問とM3選択肢H・Iだけを指定文へ変更した。旧v5のSHA-256、旧v3、他の7選択肢とJ、残り8確認問題（LLM知識の前回改訂を含む）が不変であることを検証した。易しい版・テスト問題・訂正情報・AIプロンプト・生成契約も変更しない。[全文と分類根拠](26_multi_agent_confirmation_revision.md)。
- 新規は実験仕様版13 / experiment-plan-2026-10-25-multi-agent-confirmation-v1、通常版の学習版6・易しい版4を保存する。旧版12以下の操作・再送・worker・削除・再計算を拒否し、現行集計から除外する。隔離SQLiteでseedと起動時補修を2回ずつ実行し、旧v3・v5の参加者・セッション・教材/回答JSONが不変、snapshot優先と保存版での不足時復元を確認した。バンク不整合・欠落時は他版へフォールバックしない。
- backend全481テスト、frontend smoke、本番build/TypeScript、git diff --checkに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。今回の改訂問題について両群×両配置×両学習段階で完全正解、M3優先（H・Iを含む混在回答）、J単独と混在拒否、正誤解説、再送、先行生成と同一問題での再回答を検証した。
- 隔離Mock API 8023番 / frontend 3023番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件をマルチエージェントで、同じ24条件をLLM知識の回帰確認で実行した。問題全文・10選択肢の一致、公開項目の非漏えい、J単独、正誤解説、誤答後の続行、文字の収まり・選択肢間の非重複・横はみ出しなしを確認した。desktop/mobileの問題・教材・解説のスクリーンショットを保存し目視確認した。
- 再実行はfrontend/tests/learning-confirmation-browser.mjsを使う。従来の隔離用環境変数に加えてLEARNING_TERM_SLUG=multi_agentで今回の問題、未指定またはllm_knowledgeで前回問題を検証する。実AI呼び出し、研究DB・3000番・Word・別仕様リポジトリの変更、データ削除、コミット・pushは実施しない。機械検査・Mockだけで初心者への読みやすさや分類妥当性を実証したとは扱わない。

## 2026-10-25 仕様版12・LLM知識の確認問題改訂

- 通常版学習バンクv5を追加し、LLM知識のlearning_round_v1だけを履修案内AIの指定文へ変更した。シナリオ・設問・9選択肢の完全一致、J追加、正解/M1/M3各3つ、旧v3のSHA-256不変、残る8確認問題の不変を検証した。易しい版・テスト問題・訂正情報・AIプロンプトは変更しない。全文・分類根拠は[25](25_learning_confirmation_revision.md)。
- 新規通常版は学習版5、易しい版は4、実験仕様版12 / experiment-plan-2026-10-25-learning-confirmation-v1を保存する。旧版11以下は閲覧専用。旧v3のsnapshotなし履歴が新v5へ置換されないこと、保存snapshot優先、版不整合・欠落時の非フォールバックを検証した。
- 隔離SQLiteでseed・起動時補修を2回ずつ実行し、旧版11の参加者・セッション・教材/回答JSONが不変であることを確認した。既存の旧版操作・再送・worker・再計算・削除拒否と集計除外も両学習版で確認した。テストDB行数やDB列は追加変更しない。
- backend全436テスト、frontend smoke、本番build/TypeScript、git diff --checkに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。両版・両群・両配置の採点、M3優先、J単独、先行生成、再送、回数上限を回帰確認した。
- 隔離Mock API 8022番 / frontend 3022番で、1440px・390px × 両群 × 両配置 × unknown/M1/M3開始の24条件をPlaywrightで確認した。新問題・10選択肢と公開項目、J単独、混在誤答・unknown・正答の解説、誤答後の同一問題での続行、横はみ出しなしを確認し、スクリーンショットを保存した。desktop/mobileの教材・問題・解説を目視した。再実行はfrontend/tests/learning-confirmation-browser.mjsを使用する。
- LEARNING_VERIFY_ISOLATED=1、非3000ポートのLEARNING_UI_BASE_URL、LEARNING_PLAYWRIGHT_MODULE、LEARNING_SCREENSHOT_DIRを明示し、Chromeと隔離Mockで検証する。これは実AI生成成功や初心者への理解しやすさの実証ではない。研究DB・3000番・Word・別仕様リポジトリ、既存データ削除、コミット・pushは対象外。

## 2026-10-25 仕様版11・問1 Fの表現改善

- 通常版事前テスト問1のFだけを指定文へ変更し、M1判定と既存訂正情報を維持する。v3からの差分がこの本文とバンク識別子だけであることを検証した。問題文・他選択肢・再テスト・学習確認・易しい版は不変。
- 旧v3のYAMLが更新前HEADとバイト単位で一致することを確認した。旧版10の通常版・易しい版について、操作・再送・worker・削除・再計算の拒否、集計除外、保存済み記録の不変、当時のv3による結果復元を検証した。snapshotのない旧Fの本文も新Fに置き換わらない。
- 隔離SQLiteでseedと起動時補修を2回ずつ実行し、旧問題・選択肢・参加者・回答・評価が不変、移行後36問題行・active24行であることを確認した。新規は仕様版11 / experiment-plan-2026-10-25-pretest-f-wording-v1 / scenario-actions-v4。新DBは24行、DB列追加なし。
- backend全424テスト、frontend smoke、本番build/TypeScript、git diff --checkに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。
- 隔離Mock API 8021番 / frontend 3021番で、1440px・390px × 通常版・易しい版 × デバッグ・ランダム配置の8条件、各3問をPlaywrightで確認した。APIのFが指定文と一致すること、正答情報非公開、折り返し・重なり・横はみ出しなし、3つ選択・J単独選択、採点・結果レビューの表示ラベルと本文保存を照合した。再実行はfrontend/tests/pretest-improvement-browser.mjsを使用する。
- AIプロンプト・生成契約・注釈・教材600〜800文字・採点・配置・研究仮説・評価式は変更しない。実AI、研究DB、3000番、Word、別仕様リポジトリ、既存記録削除、コミット・pushは対象外。

## 2026-10-25 仕様版10・問1 A・Bの表現改善

- 通常版事前テスト問1のA・Bを承認文へ変更し、両方とも正解を維持する。v2からの差分がこの2本文とバンク識別子だけであることを検証し、問題文・他選択肢・訂正情報・再テスト・学習確認・易しい版は変更しない。
- 旧v2のYAMLをバイト単位で保全し、前回の6選択肢と4教授対象の改訂も歴史的検証として残す。新規版10 / experiment-plan-2026-10-25-pretest-wording-v1 / scenario-actions-v3を使用し、版9以下は閲覧専用。
- 隔離SQLiteで旧v2＋易しい版からseedと起動時補修をそれぞれ2回実行した。旧ID・本文・判定・参加者・回答・評価は不変で、36問題行・active24行を維持する。旧版9のsnapshotなし選択本文を旧Aから復元し、未回答問題やfinal_test後の回次もv2から復元する。旧版9の再送・worker・削除・再計算拒否、集計除外を両学習版で確認する。新DBは24行、DB列追加なし。
- backend全419テスト、frontend smoke、本番build/TypeScript、git diff --checkに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。
- 隔離Mock API 8020番 / frontend 3020番で、1440px・390px × 通常版・易しい版 × デバッグ・ランダム配置の8条件、各3問をPlaywrightで確認した。APIのA・Bが承認文と完全一致すること、公開項目、折り返し・重なり・横はみ出しなし、3つ選択・J単独選択、採点と結果レビューのラベル・本文保存を検証した。24スクリーンショットを保存し、desktopデバッグとmobileランダムの問1を目視した。
- 再実行はfrontend/tests/pretest-improvement-browser.mjsを使用する。PRETEST_VERIFY_ISOLATED=1、非3000のPRETEST_UI_BASE_URL、PRETEST_PLAYWRIGHT_MODULE、PRETEST_SCREENSHOT_DIRを指定し、隔離MockとChromeで行う。実AI・研究DB・3000番・Word・別仕様リポジトリ・既存記録の削除・コミット・pushは対象外。

## 2026-10-25 仕様版9・通常版事前テストの改善

- 通常版事前の問1 C/I、問2 D、問3 A/D/Iを承認文へ変更し、誤答4選択肢の訂正情報を整合させる。旧v1のアーカイブとissue156 fixtureを保持し、指定外の本文、再テスト、学習確認、易しい版YAMLの不変を検証する。全文と分類根拠は[21](21_assessment_action_questions.md)。
- 両版の全テスト・学習確認で数値的な文長検査を撤廃し、短文・長文・大きな文長差を受け付ける。空欄・重複・選択肢数・役割数・教授対象の検査は維持する。教材600〜800文字の検査、AIプロンプト・生成契約v7・注釈v1・採点・最大テスト回数は変えない。
- 新規は仕様版9 / experiment-plan-2026-10-25-pretest-improvement-v1 / 通常版scenario-actions-v2。旧版8以下は再送・worker・起動時補修・集計を含め閲覧専用。旧版6〜8のsnapshot不足時も当時のバンクと回次を参照し、新バンクを代用しない。
- 隔離SQLiteで旧通常版12行＋易しい版12行からseedを2回再実行し、36行・active24行・選択肢360行となることを確認した。旧標準問題12行は非active、旧ID・本文・判定情報は不変。新DBは24行で、DB列は追加しない。保存済み評価・回答・参加者を更新せず、移行・起動時補修を再実行しても不変であることを検証する。
- backend全414テスト、frontend smoke、Next.js本番build/TypeScriptに合格。既存Starlette/NumPyのDeprecationWarningが2件ある。
- 隔離Mock API 8019番 / frontend 3019番で、1440px・390px × 通常版・易しい版 × デバッグ・ランダム配置の8条件、各3問をPlaywrightで確認した。折り返し、横はみ出し・チェック欄と本文の重なりなし、3つ選択、J単独選択、採点、結果レビューの表示ラベル・本文を照合した。24スクリーンショットを保存し、長文を含むmobile問3とdesktopランダム問1を目視した。
- 再実行用はfrontend/tests/pretest-improvement-browser.mjs。PRETEST_VERIFY_ISOLATED=1、非3000ポートのPRETEST_UI_BASE_URL、PRETEST_PLAYWRIGHT_MODULE、PRETEST_SCREENSHOT_DIRを指定し、Chromeと隔離Mockを使う。長さが回答の手掛かりとなり得ること、初心者の読みやすさやM3の妥当性を実証したものではないことに留意する。
- 実AI、研究DB、稼働中3000番、Word、別仕様リポジトリ、過去の検証記録は対象外。コミット・push・既存試用データ削除は行わない。

## 2026-10-25 仕様版8・共通の用語注釈

- feature/issue-132で教材・回答後解説の下へ固定辞書25語の補足一覧を追加する。両群・両問題版に同じ辞書と抽出規則を使い、問題・選択肢・各テスト・結果確認には付けない。AI本文・プロンプト・出力Schema・生成契約版v7・教材600〜800文字は変更しない。
- 新規参加者だけ仕様版8 / experiment-plan-2026-10-25-glossary-v1とする。版7以下の操作・再送・worker・起動時補修・集計の境界を保ち、注釈のない旧JSONや問題snapshot欠落時の版7問題復元を確認する。
- 抽出は表示文字列、長い語の優先、表記揺れ、英字境界、出現順・重複排除を検証する。不正辞書はDB初期化前に起動を拒否する。指紋・表示文snapshot、再取得・再送・先行生成、管理ログ・CSV、モデル入力への非混入をテストする。
- backend全385テスト、frontend smoke、Next.js本番build/TypeScript、git diff --checkに合格。既存のStarlette/NumPyのDeprecationWarningが2件ある。
- 隔離SQLiteとMock API（8013番）・検証用画面（3013番）で、1440px/390px×通常版/易しい版×両群×正答/誤答の16ケースをPlaywrightで確認した。表示された用語・説明とAPIの保存snapshotを照合し、横はみ出しなし、回答後の続行操作を確認した。空の注釈欄の非表示は専用API応答fixtureで確認し、抽出処理そのものの該当語なしはbackend単体テストで確認した。スクリーンショットを目視した。
- 再実行用はfrontend/tests/learning-glossary-browser.mjs。GLOSSARY_VERIFY_ISOLATED=1、非3000ポートのGLOSSARY_UI_BASE_URL、GLOSSARY_PLAYWRIGHT_MODULE、GLOSSARY_SCREENSHOT_DIRを明示し、Mockのみの隔離環境を使う。必要時はGLOSSARY_BROWSER_CHANNEL=chromeを指定する。
- ブラウザ検証の隔離DBへ版7の合成旧記録を加え、起動時補修・seedを2回再実行した。参加者・回答・セッション・教材・保存評価の全行の指紋が前後で一致し、active問題24行も維持された。DB列・問題バンク・既存snapshotを追加変更していない。
- 実AI生成は再実行していない。注釈表示の検証を実AI成功や初心者への理解しやすさの実証とせず、現在のモデル非対応エラーと区別する。研究DB・稼働中3000番・Word・別仕様リポジトリ・問題YAML・モデル設定・過去の検証記録は変更しない。辞書全文と出典は[24](24_learning_glossary.md)。

## 2026-10-25 管理画面のAIモデル切替

- 管理画面にGPT-6.1 Sol / GPT-6 Lunaを追加。選択値と推論レベルはbackendプロセス内だけに保持し、AI呼び出しごとにモデル/effortを固定してthread/start、turn/start、監査へ同じ値を渡す。既定はgpt-6-luna / low。明示的な環境設定は優先する。
- APIで両モデルの選択、推論設定との独立性、許可外モデルの422、Mockでの409を確認。呼び出し中に設定が変わっても開始済み要求・監査は固定され、次の呼び出しから変更されることをbackend testで確認した。
- backend全351テスト、frontend smoke・production build/TypeScript、git diff --checkに合格。macOSのpytest既定一時パスではUnix socketテストがパス長上限に当たったため、`TMPDIR=/tmp`で全体を再実行して通過した。既存DeprecationWarningが2件ある。
- 隔離SQLite・app-server未接続のローカル管理画面/APIを起動し、状態取得・切替・無効値を確認した。実AI app-server検証では、GPT-6.1 Sol / GPT-6 Lunaのlow/medium/high全6要求が現在のChatGPTアカウントでmodel_not_found（アカウント非対応）となった。自動フォールバックはせず、実際のモデル生成成功は確認できていない。
- 研究計画書原本、DB schema、実験仕様版、protocol、問題/教授指示は変更していない。作業は当時未commit・未pushで、稼働確認は隔離DBだけを使用した。

## 実験全体の進捗メーター

- `current-step` は既存のstep遷移契約を維持し、現行参加者にだけ `{stage_id, label, percent}` を追加で返す。旧試用・未知状態は `progress: null`。GETによるDB更新・評価再計算・正答/診断情報の追加公開がない。
- 事前テスト・採点中0％、事前後1回目まで25％、事前後2回目まで50％、アンケート75％、終了100％を確認する。学習前の内部`final_test`は事前後1回目として数え、完了したテスト回数と表示割合を一致させる。
- 通常経路、初回満点経路、早期満点、2回目未達、学習ギブアップ、実験ギブアップを確認する。結果レビュー画面は「テストの結果確認」とし、現在の画面名を次工程の表示に誤置換せず、割合だけ保存済みの次工程に合わせる。
- 画面取得の再読み込み・再開・再送で割合が保存状態から再現される。開始・同意・管理・旧試用では表示せず、読込中に仮の％を出さない。API失敗時に再取得でき、回答操作を妨げない。
- 両群・問題版・選択肢配置モードで表示規則が共通。終了100％は手続き完了であり、満点到達とは別である。

実装検証（2026-10-25）: backend全346テスト、frontend smoke、Next.js本番build/TypeScript検査、`git diff --check`に合格。既存NumPy DeprecationWarningが1件ある。Playwrightで既存の3001番開発画面を使い、API応答をテスト用にスタブして、結果確認25％、進捗取得失敗後の再取得、終了100％、390px幅の横はみ出しなし、開始・同意・管理画面での非表示を確認した。画面検証はAPIスタブによるもので、研究DBや3000番は使用していない。実験フローと進捗値の組合せはbackendテストで確認した。

## PR #162 採点時の用語データ欠落への対処

- score_phaseでTermの存在を確認し、欠落時は503 question_term_unavailableで停止する。正常時の採点・分類・回数・実験仕様版は変更しない。他2件のレビュー指摘に対するコード変更は行わない。
- 隔離SQLiteで最後の未採点回答の用語データを欠落させ、通常版/易しい版×retest/final_test×再送キー有無の8ケースを検証した。先に処理した回答も含め、採点・学習状態・教授対象・再発記録・参加者の進行と回数が確定されないこと、失敗時の再送でも不変なこと、用語復旧後に同じ再送キーで正常に採点でき回数が1回分だけ進むことを確認した。
- backend全344テスト、frontend smoke・production build/TypeScript検査、git diff --checkに合格。既存NumPy DeprecationWarningが1件ある。今回の実AI・独立ブラウザ検証は行っていない。研究DB、稼働環境、プロンプト、問題YAML、旧データは変更せず、コミット・pushも行わない。

## 2026-10-24 仕様版7・通常版と易しい版

- backend全336テスト、frontend smoke、production build/TypeScript検査、git diff --checkに合格。既存NumPy DeprecationWarningが1件ある。
- 通常版の2 YAMLは変更前のSHA-256と一致。両版の役割数、文長、重複、分類理由、教授対象、別版ID拒否、版固定、履歴復元、先行生成、再送、回数上限を検証した。隔離SQLiteの列追加・seed再実行・旧版6記録とNULL保持・保存評価の保全を確認した。
- 通常版/易しい版×両配置×両群×通常/事前満点経路の16通りを、Mockと合成記録だけを使う隔離DBでブラウザ完了した。最大3テスト・未達終了・結果レビュー・アンケート・版別記録を確認した。
- 管理画面の版切替と独立した集計版切替、CSVリンク、保存値をブラウザ確認。1440px/390pxのスクリーンショットを目視し、ボタンの折り返しと管理表の横はみ出しを修正した。
- 実AIは隔離DB・Codex app-server 4501番・gpt-5.6-luna/lowで、易しい版の両群×M1/M3/unknownをAPIとブラウザで確認した。教材生成、誤答解説、再教材、正答要約、600〜800文字、本文証拠、実送信beginner、統制群への診断非混入を照合した。
- 途中の実AI試行では証拠文の不一致で3試行後503停止も観測した。検査を緩めず、本文を平易化した後の証拠コピーを明示する指示を追加し、最終ブラウザ実行の6条件は完了した。失敗ログも隔離DBに保持した。成功を生成成功率や初心者への有効性の実証とは扱わない。
- 再実行用: frontend/tests/test-cycle-limit-browser.mjs（CYCLE_QUESTION_MODES=standard,easy / CYCLE_OPTION_MODES=debug_fixed,randomized）、question-set-admin-browser.mjs、easy-real-ai-browser.mjs。既存の隔離ガードと非3000ポート指定を必要とする。実AIのAPI検証はbackend/scripts/verify_plan_real_ai.pyへVERIFY_QUESTION_SET=easyを指定する。
- 検証DBは/tmp/gogainen-easy-uiと/tmp/gogainen-easy-real。研究DB、稼働中3000番、Word、別仕様リポジトリ、過去の問題YAMLは変更していない。コミット・pushは行っていない。

## 2026-10-24 仕様版6・事前込み最大3テスト（当時の検証記録）

- 当時は仕様版6 / experiment-plan-2026-10-24-two-posttests-v1。事前後のテストをfinal_test込み最大2回に制限し、2回目未達は未達のままsurveyへ進む。学習後回数の保存列と共通の導出回数を区別する。
- 行動選択型の9固有問題、final_testのretest_v1共用、次回の全用語retest_v2、未回答・前後回次ID拒否、再送時の非加算、旧版5の読取り専用を検証する。
- 新問題は旧問題と別ID。隔離DBのseed再実行で旧本文・選択肢・snapshotなしの過去表示・保存評価が不変で、新問題を重複作成しないことを確認する。
- backend全269件、frontend smoke、本番build/TypeScript検査、git diff --checkに合格。既存NumPy DeprecationWarningが1件あり、テスト失敗ではない。
- 隔離SQLiteで旧15問題・150選択肢を保持したまま新12active行（9固有問題＋final共用行）を追加し、再seedでも旧本文・判定情報・snapshotなしの過去表示・保存評価が不変であることを確認した。ブラウザ用隔離DBでもseedを2回再実行し、参加者行の不変と12active行/120選択肢を確認した。
- 検証専用8001/3001、合成番号、Mockのみで、両群×通常/事前満点の4経路を完了した。各経路で9問/3テスト、事前後2回終了、全問題の非重複、未達維持、アンケート、満点到達指標0、管理画面の共通回数と学習後回数の区別を確認した。1440px/390pxのスクリーンショットと横方向のはみ出しも確認した。
- 再実行はfrontend/tests/test-cycle-limit-browser.mjsへCYCLE_VERIFY_ISOLATED=1、隔離環境のCYCLE_UI_BASE_URL、CYCLE_PLAYWRIGHT_MODULE、CYCLE_SCREENSHOT_DIRを明示する。専用ChromiumがなければCYCLE_BROWSER_CHANNEL=chromeでインストール済みChromeを利用できる。Next devはlocalhostで接続する。研究用3000番には実行しない。
- 実AIは呼び出さず、過去の実AI成功を今回の結果とは扱わない。研究DB・稼働中3000番・既存試用・Word・別仕様リポジトリを変更せず、コミット・pushは行っていない。

## 2026-10-23 学習確認v3・仕様版5

- 新規参加者のみ実験仕様版5 / experiment-plan-2026-10-23-learning-rotation-v1とし、retest_cycles_completed=0で開始する。既存版4以下、旧protocol_id、NULL記録は閲覧専用である。
- `standard/learning_questions_v3.yml`は3用語×3学習セッションvariantの9問で、`archive/learning_questions_v2_unused.yml`はアーカイブとして検証・保存するが、通常の出題には使わない。易しい版の確認問題は`easy/learning_questions_v4_easy.yml`から読み込む。
- 各用語の学習セッションはsession_indexに対応するv1→v2→v3の固定順。同一セッション内は同じ問題を最大3回答し、誤答時は教材だけを再生成する。
- enrichmentとconceptual_changeの問題本文・選択肢・正答は一致し、教材生成のstageだけが変わる。
- 最大経路の固有問題数はテスト12問＋学習9問＝21問、採点回答イベントの最大数は39回である。

## 2026-10-22 学習後再テスト回数の上限

- 新規参加者のみ実験仕様版4 / `experiment-plan-2026-10-22-v1`とし、`retest_cycles_completed=0`で開始する。既存参加者の追加列はNULLのまま保たれ、旧版記録は閲覧専用である。
- 学習後`retest`の採点済みバッチを最大3回数える。1・2回目の未達は学習へ戻り、3回目の未達は正誤・未回答・未達対象を保ってアンケートへ進む。満点はどの回でもアンケートへ進む。学習前`final_test`は上限に含めない。
- 未回答を含む再テストバッチも1回とする。`Idempotency-Key`による採点再送で回数を重複加算しない。上限時の結果確認には未達であることとアンケートへの案内を表示する。
- 全backendテスト249件合格。初回はmacOSの一時パスがAF_UNIXの長さ上限を超えて既存transportテスト1件が失敗したため、短い`--basetemp=/tmp/gogainen-pn-pytest`を指定して再実行し全件成功した。既存NumPy DeprecationWarningが1件ある。
- frontend smokeとNext.js production build/TypeScript検査に合格。隔離SQLiteの旧スキーマ列追加・既存行不変・seed再実行、新規参加者の初期値、上限到達・早期満点・final_test除外・未回答保持・冪等再送を自動テストで確認した。
- 今回は実AI生成・研究DBへの変更・コミット・pushを行っていない。UIはsmoke/buildとAPI応答に基づく検証であり、独立したブラウザ操作確認は未実施。

## 2026-10-21 PR #145レビュー対応

- レビュー6件を実装と照合し、重複import・検証スクリプトの重複ガード/辞書キー・削除済み登録キー検索の4件を修正した。登録キーは監査JSONを全件取得せずSQL側で配列内の完全一致を判定する。DB列・テーブル・既存監査は変更しない。
- 当時の削除実装では、削除の早期commitという指摘は再現しなかった。delete_participantはdefer_commitsを尊重する_commitを使っていた。対応表削除失敗で研究DB側をrollbackする検証を行ったが、別DB間の分散トランザクションを保証するものではなく、後述の2026-10-22対応で削除順序と回復方式を置き換えた。
- 通知にjsonrpcフィールドを追加する指摘は、[Codex公式Protocol仕様](https://learn.chatgpt.com/docs/app-server#protocol)と異なるため現行のmethod/paramsのみを維持した。WebSocket/Unix socketの両方で、initialized通知の正確な形とaccount/read前の送信順を確認した。
- backend全240件合格（新規2件）。隔離SQLiteの旧記録保持・移行/seed・再送・削除の既存テストを含む。frontend smoke・本番ビルド/型検査、検証スクリプトの構文確認、git diff --checkも合格。
- 永続volumeや公開ポートを持たない隔離PostgreSQL 16でも、複数キーを持つ監査・キーなし旧監査・引用符/ワイルドカード/日本語を含むキーの完全一致と非部分一致、seed再実行、対応表削除失敗のロールバック、撤回後の再送409を確認した。検証用DBと合成データは破棄した。
- 研究DB・対応表・既存実AIログ・実験仕様版・protocol_id・モデル・教授条件は変更していない。今回の修正では教材RAGの外部送信・実AI生成を再実行せず、コミット・push・GitHubへの投稿・レビュー解決・マージは行っていない。

## 2026-10-22 分離DB間の参加者削除回復

- 研究DBでは参加者データ削除と対応表削除待ち状態を同一トランザクションで確定し、その後に対応表SQLiteを削除、最後に監査状態をcompleteへ更新する順序に変更した。研究DB commit失敗時は対応表を保持し、対応表削除失敗時はpendingを維持する。
- pendingはアプリ起動時に自動再試行し、削除APIの再送でも回復できる。対応表の消去が保留中ならAPIは503を返し、研究データ削除済みであることと再試行が必要なことを説明する。
- 隔離テストで、研究DB commit失敗時に参加者と対応表が残り対応表削除が呼ばれないこと、対応表削除失敗時に研究DB削除とpending監査が残ること、対応表削除後の監査commit失敗も冪等に回復すること、API再試行・再起動でcleanupが完了することを確認した。
- backend全243テスト合格。既存のNumPy形状設定に関するDeprecationWarningが1件ある。`git diff --check`も合格。
- 実参加者データ・実AI呼び出し・実験仕様版・protocol_idは変更していない。frontendコードは変更していない。

## 2026-10-21 ランダム配置の「わからない」末尾固定

- ユーザー指定により、「わからない」は最後のJ、残る9択はA〜Iへ決定的に配置する。テスト21問・学習確認30問すべてで末尾固定・重複なし・再取得時の同じ並び、正解/M1/M3のA〜Iでの均衡を確認した。
- 隔離SQLiteで、両群の共通配置、表示ラベルに依存しない採点、unknown単独選択、回答snapshotを確認した。変更前の配置を模した保存済み学習問題も再取得・回答時に元の並びを保持する。
- backend全238件、frontend smoke・本番ビルド（型検査含む）合格。既存のStarlette/NumPy非推奨警告2件はテスト失敗ではない。
- 研究用3000番・研究DBから分離した検証用3001番、隔離SQLite、合成参加者、Mockのみでブラウザ確認。事前3問のJ固定・unknown選択時の他9択の無効化・回答保存・学習画面のJ固定を確認した。今回の表示変更で実AIや教材RAGの外部送信は行っていない。
- 既存回答・教材snapshotの書換え、実験仕様版・protocol_id・問題本文・教授条件の変更、コミット・pushは行っていない。稼働中の研究環境への反映は、回答途中を避けて再ビルド・再作成する。

## 2026-10-21 同意書・分離対応表の検証

- backend全223テスト合格。その後の登録キー空白対策・CSV数式検証を含む対応表15テストも合格。学籍番号の必須入力・型エラーの非反射・研究DB全テーブル/研究用CSVへの非混入・同意時刻/文書版・二重送信・対応表削除後の再送・撤回後の登録キー再送拒否・保存失敗時のロールバックを確認した。
- 旧データ保護・nullable列追加・seed再実行は既存の隔離SQLiteテストに加え、consent_document_version/consented_atを欠くDBの移行でも確認。仕様版とprotocol_idは変更しない。
- frontend smokeとNext.js本番ビルド（型検査を含む）合格。専用DockerネットワークのMock API・3001番の画面に対しPlaywrightで登録、ブラウザ保存領域への学籍番号非混入、対応表CSVダウンロード、削除キャンセル、個別/全件削除後の研究データ保持を確認。全文スクリーンショットも目視確認した。
- AI待機中に参加者を削除した場合、後着AIログを保存しないことを確認。対応表の保存先が研究DBと同じ場合は拒否する。
- ローカル3000番へ反映。backend停止後にSQLite backup APIでバックアップを作成・整合性確認し、再起動後に既存286行・17テーブルの旧列全件が同一であることを照合した。既存参加者の追加同意列はNULLのまま。反映後の同意画面は読み取り専用のブラウザ確認、healthと空の対応表APIは200を確認した。研究DBに検証参加者を作成していない。
- 今回の実AI検証は未実施。隔離SQLite・合成番号での実行を試みたが、RAG資料をAIへ送信することへの明示承認がないとして自動承認レビューに拒否された。過去の実AI合格記録を今回の検証結果とは扱わない。
- 管理者認証、責任者等の正式値、正解位置のデバッグ配置は未対応/保留のまま。対応表の削除機能や確認ポップアップを、本実験開始可能・アクセス制御実装済みの根拠にしない。

## 2026-10-18 PR #142レビュー修正の検証

- backend全210テスト合格（新規5ケース）。未作成の入れ子出力先への参加者別/群別CSV、仮説2の未観測人数・終了状況別観測回数・仮説6の分母不変、教材表示のみで離脱した場合のキャッシュ更新と再表示時の非更新、指標版更新時の現行プロトコル限定再作成を確認した。
- 教材表示のキャッシュ監視がないという指摘は既存コードで再現しなかった。Participant.updated_atとTutorTurn.updated_atの監視を維持し、表示のみ・未回答の回帰テストを追加した。
- 全テストには隔離SQLiteでのnullable列移行・seed再実行・旧記録保全の既存テストを含む。今回はDBスキーマ・実験プロトコル・教授内容・仮説の主計算式を変更していない。指標版はsix-hypotheses-v2。
- frontend smoke・Next.js本番ビルド合格。Linux Node.js v22.14.0を使用。
- browserスキルの組み込みブラウザは接続エラーで実行できず、独立Playwright/Chromiumで代替した。初期満点・教材閲覧の両経路を通し、8/14アンケート項目、管理画面の未達内訳、群別CSV、内訳人数の合計と仮説6の分母を確認した。両群それぞれ中断・継続中・完了時点未達・その他を1人ずつ含む合成データも使い、未達者の観測回数平均1.5を照合した。スクリーンショット環境には日本語フォントがないため、ラベル内容はDOMで検査した。
- 検証用Codex app-server（4501番）、API（8001番）、画面（3001番）、SQLiteと出力先（/tmp/gogainen-pr142.dR3Cfk/）を使用。研究DBや8000番の既存プロセスは変更しなかった。検証用3プロセスは終了した。
- 今回の実AIは教材閲覧経路で教材生成と正答要約の計2呼出し。保存監査でcodex_app_server / gpt-5.6-luna / lowを確認した。両群×3タイプの全組合せは今回再実行しておらず、下記の先行検証記録と区別する。
- git diff --check合格。コミット・push・GitHubコメントの投稿やスレッド解決は行っていない。

## 2026-10-18の計画整合実装・今回の検証

- backend全205テスト合格。6仮説の期待値、欠測/対象外/未達、初期満点final_test、後半variant再使用、アンケートの厳密入力・必須条件、教材表示の冪等性を検証した。
- 隔離SQLiteで不足nullable列の追加・起動/seed再実行・旧版3を含む旧記録の不変を検証。配布先PostgreSQL/Dockerの実行確認とは区別する。
- frontend smokeとNext.js本番ビルド合格。検証には一時配置したLinux Node.js v22.14.0を使用した。
- 実Codex CLI 0.149.0のログイン済みapp-serverを検証専用4501番で起動し、gpt-5.6-luna/lowで両群×M1/M3/unknownの教材・正答要約を確認した。M1回答後のM3誤答解説と次教材も両群で確認した。
- backend/scripts/verify_plan_real_ai.pyで本文証拠・文字数・表示記録、実送信model/effort、統制群入力分離を検査した。Mockへ切り替えていない。
- 実AIの記録は検証専用の/tmp/gogainen-plan-verification.dbと/tmp/gogainen-plan-exportsへ分離した。研究DBを移行・再計算していない。
- 画面は独立したPlaywright/Chromiumで、開始→同意→事前テスト→初期満点final_test/教材閲覧学習→再テスト→結果確認→アンケート保存→終了→管理画面まで両経路合格。未表示者は8選択項目、表示者は14選択項目と必須自由記述、教材評価平均8の保存・集計を確認した。
- 組み込みブラウザはsandboxCwd接続エラーで使用できず、一時Playwrightと不足ライブラリ2個を/tmpへ置いて代替した。OSやリポジトリの依存定義へブラウザ用パッケージを追加していない。

実AIの再実行はPLAN_VERIFY_ISOLATED=1、AI_BACKEND=codex_app_server、隔離SQLite DATABASE_URL、EXPORT_DIR、RAG_BASE_DIR、検証用CODEX_APP_SERVER_URLを明示して上記スクリプトを使う。画面検証はfrontend/tests/plan-browser.mjsにPLAN_VERIFY_ISOLATED、ローカル専用PLAN_UI_BASE_URL、PLAN_PLAYWRIGHT_MODULEを明示する。通常の研究DBへ接続しない。

採用判断は[20](20_experiment_plan_alignment.md)、指標は[12](12_evaluation_metrics.md)。デバッグ正答配置・管理アクセス・割付運用・承認等は未解決であり、テスト合格を実験開始可能の認定としない。

## 先行する文書整理時点の受け入れ条件（過去記録）

- 計画書の6仮説が研究条件・評価指標・対応表・READMEで同じ番号と意味を持つ。
- 目標仕様、現行実装、未対応D01〜D07、要確認Q01〜Q10を区別する。計画書の抜粋を現行送信原文としない。
- low目標/medium既定値、unknownの目標/現行6項目、新アンケート/現行5段階、最大3回答/計画書の表現差を明記する。
- 出典の指紋、参照ファイル・行番号、Markdownリンクと見出しを確認し、git diff --checkを実行する。
- 変更は仕様書類のMarkdownのみ。Word、履歴、別リポジトリ、コード・設定・問題・API・DB・実行版・既存データを変更しない。
- この文書更新ではbackend/frontend全テスト・実AI生成・seed・DB移行を実行しない。以下はコード変更時の受け入れ条件と過去の検証記録であり、今回の実行結果ではない。

## 文書整理時点の実装後チェックリスト（当時未実施）

- [ ] 計画書に合わせた共通/統制群指示とunknownの教授・検査契約を、入力・Schema・Mock・送信監査まで照合する。
- [ ] 両群のgpt-5.6-luna / lowを配布設定と実送信で確認する。
- [ ] 有無回答・1〜10段階・教材評価6項目・自由記述を画面から保存・CSVまで通して確認する。
- [ ] 測定条件確定後、仮説1〜6の回次・単位・分母・閲覧/欠測/中断・経路別ケースを検証する。
- [ ] デバッグ正解配置の復旧、管理アクセス対策、同意と割付運用を収集開始前に確認する。

詳細な保留条件は [計画書対応表](20_experiment_plan_alignment.md)。未確定の式・新しいSchemaをテスト側で先に確定しない。

## 現行実装の受け入れ検証

```sh
cd backend && TEST_DATABASE_DIR="$(mktemp -d /tmp/gogainen-tests.XXXXXX)" .venv/bin/pytest -q
cd frontend && npm test
cd frontend && npm run build
git -c core.whitespace=cr-at-eol diff --check
```

- seedは事前3・再6・最終の共用行3（12active行、9固有問題）。廃止問題は非activeで保存。
- 現行経路の学習バンクは通常版v15の9問。通常版の現行テスト・確認問題はsplit-assessmentの6設問・4択単一選択である。
- 採点・結果確認・再学習・ギブアップ・ロック・冪等性・先行生成の回帰検証。
- final_test未採点の直接学習開始を拒否し、廃止専用URL/APIは404。
- NULL・実験仕様版1〜22・未対応版は409。旧POST、cached再送、先行生成でも値が不変。
- can_resume、ブラウザ新規開始、厳密入力、参加者向け正答非公開。
- 全3タイプ/両群のprompt・Schemaに廃止教授や支援量がなく、方略enumを固定。transfer_checkは必須。
- 履歴・生AI・保存評価・CSVを保持し、再計算/群集計しない。
- 隔離DBで移行とseed再実行を確認。

## 選択肢配置切替（issue-143）

- 管理APIの初期値・DB永続化・未知modeの拒否、既存参加者への非遡及、新規参加者へのmode snapshotを確認する。
- テスト9固有問と学習確認9問それぞれで、同じ問題の決定的な表示順、全10ラベルの重複なし、「わからない」のJ/末尾固定、正解/M1/M3のA〜I内のラベル別回数差1以内を確認する。
- 両群・参加者間・アプリ再起動後に同一問題の並びが変わらないことを確認する。
- 採点・教授対象・unknown単独選択が表示ラベルではなく内部ID/メタデータに基づき、設問取得APIの選択肢に正誤属性やM1/M3分類を含まないことを確認する。
- AttemptおよびTutorTurnのsnapshotが表示当時のラベル・本文・順序を保持し、既存mode未記録はdebug_fixedとして表示されることを確認する。

## 共通履歴の条件（仕様版3でも維持）

- 同じ用語の全フェーズ/全周回の履歴、snapshot優先と復元、時系列、J、正誤混在、他用語/未回答/prefetch除外を検証。
- 教材・正答要約・誤答解説の全タスクで共通履歴を渡し、統制群の診断・教授情報を除外。共通データが同じなら群間で一致、診断だけの変更ではcontrol prompt不変、履歴変更では変化。
- 両群のunknown開始、M1/M3とunknown間の変化、正答終了で問題・variant・遷移が一致。
- 先行生成の投影履歴と確定後履歴が一致し、現在回答が重複しない。解説失敗・二重送信、入力への過去AI解説全文の非混入、自動prefix追記がないことを回帰検証する。生成文の意味的な解説混入を自動判定するテストとは区別する。
- NULL/仕様版1/2/未対応版は操作・再送・worker・起動時補修でも不変。新規版3だけを進行・集計。
- AI監査の仕様版/契約版/共通履歴件数/SHA-256/出題規則版/有効入力を照合。

実AI確認はAI_BACKEND=codex_app_serverで接続・ログインを確認し、両群教材・正答要約・誤答解説をブラウザ操作する。実送信prompt、Schema、モデル・推論、共通RAG、版、教材長と照合する。Mock成功を実AI成功とみなさない。

## 仕様版3の章立て条件

- 両群promptに固定小見出し・固定順序・固定項目数・従来の見出し禁止がない。統制群には診断と型別契約を渡さない。
- 任意の小見出し・異なる節数・順序・複数要素をまとめた教材・従来の見出し・重複見出しを許容する。
- 冒頭の用語見出し、1つ以上の非空###節、内部ラベル非表示を検証する。見出し風のインライン文字列やコード/引用内見出しは節として扱わない。
- JSONだけ・見出しだけの証拠、空フィールド、必須要素欠落、教授契約不一致を拒否する。固定見出し先頭文や任意の行で補正せず、同backendで最大3試行・失敗503とする。
- AIログのmaterial_structureとTutorTurnのmaterial_structure_validationで、見出し順・節数・証拠配置・最終検証が一致する。
- 新規版3だけ進行/補修/集計し、版2以下の旧記録・保存教材・回答・評価・生AIログは再計算も書換えもしない。
- 実app-server・隔離DBで両群×M1/M3/unknown、正誤解説・次教材・再学習を確認し、自由な章立てと固定の教授内容を分けて監査する。

## 自動検査と目視確認の境界

自動テストの合格とgeneration_validation.validは、契約ID・指定方略・フィールド条件・証拠文字列の本文出現・章立て・文字数・禁止文字列など、実装済みの機械検査への合格を示す。教材の事実的正しさ、反駁の妥当性、言い換えによる正答漏えい、意味的な過去解説混入まで保証しない。生成教材と解説は研究者が目視確認し、[AI契約の検証範囲](10_ai_prompt_contracts.md#出力検証) と区別して記録する。

管理画面・管理APIの認証・権限確認は未実装であり、「研究者限定」という運用方針を認証機能の受け入れ結果として扱わない。本実験開始前のアクセス対策と、その有効性確認は [セキュリティ仕様](15_security_privacy.md) の未解決事項である。旧試用の書込み409や移動確認ダイアログのテストは、管理者アクセスを制限できることの証明ではない。

## 2026-10-07の検証記録

- backend全136件、frontend smoke、frontend build、git diff --checkを実施。
- 隔離SQLiteで既存スキーマへのnullable列追加・seed再実行を確認。旧行・保存評価の不変を検証。
- 実app-server（gpt-5.6-luna / medium）で両群×M1/M3/unknownの6ケースをブラウザ確認。M1ケースは両群の誤答解説・次教材・正答要約まで確認。
- 送信監査ログで方略enum、現行版、旧教授入力の不在を照合。生成の欠落/文字数違反は検証で拒否し、Mockへは切り替えなかった。
- 旧試用の閲覧専用画面をdesktop/mobileで確認。ブラウザ状態だけの新規開始、旧POST/管理者削除の409、旧ログ表示、全問正解の事前/最終結果画面、廃止ページ404を確認。
- 管理画面の両群で現行参加者数と旧試用数の分離、API群集計との一致、保存評価の試用区分を確認。旧記録は個別ログに保持したまま、全体評価の現行一覧から除外。
- 起動した検証環境はbackend/.local/old-spec-validation.dbを使用し、従来の試用DBを変更していない。

## 仕様版2の検証記録（2026-10-07）

- backend全151件、frontend smoke・build・型検査、git diff --checkを実施。
- 同じ用語の全フェーズ/全周回、snapshot優先と不足部分の復元、時系列、J単独、正誤混在、他用語/他参加者/未回答/未利用prefetchの除外を確認。
- 3AIタスクの統制群promptは診断だけを変えても不変で、共通回答履歴を変えると変化する。履歴内の入れ子の診断情報も除外される。
- 隔離SQLiteで仕様版1の進行・回答・保存評価・prefetch状態が起動時補修で変わらず、版2だけが補修されることを確認。seed再実行は21問/210選択肢のままで重複しない。
- 実app-server（gpt-5.6-luna / medium）で両群×M1/M3/unknownの6ケースをブラウザ確認。M1は誤答解説・次教材・正答要約まで確認し、教材の履歴が1件から2件へ増える一方、即時解説には現在回答が重複しないことを照合。
- 同じ事前回答の両群ではterm/component_terms/rag_context/interaction_historyが一致し、統制群へ明示的診断・対象主張・taxonomy・タイプ別教授方針が送られていないことを実送信promptとactual_ai_inputで確認。
- 両群とも再テスト1でM3誤答を選び、結果確認画面から再学習へ進むことをブラウザ確認。次教材の履歴は事前・学習2回・再テストの4件となり、実験群だけにM3の明示的教授情報が追加される。
- 履歴SHA-256を実送信JSONから再計算して照合。600〜800文字や教授契約に違反した試行は記録して再生成し、Mockへの切替は行わなかった。
- desktop/mobileの教材・確認問題を目視確認。検証環境はbackend/.local/issue-138-validation.dbを使用し、従来の試用DBを変更していない。

## 仕様版3の検証記録（2026-10-07）

- backend全187件成功。frontend smoke・production build・TypeScript検査、git diff --checkを実施。既存のjoblib/NumPyの非推奨警告が1件あり、テスト失敗ではない。
- 必須証拠を1/2/3/6節へ分配・統合・逆順配置したM1/M3/unknown教材が通ることを確認。要点/具体例/注意点など従来の見出しも許容し、同名の節は位置で監査する。
- 本文外・見出しだけ・JSONだけ・コード/HTML内の証拠、空節・偽の見出し・用語見出し欠落・教授契約不一致を拒否。両群とも同backendの最大3試行で検証し、自動証拠補正をしない。
- NULL/版1/版2/未対応版は、旧POST再送・worker・起動時補修・再計算・群集計の境界で保護。隔離DBの版2試用はブラウザから操作拒否を確認し、保存教材・回答・解説・評価の前後snapshotが一致。新規開始では別IDの版3参加者を作成する。
- 隔離DBのseedを再実行し、21問/210選択肢（pretest 3、retest 15、final_test 3）で重複しないことを確認。
- 実app-server（gpt-5.6-luna / medium）で両群×M1/M3/unknownの6ケースをブラウザ確認。2〜4節の自由な章立て、600〜800文字、実験群の本文内必須証拠・教材内適用確認を照合。M1は両群で誤答解説・次教材・正答要約まで確認。
- 同じ事前回答の両群で共通入力が一致し、controlの実送信入力に診断・taxonomy・型別教授契約が含まれないことを照合。共通履歴のSHA-256を実送信JSONから再計算した。
- 両群とも再テスト1のM3誤答から結果確認を経て再学習へ進み、事前/学習2回/再テストの4件履歴、自由な章立て、教授契約の検証を確認。
- 生成各試行のmaterial_structureと保存TutorTurnの章立て・節数・証拠配置を照合。証拠不一致は再生成で修正し、検証を緩めなかった。最初の確認でモデル混雑エラーも記録したが、同モデルで再試行し、Mockへ切り替えていない。
- desktop/mobileの表示と横方向のはみ出しがないことを確認。検証環境はbackend/.local/dynamic-sections-validation.dbを使用し、従来の試用DB・別仕様リポジトリ・履歴資料を変更していない。
