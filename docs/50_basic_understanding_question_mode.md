# 基礎理解版テスト問題モード（仕様版43の導入記録）

> 本文は仕様版43で導入した`basic_understanding`の条件と互換性を記録する。仕様版44で第3モード`four_topic_fundamentals`を追加し、仕様版50では事前アンケート文面と4用語版バンクを更新した。現行3モード共通条件と進行は[51](51_four_topic_foundation_mode.md)、現行アンケートは[49](49_presurvey_baseline.md)を参照する。

## 現行3モードとの互換性

新規参加者は管理画面の登録前設定に従い、`application`（現行版・場面応用）、`basic_understanding`（基礎理解版）、`four_topic_fundamentals`（4用語版）のいずれかで開始する。RuntimeSetting未設定時の現行既定値は`four_topic_fundamentals`。選択値は登録時に`Participant.test_content_mode`へ保存し、その後の管理設定変更では既存参加者の問題・回答・確認問題を切り替えない。RuntimeSettingの設定APIは管理認証を必須とし、適用範囲は新規参加者のみ。本書では最初の2モードの問題バンクと、仕様版43で導入した互換性を説明する。

仕様版43のprotocolは`experiment-plan-2026-11-08-basic-understanding-question-mode-v1`。仕様版44以降では仕様版43以下・旧protocolを閲覧専用で記録を保持し、既存Participantのspec/protocol、問題snapshot、回答、教材、評価を移行・補完しない。仕様版43の`test_content_mode=NULL`は旧既定の`application` / `split-actions-v5`として結果復元する。現行仕様版55の新規参加者にNULLは認めず、値が欠落した場合は登録・進行条件の不整合として扱う。

## 問題バンク

| モード | 問題バンク | 内容 |
| --- | --- | --- |
| `application` | `split-actions-v5` | 従来の場面応用問題 |
| `basic_understanding` | `split-actions-basic-v1` | 基礎理解を直接問う新規問題 |

基礎理解版は`backend/app/seed/content/standard/split_assessment_basic_v1.yml`に保存する。事前テスト・再テスト1・2の計9問（3用語×3回次）を含み、各問は正解1・M1誤答2・M3誤答2・unknown1の6択。仕様版43で導入した条件を引き継ぎ、現行仕様版55でも各テストで3用語各1問、計3問を出題・採点する。選択肢の配置・固定採点・表示後の注釈は共通規則を使う。

学習確認問題は直前テストで誤答した問題の保存snapshotを再利用し、ライブバンクを参照して過去の問題を書き換えない。application/basic_understandingで必要な場合は内部`final_test`に再テスト1と同じ問題を使う。教材、教材生成プロンプト、教授方略、群割付、採点規則、4用語版の固定進行は本書の対象外とし、[51](51_four_topic_foundation_mode.md)を参照する。

## 集計と記録

現行指標版`four-hypotheses-v1`は3モードごとに集計し、異なるモード間の値を合算しない。`application`と`basic_understanding`は3問、4用語版は4問を分母とする。群別・参加者別集計、詳細JSON、専用CSV/XLSX、参加者ログ、全体ログ、参加者テーブルCSVに問題モードを記録する。統合ログCSVの`test_content_mode`列は仕様版43で追加した。事前アンケート版は[49](49_presurvey_baseline.md)、評価指標は[12](12_evaluation_metrics.md)を参照する。

## 研究上の留意点

基礎理解版は、長い業務場面や複数の設計判断を減らし、RAGと重み、役割分担、会話を越える記録の各基本関係を問うよう作成した。しかし、実際に難易度が下がること、現行版と難易度・測定特性が同等であること、回次間の等価性は検証済みではない。問題は各回で表現を変えるため、同じ学習目標を保つ意図はあるが、同等性を保証しない。測定できる範囲も、対象3用語の限定された基礎理解に限られ、広い応用力や習得全体を示すものではない。

研究者向けの正誤理由・誤答の分類意図は実行時問題データに含めない。問題の教育的妥当性と基礎理解版の採用について、研究上の承認が得られたことを意味しない。収集前に研究者が内容を確認し、必要なら予備調査を行う。

## 検証契約

- 各モードの3回次・3用語・出題対象設問と役割数を検証する。
- 仕様43の新規参加者は指定モードのbank keyだけを取得・採点・復元し、設定変更は既存参加者へ遡及しない。
- 仕様42以前のNULLはv5で履歴復元され、既存snapshotを優先する。
- 管理ログ・参加者CSV・全体／参加者ログCSVとExcelにモードを含める。
- モードが混在する群集計・仮説集計は別々に出力し、統合値を生成しない。
