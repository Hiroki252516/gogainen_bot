# 99. Sources and Notes

## Uploaded Research Decks

この仕様リポジトリは、以下のPPTXから抽出した研究計画をもとに整備した。

- `/Users/hiroki/Downloads/5月18日(テーマ変更) (2) 2.pptx`
- `/Users/hiroki/Downloads/5月25日進捗報告.pptx`

## Research Plan Summary

研究の中心は、AIチューターを作ること自体ではない。中心は、AI・情報系専門用語の誤概念を学習ログから追跡し、同じ誤概念の再発抑制と足場掛けなし転移を評価することである。

比較対象は「AIを使うかどうか」ではなく、以下である。

- 統制群: 一般的なAI解説
- 提案群: 学習ログ、誤概念タイプ、足場掛けレベルに基づいて支援を変えるAIチューター

## Key Decisions from Decks

### Final taxonomy

5月18日案ではM1〜M6の誤概念分類が提示されていた。5月25日案では、先行研究に基づく独自の分析枠組みとしてM1〜M4へ整理された。

最終仕様ではM1〜M4を採用する。

| Final | Name |
|---|---|
| M1 | カテゴリー誤分類型 |
| M2 | 類似概念境界混同型 |
| M3 | 表層特徴・キーワード反応型 |
| M4 | 文脈転移失敗型 |

### Problem phase separation

5月25日案では、問題タイプとフェーズの対応が明示されていた。

| フェーズ | 使う問題 |
|---|---|
| 事前テスト | 定義問題・識別問題 |
| 学習セッション | 定義問題・識別問題・類題 |
| 即時再テスト | 事前テストと同型だが文面を変えた問題 |
| 遅延再テスト | Q1/Q2/Q4の別バージョン |

このため、実装では `construct_key` と `variant_key` を持たせ、同じ構成概念を別文面で測れるようにする。

### Main metrics

PPTXで繰り返し示されていた主評価指標は以下。

- 同種誤答再発率
- 足場掛けなし自力解答率

これらは `docs/12_evaluation_metrics.md` に定義した。

## References in Decks

### Conceptual change / category shift

- Chi, M. T. (2009). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift.
- Chi, M. T. H. (2008). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift.

M1「カテゴリー誤分類型」の根拠として使用。

### Similar concept boundary confusion

- Hassani, H., Ghodsi, M., & Howell, G. (2010). A note on standard deviation and standard error. Teaching Mathematics and its Applications, 29(2), 108-112.
- Qian, Y., & Lehman, J. (2017). Students' Misconceptions and Other Difficulties in Introductory Programming: A Literature Review.

M2「類似概念境界混同型」の根拠として使用。

### Surface feature / keyword reaction

- Chi, M. T., Feltovich, P. J., & Glaser, R. (1981). Categorization and representation of physics problems by experts and novices. Cognitive Science, 5(2), 121-152.

M3「表層特徴・キーワード反応型」の根拠として使用。

### Transfer

- Bransford, J. D., & Schwartz, D. L. (1999). Rethinking Transfer: A Simple Proposal With Multiple Implications. Review of Research in Education, 24(1), 61-100.
- 白水始. (2012). 認知科学と学習科学における知識の転移. 人工知能, 27(4), 347-358.

M4「文脈転移失敗型」と転移テストの根拠として使用。

### AI tutoring / scaffolding / learning analytics

- VanLehn, K. (2011). The Relative Effectiveness of Human Tutoring, Intelligent Tutoring Systems, and Other Tutoring Systems.
- SoLAR (2025). What is Learning Analytics? Society for Learning Analytics Research.
- Kestin, G. et al. (2025). AI tutoring outperforms in-class active learning. Scientific Reports.
- Zheng, L. et al. (2022). An exploratory study on fade-in versus fade-out scaffolding.
- 加納政芳. (2013). 英単語学習システムにおける足場かけ使用による学習能力の変化.
- 和久友親, 田村哲嗣, & 川瀬真弓. (2024). 学習者の理解度に応じた自動問題生成AIシステムの開発.
- Puech, R., Macina, J., Chatain, J., Sachan, M., & Kapur, M. (2025). Towards the pedagogical steering of large language models for tutoring.

## Codex app-server Notes

このプロジェクトはOpenAI APIキーを使わない。Codex app-server経由でユーザーのChatGPT/Codexログインを使う。ただしapp-serverは仕様変更可能性があるため、`AIBackend` として隔離する。

ローカルCLI確認:

- `codex app-server --listen ws://127.0.0.1:4500`
- `--ws-auth capability-token`
- `--ws-token-file`
- `generate-json-schema --experimental --out <dir>`
- v2 schemaに `thread/start`, `turn/start`, `account/read`, `account/login/start`, `account/login/cancel`
- `turn/start` に `outputSchema`

実装時はその時点のschemaを再生成して確認する。

## Design Assumptions

- MVPは参加者単位の群間比較を基本にする
- 参加者数が少ない場合、用語単位の被験者内比較へ拡張可能にする
- 学習対象用語は最大4件
- 事前テストは過学習、汎化、Attention、Embeddingの4語、学習とL0確認は重点用語を基本にする
- 遅延再テストは任意拡張
- MockAIBackendを必ず先に完成させる

## Known Deck Inconsistencies and Resolution

5月25日PPTXの一部ノートには、旧分類番号らしきM2/M3/M7表記が残っていた。最終スライド本文ではM1〜M4が採用されているため、仕様ではM1〜M4へ統一した。

5月18日PPTXではH0の表記があったが、仕様では足場掛けなしをL0として統一した。

## Implementation Non-goals

- 汎用チャットボットの作成
- OpenAI APIキー利用
- インターネット公開
- 個人情報収集
- 全AI用語を網羅する教材サイト化
- 統計分析ソフト内蔵の本格実装
