# 研究計画と仕様・実装の対応

2026-10-18確認の計画書の仮説一覧を優先する。目標、候補となる現行ログ、未対応を区別する。出典指紋と計画書の節ごとの対応は [計画書対応表](20_experiment_plan_alignment.md) を参照する。

| 目標・仮説 | 対応する仕様 | 現行実装・記録の候補 | 状態 |
| --- | --- | --- | --- |
| 仮説1: 正答率の伸び | docs/01・12 | Attempt、score_timeline_json.rounds | 比較回次等はQ01 |
| 仮説2: 満点までの学習セッション回数 | docs/01・12 | TutorSession、learning_burden_json、満点回答 | 集計単位・未達者はQ02 |
| 仮説3: 用語当たり周回数 | docs/01・12 | 回答済みTutorTurn、grading_json | 回答/不正解/再挑戦の定義はQ03/Q09 |
| 仮説4: 同種誤答の再選択率 | docs/01・12 | Attempt、recurrence_events、misconception_timeline_json | 対象回次・分母等はQ04 |
| 仮説5: 教材閲覧者の教材評価 | docs/01・07〜09・12 | 現行ParticipantSurveyは仮項目のみ | 新6項目と1〜10尺度はD05未対応、合成等はQ05 |
| 仮説6: 再テスト満点到達割合 | docs/01・12・19 | 採点済み再テスト、Participant、割付記録 | completed/attainment_correct_rateと区別。経路等はQ06 |
| 40名・各群20名・原則無作為割付 | docs/01・19 | A/Bコードで参加者を作成 | 自動割付・上限は未実装、運用方法を確認 |
| 共通回答履歴と群別入力 | docs/03〜05・10 | services/interaction_history.py、ai/interaction_history.py | 実装あり。共通とは取得規則であり各人の値ではない |
| 方略と本文証拠 | docs/03・04・10 | ai/backend.py、mandatory_elements.py、teaching_contract.py、material_structure.py | 実装あり。unknownの6項目等はD03未対応 |
| 教材・解説の生成と送信監査 | docs/05・06・10 | ai/codex_app_server_backend.py、services/experiment.py | 実装あり。目標文言とlow設定はD01〜D04 |
| 固定問題・採点・出題 | docs/02・08・11 | seed/content、services/experiment.py | 21テスト/30確認、M3優先、デバッグ正解配置 |
| 新アンケートの入力・保存 | docs/07〜09・12 | main.py:SurveyPayload、ParticipantSurvey、survey画面 | 現行5段階。目標へのAPI・型・保存・集計は未対応 |
| 版・閲覧専用・旧ログ保全 | docs/07・08・15 | core/experiment_spec.py、services/idempotency.py、legacy_logs.py、db/session.py | 現行版3を維持。今回の版更新・再計算なし |
| 先行生成・冪等性 | docs/05・08・18 | services/experiment.py、prefetch.py、tutor_prefetch.py | 現行挙動を維持、未利用生成物を実績に数えない |
| 承認・同意・アクセス対策 | docs/14・15・19 | 同意画面・ログ、管理API | 承認と運用は別途確認。管理者認証は未実装 |

実装パスはbackend/appからの相対位置（survey画面はfrontend/app/survey）。候補ログとの対応は、仮説の集計が実装済みという意味ではない。旧対応表はhistoryに保持する。
