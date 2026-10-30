# 教材の用語解説モード（仕様版29）

## 条件と適用範囲

管理画面に「注釈欄のみ／教材内解説」を追加する。初期値は現行条件の「注釈欄のみ」。選択内容は新規参加者だけ、登録時にParticipantへ保存して固定する。登録後の管理設定変更は既存参加者へ遡及しない。設定未保存・RuntimeSettingのNULLは`annotation_only`として扱う。既存ParticipantのNULLは補完せず、仕様版28以下は閲覧専用とする。

仕様版29 / `experiment-plan-2026-10-30-learning-glossary-material-v1`を新規参加者へ保存する。仕様版28以下の進行・回答・教材・snapshot・評価を変更しない。教材生成の実験条件を区別するための版更新であり、教材の正確さや学習効果の確認済みを意味しない。

## モードの挙動

| モード | 教材生成 | 教材画面 | 回答後解説・テスト |
| --- | --- | --- | --- |
| `annotation_only` | 辞書をAI入力へ渡さない | 現行どおり教材snapshotに基づく右側注釈を表示 | 現行どおり |
| `integrated_material` | learning-glossary-v2の辞書を両群共通の参考入力として渡し、本文に実際に使う登録語を初出時に説明するよう指示 | 教材右側の用語注釈欄を隠す。教材snapshotは監査用に保存 | 現行どおり |

「教材内解説」は辞書の16語すべてを列挙する要件ではない。教材で実際に扱う登録語のみを説明するよう指示する。未登録語を辞書から増やさず、教材本文のMarkdown、見出し構成、生成Schema、教授契約v7、600〜800文字条件は維持する。教材内解説モードであっても回答後解説用glossary、テスト用glossary、辞書定義・抽出規則・保存snapshotを変更しない。

## 管理API・保存

- 認証済み`GET /api/admin/learning-material-glossary-mode`は`{mode, applies_to: "new_participants_only"}`を返し、キャッシュを無効にする。
- 認証済み`PUT /api/admin/learning-material-glossary-mode`は`mode`だけを受け付け、未知項目や許可外の値を拒否する。
- RuntimeSettingとParticipantにnullableな`learning_material_glossary_mode`列を追加する。軽量schema補修はSQLite/PostgreSQLで冪等に行い、既存行へ値を埋めない。
- 新規登録時に現在の設定値をParticipantへコピーする。管理設定の変更は開始済み参加者に反映しない。
- 参加者一覧、個別ログ、participants CSVに登録時値を含める。旧NULLは「未記録（旧仕様）」であり「注釈欄のみで登録した」と断定しない。
- 教材生成APIへ`show_material_glossary`を追加する。従来のmaterial glossary snapshotは両モードで返却・保存し、教材内解説モードの画面だけがその表示を隠す。

## 教材生成入力と群分離

教材内解説モードでは、固定辞書のversionと各entryの`id`、`term`、`definition`を`glossary_reference`に入れる。これはcontrol/proposedの双方に同じ構造で渡す。`project_model_payload`で明示的に許可する任意の共通入力とし、共通回答履歴には追加しない。

生成指示は、本文で実際に使用する登録語を初出時に短く正確に説明すること、無関係な辞書語を列挙しないこと、本文600〜800文字を維持することを求める。教材内解説モードでもproposed専用の診断・taxonomy・教授情報は従来どおりproposedだけに渡し、controlへの混入を許さない。既定のannotation-onlyでは`glossary_reference`を生成入力に含めない。

教材表示のmaterial glossary snapshotは従来どおり`TutorTurn.diagnosis_json.material_glossary`に保存する。教材本文に統合された用語説明を自動でsnapshotへ追記したり、旧ターンを再解析したりしない。再表示は保存snapshotと参加者modeを使い、AI再生成や旧記録の補完をしない。

## 画面と運用

管理UIは取得中・保存中に切替を無効化し、PUT成功後だけ選択状態を更新する。保存失敗時は前回保存済みの表示を維持し、エラーを表示する。

学習画面では教材右側の注釈欄だけをmodeに応じて表示・非表示にする。`integrated_material`でも回答後フィードバックの注釈は表示する。テストの注釈、設問の採点、診断、教授方針にはmodeを使わない。

モードは教材で用語を説明する位置を変える実験条件である。実験途中で適用する場合は条件変更として記録する。管理ログと参加者CSVでmode別に識別し、条件の異なる参加者の教材評価・結果を無条件で同等扱いしない。

## 検証境界

自動テストで確認するのは、初期値、保存・再起動後の保持、登録時snapshot、非遡及、DB NULL保全、両群の共通入力、proposed診断情報の分離、教材欄の表示制御、旧版保護、教材長条件である。プロンプトに従う指示を実AI教材が完全に実行すること、説明の意味的な正確さ、用語理解・学習成果の向上は機械検査だけで実証されない。研究者の内容確認・予備調査を別途行う。
