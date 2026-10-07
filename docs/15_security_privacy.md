# 15. Security and Privacy

## 個人情報

MVPでは個人名・メールアドレスを収集しない。被験者IDのみ使用する。

保存しない:

- 氏名
- メールアドレス
- 学籍番号
- 電話番号
- ChatGPT認証情報
- APIキー

## ChatGPT/Codex認証

- ChatGPT認証情報をDBに保存しない
- `~/.codex/auth.json` をアプリで直接読み取らない
- app-serverの認証状態は `account/read` で確認する
- logout API（`/api/admin/ai/logout`）を提供する。現行管理画面にはログアウトボタンを置いていない。今後導線を追加する場合は誤操作防止の確認を入れる

## app-serverの公開範囲

- `127.0.0.1` のみにバインドする
- `0.0.0.0` で公開しない
- 可能なら capability token を使う
- 非ローカル公開はしない
- 現行Composeの既定はhost networkで、backendは`.env`の`CODEX_APP_SERVER_URL=ws://127.0.0.1:4500`を使う。bridgeネットワークを選ぶ場合だけ`host.docker.internal:4500`などへ上書きする

## 実験データ

保存する:

- 回答
- 理由記述（任意の互換フィールド。現行のpretest・learning画面では収集しない）
- 自信度は事前テストと学習セッションでは収集しない
- 回答時間
- AI診断
- AI応答
- 学習ログ
- 意味的な学習stageと固定教授方略
- AI call log、診断・学習ログ、再発イベント

保存しない:

- 個人名
- メールアドレス
- ChatGPTアクセストークン
- APIキー

## AI出力の注意

AIは教材と解説だけを生成する。誤りや正答漏えいを検証し、固定採点・分類・状態・方略をAIに変更させない。旧試用は読取り専用で回答や評価を更新しない。

手動修正（将来対応）:

- 修正前後を `audit_events` に保存
- 修正理由を必須にする
- CSVで手動修正済みか判別可能にする

## 削除機能（現行MVP）

現行版の参加者だけは管理画面の確認後にDELETEできる。旧試用は削除も409で拒否する。現行版の削除は所有レコードのみを対象とし、seedや他参加者の記録を消さない。

削除前に`delete_participant`の`AuditEvent`を保存し、参加者削除後もその監査記録を残す。削除は被験者1名単位であり、全参加者一括削除、全実験データ削除、CSV/export file削除のAPIはない。

## 診断結果の手動修正（将来対応）

現行管理画面では診断・AI call logを確認できるが、診断結果を編集するUIと修正内容の監査書き込みは未実装である。導入時は修正前後、修正理由、CSVでの判別方法を定義する。

## ローカル用途

このシステムは卒業研究用のローカル実験システムであり、インターネットに公開しない。

## ログ出力

アプリケーションログに出してよいもの:

- participant display_code
- API endpoint
- error_code
- latency

出してはいけないもの:

- ChatGPT token
- capability token
- raw auth response
- secret file pathの中身

## CSV取扱い

CSVは研究分析用データである。個人情報は含めないが、回答テキストが含まれるため、外部公開しない。

CSV出力先:

- `exports/`
- gitignore対象

## セキュリティ上の実装禁止事項

- OpenAI APIキー入力欄
- 認証トークンのDB保存
- app-serverの外部公開
- 管理画面の削除APIを確認なしで実行
- 被験者画面から管理者APIを呼べる設計
