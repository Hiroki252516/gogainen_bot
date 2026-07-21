TRANSFORMER_QUESTION = {
    "body": "Transformerについて、適切だと思うものをすべて選びなさい。",
    "expected": "A、B、Cをすべて選択し、それ以外を選ばない。",
    "options": [
        (
            "A",
            "Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換する構造である。",
            True,
            None,
        ),
        (
            "B",
            "Attentionは、入力中の各トークンが他のトークンとどのように関係するかを重みづけして扱う仕組みである。",
            True,
            None,
        ),
        (
            "C",
            "FFNは、Attentionの結果を受け取り、各トークンの表現を変換する層である。",
            True,
            None,
        ),
        (
            "D",
            "Transformerは、Attentionレイヤーで文章全体の意味を理解し、FFNレイヤーで考えたり判断したりする構造である。",
            False,
            "M1",
        ),
        ("E", "Attentionレイヤーは、文章全体の意味を理解する部分である。", False, "M1"),
        (
            "F",
            "FFNレイヤーは、Attentionの結果を受け取り、モデルが内部で考えたり判断したりする部分である。",
            False,
            "M1",
        ),
        (
            "G",
            "Transformerは、Attentionレイヤーで文章中の重要語を探し、FFNレイヤーで文章を翻訳や生成に変換する機能である。",
            False,
            "M3",
        ),
        (
            "H",
            "Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換するアプリである。",
            False,
            "M3",
        ),
        (
            "I",
            "Transformerは、Attentionレイヤーで文章中の重要語を探し、FFNレイヤーで思考・判断を行う知能である。",
            False,
            "M3",
        ),
        ("J", "わからない。", False, "unknown"),
    ],
}


SEED_TERMS = [
    {
        "slug": "transformer",
        "label": "Transformer",
        "description": "Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換するモデルアーキテクチャである。",
        "keywords": ["Transformer", "Attention", "FFN", "トークン間の関係性", "特徴を変換"],
        "questions": {
            "pretest": TRANSFORMER_QUESTION,
            "retest": TRANSFORMER_QUESTION,
            "l0": "Transformerの構造を、Attentionレイヤー、FFNレイヤー、トークン間の関係性に触れて説明してください。",
            "final_test": TRANSFORMER_QUESTION,
            "transfer": "長い文章の要約で、離れた語同士の関係を扱いながら各トークンの特徴を変換できる理由を、Transformerの構造から説明してください。",
        },
    },
]
