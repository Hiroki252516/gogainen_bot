# 教材の用語解説モード（仕様版29導入履歴）

## 現行条件（仕様版41）

新規参加者は`integrated_material`に固定する。管理画面には教材モード名・固定表示・切替ボタンを置かず、管理用GET/PUT APIも提供しない。登録時には`Participant.learning_material_glossary_mode`へ固定値を保存し、教材生成では辞書v4を両群共通の意味参照として渡す。教材本文で実際に使う登録語を文脈に合わせて説明し、教材右側の用語注釈欄を隠す。教材snapshot・回答後解説・テスト注釈は従来どおり保存・表示する。

仕様版41 / `experiment-plan-2026-11-07-fixed-admin-settings-control-shared-prompt-v1`を新規参加者に適用する。仕様版40以下と旧protocolは閲覧専用とし、参加者の保存モード、教材、snapshot、回答を変更しない。`RuntimeSetting.learning_material_glossary_mode`列は過去値を保全するため残すが、現行コードでは参照・更新しない。仕様版39での固定化、仕様版40での管理画面表示削除、仕様版41での統制群プロンプト統合は[受入記録](14_testing_acceptance.md)を参照する。

## 仕様版29導入時の条件・実装履歴

## 条件と適用範囲

仕様版29導入時に管理画面の「注釈欄のみ／教材内解説」切替を追加し、当時は初期値を「注釈欄のみ」とした。選択内容は新規参加者へ登録時固定し、登録後の設定変更は既存参加者へ遡及しなかった。設定未保存・RuntimeSettingのNULLは当時`annotation_only`として扱った。この節の既定値とUIは導入時履歴であり、現行条件は上の仕様版41節を参照する。

仕様版29 / `experiment-plan-2026-10-30-learning-glossary-material-v1`を当時の新規参加者へ保存した。現行版境界に従い仕様版35以下の既存記録は進行・回答・教材・snapshot・評価を変更しない。教材生成の実験条件を区別するための版更新であり、教材の正確さや学習効果の確認済みを意味しない。

## モードの挙動

| モード | 教材生成 | 教材画面 | 回答後解説・テスト |
| --- | --- | --- | --- |
| `annotation_only` | 辞書をAI入力へ渡さない | 現行どおり教材snapshotに基づく右側注釈を表示 | 現行どおり |
| `integrated_material` | 仕様版31から辞書を両群共通の意味参照として渡す。仕様版36ではRAGを含むv4を使用する。本文に実際に使う登録語だけを文脈に合わせて言い換え、初出時に説明するよう指示 | 教材右側の用語注釈欄を隠す。教材snapshotは監査用に保存 | 現行どおり |

「教材内解説」は辞書の全17語を列挙する要件ではない。教材で実際に扱う登録語のみを説明するよう指示する。仕様版31では定義文をそのまま転載せず、意味を参照して文脈に沿う自然な説明に言い換え、意味を変えたり辞書にない性質を足したりしないよう指示する。未登録語を辞書から増やさず、教材本文のMarkdown、見出し構成、生成Schema、教授契約v7、仕様版30で導入したannotation_only 600〜800文字・integrated_material 600〜1200文字条件は維持する。教材内解説モードであっても回答後解説用glossary、テスト用glossary、辞書の抽出規則・保存snapshotを変更しない。v2辞書は履歴用に保持し、仕様版35以下の参加者・snapshotは更新しない。仕様版36のRAG追加は[RAG注釈](49_rag_glossary.md)を参照。

## 管理API・保存（仕様版29時点の履歴）

- 当時は認証済み`GET/PUT /api/admin/learning-material-glossary-mode`を提供していた。仕様版39で両ルートを削除した。
- RuntimeSettingとParticipantにnullableな`learning_material_glossary_mode`列を追加する。軽量schema補修はSQLite/PostgreSQLで冪等に行い、既存行へ値を埋めない。
- 仕様版29〜38では新規登録時に設定値をParticipantへコピーした。仕様版39以降は`integrated_material`を固定保存し、RuntimeSetting値は参照しない。
- 参加者一覧、個別ログ、participants CSVに登録時値を含める。旧NULLは「未記録（旧仕様）」であり「注釈欄のみで登録した」と断定しない。
- 教材生成APIへ`show_material_glossary`を追加する。従来のmaterial glossary snapshotは両モードで返却・保存し、教材内解説モードの画面だけがその表示を隠す。

## 教材生成入力と群分離

教材内解説モードでは、固定辞書のversionと各entryの`id`、`term`、`definition`を`glossary_reference`に入れる。これはcontrol/proposedの双方に同じ構造で渡す。`project_model_payload`で明示的に許可する任意の共通入力とし、共通回答履歴には追加しない。

生成指示は、本文で実際に使用する登録語を初出時に短く正確に説明すること、無関係な辞書語を列挙しないこと、教材内解説の本文600〜1200文字条件を守ることを求める。proposed専用の診断・taxonomy・教授情報はproposedだけに渡し、controlへの混入を許さない。仕様版29〜38のannotation-only参加者向けに`glossary_reference`を除く生成分岐は後方互換として残すが、新規参加者には適用しない。

教材表示のmaterial glossary snapshotは従来どおり`TutorTurn.diagnosis_json.material_glossary`に保存する。教材本文に統合された用語説明を自動でsnapshotへ追記したり、旧ターンを再解析したりしない。再表示は保存snapshotと参加者modeを使い、AI再生成や旧記録の補完をしない。

## 画面と運用

仕様版29〜38は管理UIでモードを切り替えられた。仕様版39では切替UI/APIを削除し、「教材内解説」を適用する固定表示にした。仕様版40で固定表示も削除し、仕様版41でも管理画面にモード名を表示しない。

学習画面では教材右側の注釈欄だけをmodeに応じて表示・非表示にする。`integrated_material`でも回答後フィードバックの注釈は表示する。テストの注釈、設問の採点、診断、教授方針にはmodeを使わない。

モードは教材で用語を説明する位置を変える実験条件である。仕様版39の変更は新しい実験条件として版で識別する。管理ログと参加者CSVにはParticipantに保存されたモードを維持し、過去版と仕様版39の結果を無条件で同等扱いしない。

## 検証境界

自動テストで確認するのは、初期値、保存・再起動後の保持、登録時snapshot、非遡及、DB NULL保全、両群の共通入力、proposed診断情報の分離、教材欄の表示制御、旧版保護、教材長条件である。プロンプトに従う指示を実AI教材が完全に実行すること、説明の意味的な正確さ、用語理解・学習成果の向上は機械検査だけで実証されない。研究者の内容確認・予備調査を別途行う。
