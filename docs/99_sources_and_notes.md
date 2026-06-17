# 99. Sources and Notes

## Uploaded Research Decks and Design Notes

この仕様リポジトリは、以下の資料から抽出した研究計画と、その後の設計見直しをもとに整備した。

- `/Users/hiroki/Downloads/5月18日(テーマ変更) (2) 2.pptx`
- `/Users/hiroki/Downloads/5月25日進捗報告.pptx`
- `revised_experiment_flow_term_concept_stages_FINAL.md`
- `revised_experiment_flow_3phase_learning_session_v2.md`

## Current Design Summary

研究の中心は、AIチューターを作ること自体ではない。中心は、AI・情報系専門用語の初期誤概念を診断し、提案群では前提用語理解、教材あり概念理解、教材なし概念説明へ段階的に支援を減らすことで、支援なし再テストで理解が改善するかを見ることである。

比較対象は「AIを使うかどうか」ではなく、以下である。

- 統制群: RAG教材を根拠にした一般小問3件、概念フェーズ1、概念フェーズ2を行う非適応AIチューター
- 提案群: 事前テスト診断と学習ログに基づく3段階適応型AIチューター

## Key Decisions

- 対象概念は現行5概念を維持する
- `revised_experiment_flow_3phase_learning_session_v2.md` は学習セッション内部の3段階化だけを採用する
- 事前アンケートは実施しない
- 事前テストと再テストは選択式のみ
- 事前テストではM1〜M3とunknownを記録する
- 提案群だけが誤概念・過去ログ・戻り制御を教授方略に使う
- 統制群には誤概念・pretest選択肢・過去ログ・戻り制御情報を渡さない
- L0確認と転移テストは現行参加者フローから外す
- 再テストを現行フローの最終テストにする
- 学習セッション中にM1〜M4の再判定やL3/L2/L1の動的更新は行わない
- 再テストは現行通り学習対象概念のみを出す

## Final Taxonomy

| Final | Name |
|---|---|
| M1 | カテゴリー誤分類型 |
| M2 | 類似概念境界混同型 |
| M3 | 表層特徴・キーワード反応型 |
| M4 | 文脈転移失敗型 |

M4は転移テスト拡張時のために保持する。現行フローでは転移テストを実施しないため主評価には含めない。

## References in Decks

### Conceptual change / category shift

- Chi, M. T. (2009). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift.
- Chi, M. T. H. (2008). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift.

### Similar concept boundary confusion

- Hassani, H., Ghodsi, M., & Howell, G. (2010). A note on standard deviation and standard error. Teaching Mathematics and its Applications, 29(2), 108-112.
- Qian, Y., & Lehman, J. (2017). Students' Misconceptions and Other Difficulties in Introductory Programming: A Literature Review.

### Surface feature / keyword reaction

- Chi, M. T., Feltovich, P. J., & Glaser, R. (1981). Categorization and representation of physics problems by experts and novices. Cognitive Science, 5(2), 121-152.

### Transfer and scaffolding

- Bransford, J. D., & Schwartz, D. L. (1999). Rethinking Transfer: A Simple Proposal With Multiple Implications.
- 白水始. (2012). 認知科学と学習科学における知識の転移.
- VanLehn, K. (2011). The Relative Effectiveness of Human Tutoring, Intelligent Tutoring Systems, and Other Tutoring Systems.
- Zheng, L. et al. (2022). An exploratory study on fade-in versus fade-out scaffolding.
- Puech, R., Macina, J., Chatain, J., Sachan, M., & Kapur, M. (2025). Towards the pedagogical steering of large language models for tutoring.

現行設計では、ヒント量レベルを細かく変えるのではなく、前提用語理解、教材あり概念理解、教材なし概念説明、支援なし再テストという段階構造をscaffolding/fadingとして扱う。v2原文の事前アンケート、全概念再テスト、転移テスト復活は今回実装しない。

## Codex app-server Notes

このプロジェクトはOpenAI APIキーを使わない。Codex app-server経由でユーザーのChatGPT/Codexログインを使う。ただしapp-serverは仕様変更可能性があるため、`AIBackend` として隔離する。

## Design Assumptions

- MVPは参加者単位の群間比較を基本にする
- 現行5問版では学習対象用語を固定上限で切らず、正答以外を全件扱う
- MockAIBackendを必ず先に完成させる
- L0/transfer関連列は互換のため残してよいが、現行実験データでは原則nullになる

## Implementation Non-goals

- 汎用チャットボットの作成
- OpenAI APIキー利用
- インターネット公開
- 個人情報収集
- 全AI用語を網羅する教材サイト化
- 統計分析ソフト内蔵の本格実装
