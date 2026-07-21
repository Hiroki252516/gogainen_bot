# AI Prompt Contracts

今回のMVPでは、AIに渡す内部分類は M1、M3、unknown、null を主導線とする。M2/M4は互換値としてDBに残っても、新規判定・教材方略では使わない。

- M1: 誤信念型。Transformerや各層を人間の意味理解・思考・判断として捉える誤り。
- M3: カテゴリー錯誤型。Transformerをモデルアーキテクチャではなく、アプリ、機能、知能主体として捉える誤り。
- unknown: 知識不足。

学習ステージは `enrichment`、`conceptual_change`、`final_feedback` を使う。unknownは豊富化、M1/M3は概念変化に進める。

統制群では `teaching_strategy = general_explanation` に固定し、M1/M3別の個別支援はしない。提案群ではM3を最優先し、次にM1、最後に正解/unknownを扱う。M3ならカテゴリー認識の修正、M1なら誤信念修正、unknownなら基礎知識の豊富化を優先する。

被験者に見える文面には内部ラベルを直接書かない。
