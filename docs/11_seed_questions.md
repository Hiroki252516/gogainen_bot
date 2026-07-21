# Seed Questions

今回のMVP対象用語は `transformer` のみである。`pretest`、`retest`、`final_test`、学習セッション内確認問題は同じ問題文・選択肢セットを使う。

## Transformer

問題文: Transformerについて、適切だと思うものをすべて選びなさい。

選択形式: A〜Iの9択から3つ選択、またはJ「わからない」単独選択。選択肢順は固定し、A〜Jを意味のある判定ラベルとして扱う。

- A. Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換する構造である。 (正解)
- B. Attentionは、入力中の各トークンが他のトークンとどのように関係するかを重みづけして扱う仕組みである。 (正解)
- C. FFNは、Attentionの結果を受け取り、各トークンの表現を変換する層である。 (正解)
- D. Transformerは、Attentionレイヤーで文章全体の意味を理解し、FFNレイヤーで考えたり判断したりする構造である。 (M1)
- E. Attentionレイヤーは、文章全体の意味を理解する部分である。 (M1)
- F. FFNレイヤーは、Attentionの結果を受け取り、モデルが内部で考えたり判断したりする部分である。 (M1)
- G. Transformerは、Attentionレイヤーで文章中の重要語を探し、FFNレイヤーで文章を翻訳や生成に変換する機能である。 (M3)
- H. Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換するアプリである。 (M3)
- I. Transformerは、Attentionレイヤーで文章中の重要語を探し、FFNレイヤーで思考・判断を行う知能である。 (M3)
- J. わからない。 (unknown)

採点はA〜IからA/B/Cの3つだけを選択した場合に完全正解とする。それ以外は不正解である。
