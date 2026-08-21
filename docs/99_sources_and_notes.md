# 99. Sources and Notes

## Uploaded Research Decks

この仕様リポジトリは、以下のPPTXから抽出した研究計画をもとに整備した。

- `/Users/hiroki/Downloads/5月18日(テーマ変更) (2) 2.pptx`
- `/Users/hiroki/Downloads/5月25日進捗報告.pptx`

## Research Plan Summary

研究の中心は、AIチューターを作ること自体ではない。中心は、AI・情報系専門用語の誤概念を学習ログから追跡し、同じ誤概念の再発抑制と足場掛けなし転移を評価することである。

比較対象は「AIを使うかどうか」ではなく、以下である。

- 統制群: 一般的なAI解説
- 提案群: 学習ログ、誤概念タイプ、学習ステージに基づいて支援を変えるAIチューター

## Key Decisions from Decks

### Final taxonomy

5月18日案ではM1〜M6の誤概念分類が提示されていた。5月25日案では、先行研究に基づく独自の分析枠組みとしてM1〜M4へ整理された。

2026-08-21更新後のMVPでは、M1〜M4を次の知識構造上の粒度として扱う。固定問題の選択肢はM1/M3/unknownを診断対象とし、M2/M4はAI内部taxonomyと将来の問題設計のために保持する。

| Final | Name |
|---|---|
| M1 | 誤信念型 |
| M2 | 欠陥メンタルモデル型 |
| M3 | カテゴリー錯誤型 |
| M4 | 欠如したスキーマ型 |
| unknown | 知識不足 |

### Problem phase separation

5月25日案では、問題タイプとフェーズの対応が明示されていた。現行仕様では問題本文と選択肢をYAMLで固定し、variant_keyで再利用規則を追跡する。

| フェーズ | 使う問題 |
|---|---|
| 事前テスト | 定義問題・識別問題 |
| 学習セッション | 用語理解・概念理解の固定確認問題 |
| 即時再テスト | 各用語4バリエーション。5回目以降はv4を再利用 |
| 最終テスト | 各用語1問。理由・ヒント・即時正解表示なし |

このため、実装では `construct_key` と `variant_key` を持たせる。現行MVPでは `backend/app/seed/content/learning_content.yml` を唯一の固定問題バンクとし、事前・最終テストは各用語1問、再テストはv1〜v4、学習確認は各学習段階・各用語v1〜v5で管理する。上限を超えた場合は最後のバリアントを再利用する。

### Main metrics

PPTXで繰り返し示されていた主評価指標は以下。

- 同種誤答再発率
- 足場掛けなし自力解答率

これらは `docs/12_evaluation_metrics.md` に定義した。

## References in Decks

### Conceptual change / category shift

- Chi, M. T. (2009). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift.
- Chi, M. T. H. (2008). Three types of conceptual change: Belief revision, mental model transformation, and categorical shift.

M1の単一信念の修正、M2のメンタルモデルの再構成、M3のカテゴリー再分類という粒度の根拠として使用する。固定問題でM3を優先判定するのは、カテゴリーの取り違えが他の局所的な誤りより上位の説明枠を壊すためである。

- Chi, M. T. (2013). Two kinds and four sub-types of misconceived knowledge, ways to change it, and the learning outcomes. In *International Handbook of Research on Conceptual Change* (pp. 49-70). Routledge.

M4「欠如したスキーマ型」の根拠として使用する。不正確な知識の修正だけでなく、学習者に不足しているカテゴリーや関係を新たに構築する必要がある場合を区別する。

### Similar concept boundary confusion

- Hassani, H., Ghodsi, M., & Howell, G. (2010). A note on standard deviation and standard error. Teaching Mathematics and its Applications, 29(2), 108-112.
- Qian, Y., & Lehman, J. (2017). Students' Misconceptions and Other Difficulties in Introductory Programming: A Literature Review.

Hassaniらの研究はM2全体を定義する根拠ではなく、標準偏差と標準誤差のような近接概念の境界混同を説明する補助例として扱う。M2の本質的定義はChiのメンタルモデルの議論に置く。

### Surface feature / keyword reaction

- Chi, M. T., Feltovich, P. J., & Glaser, R. (1981). Categorization and representation of physics problems by experts and novices. Cognitive Science, 5(2), 121-152.

初心者が表層特徴に基づいて問題を表象し、専門家が原理・構造に基づいて表象する差を、M3の診断問題と教材設計の補助根拠として使う。特定用語のM1〜M4定義そのものではない。

### Transfer

- Bransford, J. D., & Schwartz, D. L. (1999). Rethinking Transfer: A Simple Proposal With Multiple Implications. Review of Research in Education, 24(1), 61-100.
- 白水始. (2012). 認知科学と学習科学における知識の転移. 人工知能, 27(4), 347-358.

転移研究は、M4で構築したスキーマやM3で再配置したカテゴリーが新しい文脈でも使えるかを評価する補助根拠として使う。

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
- 現行MVPの学習対象は、`llm_knowledge`、`multi_agent`、`memory_process` の3件
- 診断後、正解済み用語は学習対象から除外し、未達用語だけを学習する
- 再テストは毎回、事前テスト対象の3件を出題する。
- 事前テスト、学習、再テスト、最終テストはYAMLで定義した3項目を基本にする
- Transformer、Attention、事前学習、事後学習など旧用語は過去ログ・DB互換用として非アクティブ化する
- RAGは `rag_agent_knowledge_base/` の用語別セクションを共通参照し、LangGraph関連チャンクは除外する
- 遅延再テストは任意拡張
- MockAIBackendをテスト・切り分け用に維持する

## Known Deck Inconsistencies and Resolution

7月22日PPTXと8月21日更新仕様を受け、古いTransformer固有のM1/M3判定は新規フローから外し、3項目共通のA〜C正解、D〜F=M1、G〜I=M3、J=unknownのYAML判定へ統一した。M2/M4は実行時taxonomyに保持する。

5月18日PPTXではH0の表記があったが、現在の実装では固定3ターンの足場掛け制ではなく、用語理解段階と概念理解段階のステージ制に統一する。L1/L2/L3相当の値は互換ログ用に残す。

## Implementation Non-goals

- 汎用チャットボットの作成
- OpenAI APIキー利用
- インターネット公開
- 個人情報収集
- 全AI用語を網羅する教材サイト化
- 統計分析ソフト内蔵の本格実装
