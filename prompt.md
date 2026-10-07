# 現行アプリの開発指示

既存のFastAPI/Next.jsアプリに依頼された変更だけを行う。正本はコード・YAML・テストと実験仕様版1のdocs。旧資料はdocs/historyに隔離し、旧実行機能を再導入しない。

- 対象3概念、分類M1/M3/unknown、状態stable_correct/misconception/unknown。
- controlは共通用語/RAGだけ。proposedは事前誤答/現行診断/履歴を説明へ利用。方略はbackendで固定する。
- AIは教材生成・正答要約・誤答解説のみ。固定採点・分類をAIへ委ねない。
- Codex app-serverを使い、APIキー/SDK直接利用、認証情報保存、Mockへの自動フォールバックは禁止。
- テスト21問、学習確認はv2の30問。複数選択と時刻のみを回答入力に使う。
- A〜C正解、D〜F=M1、G〜I=M3、J=unknownはデバッグ配置。依頼なしに変更せず、研究収集前に別作業で分散を復旧する。
- テスト後の結果確認、再学習ループ、ギブアップ、先行生成、冪等性を維持する。
- 教材600〜800文字、M1/M3/unknown必須要素、teaching_contractと教材内transfer_checkを維持する。
- 既存試用/未対応版は閲覧専用。再送/生成前に409、保存状態/回答/評価を変更しない。新規開始は新しいIDを作る。
- 旧物理列と生AIログを保持し、legacy_*マッピング/legacy_fieldsから履歴だけを読み出す。CSV固定ヘッダを維持する。

backend全テスト、frontendテスト/build、隔離DB移行/seed、実AIブラウザ確認、git diff --checkを実施する。コミット/pushは指示まで行わない。研究仮説と現行評価ログの対応はdocs/01、12、17を参照する。
