# Codex実装依頼ガイド

このリポジトリには、卒業研究用AIチューターのWebアプリがすでに実装されています。新規プロジェクトの雛形作成や全面再実装をせず、依頼された変更だけを既存の構成・動作に沿って行ってください。現行動作の正本は、対象ブランチのコード、YAML、テストです。`README.md`と`docs/00_project_summary.md`〜`docs/19_experiment_operation_runbook.md`、`docs/99_sources_and_notes.md`は、その実装に追随させます。

## 研究条件

- 比較対象は、一般的なAIチューター（`control`）と、学習ログを教授に使うAIチューター（`proposed`）です。
- 現行対象用語は`llm_knowledge`、`multi_agent`、`memory_process`の3項目です。
- controlは用語情報と両群共通のRAGで一般説明を生成し、個人の診断・学習段階・回答履歴を教材選択へ使いません。proposedは診断、対象主張、学習ログ、足場掛けを使います。
- M1〜M4などの内部分類は参加者画面に表示しません。固定問題で直接判定するのはM1、M3、unknownです。
- **現行問題バンクはデバッグ配置です。** テスト系と学習確認v1/v2のA〜Cが正解、D〜FがM1、G〜IがM3、Jがunknownに固定されています。正解ラベルが手掛かりになるため、実験データを収集しないでください。現行コードには実験用の役割分散へ切り替える設定がありません。

## 現行の問題・実験フロー

- テスト系の問題は`backend/app/seed/content/learning_content.yml`、学習確認v2は`backend/app/seed/content/learning_questions_v2.yml`が正本です。学習確認v1は既存参加者との互換用です。
- テスト系は各用語pretest 1問、retest 5 variant、final_test 1問です。retestは6回目以降v5を再利用します。学習確認は用語・stageごとに5 variantを使います。
- 新規参加者は学習確認v2、既存参加者と版がNULLの参加者はv1に固定します。採点は提示済み問題の版と選択肢metadataで行い、回答時に正答情報を参加者APIへ公開しません。
- 回答中はテストの正誤を表示せず、送信後の結果確認では正解・不正解を表示します。
- pretestで学習対象がない参加者は内部`final_test`（画面表示「再テスト1」）へ進みます。学習対象がある参加者は学習後に`retest`へ進み、3用語全問正解ならsurveyへ、不正解・未回答があれば該当用語の学習へ戻ります。すべての参加者が共通のfinal_testを受けるわけではなく、backendによる学習・再テストの自動周回もありません。
- 学習ギブアップは未回答のままretestへ進みます。retest/final_testでの実験ギブアップはsurveyへ進み、survey送信後に終了します。学習対象確認中の実験ギブアップは終了画面へ進みます。
- `l0_check`と`transfer`は互換・補助経路で、現行の通常導線ではありません。

## 実装上の制約

- AI呼び出しは`AIBackend`経由とし、通常実行ではCodex app-serverを使います。OpenAI APIキーやOpenAI SDKの直接呼び出しは使いません。
- `AI_BACKEND=codex_app_server`の失敗時にMockへ自動フォールバックしません。`MockAIBackend`は明示指定のテスト・切り分け専用です。
- ChatGPT/Codexの認証情報をDB・ログへ保存しません。app-server監査では実入力やRAG情報を研究者限定で扱い、秘密情報を含めません。
- 両群へ共通の用語情報と同条件のRAGを渡し、固定問題・選択肢・正答は教材生成AIへ渡しません。LangGraph関連チャンクはRAG検索結果から除外します。
- proposedのM1/M3/unknown教材では、実装済みの`mandatory_elements`と`teaching_contract`を維持します。M2/M4の教授契約や固定診断問題を、依頼なしに追加しません。
- 教材本文はMarkdown記号込みで700文字を目標に600〜800文字を検証し、範囲外なら同一backendで最大2回再生成します。app-server失敗や契約違反をMockで隠しません。
- 既存の実験遷移、採点、API、DB列、CSV固定列は、依頼に必要な場合を除いて変更しません。参加者・研究ログを破壊する操作はしません。

## 作業手順と確認

1. 対象ブランチの状態と関連する実装・テスト・仕様を確認します。
2. 依頼に必要な範囲だけ変更し、コードの振る舞いと文書の説明を一致させます。仕様更新依頼ではMarkdownだけを編集します。
3. 変更範囲に応じたbackend/frontendテストを実行し、必要ならbuildやブラウザ確認も行います。
4. `git diff --check`と差分を確認し、未検証の挙動を完了済みと記載しません。

通常起動はDocker Compose、frontendは`http://localhost:3000`、backend healthは`http://localhost:8000/api/health`です。詳細な環境・運用条件は`docs/13_docker_development.md`と`docs/19_experiment_operation_runbook.md`を参照してください。
