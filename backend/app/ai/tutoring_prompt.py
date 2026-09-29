from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.ai.mandatory_elements import (
    mandatory_element_headings,
    mandatory_element_requirements,
)


def mandatory_element_prompt(misconception_type: str | None) -> str:
    """Render the type-specific teaching instruction for教材生成."""
    requirements = mandatory_element_requirements(misconception_type)
    headings = mandatory_element_headings(misconception_type)
    if not requirements:
        return ""
    lines = [
        f"現在の必須教授要素タイプは {misconception_type}。次の見出しをこの順序で教材本文に使う:",
    ]
    lines.extend(
        f"- {field} / ### {headings[field]}: {description}"
        for field, description in requirements.items()
    )
    lines.append("## 用語名の直後に、上記の ### 見出しを順番どおりに置く。")
    lines.append("M1/M3/unknownでは「### 要点」「### 具体例」「### 注意点」を使わない。")
    lines.append("mandatory_elements は type と上記フィールドを直下に持つオブジェクトにし、不要なフィールドや入れ子を追加しない。")
    lines.append("mandatory_elements の各値は、教材本文からそのまま抜き出した短い証拠文にする。")
    lines.append("各証拠文は、対応する見出しのセクション内に置く。")
    lines.append("mandatory_elements は研究ログ用であり、学習者向け本文に内部ラベルを表示しない。")
    return "\n".join(lines)
from app.ai.teaching_contract import (
    MATERIAL_MAX_CHARACTERS,
    MATERIAL_MIN_CHARACTERS,
    MATERIAL_TARGET_CHARACTERS,
)


def compose_structured_prompt(
    purpose: str,
    payload: dict[str, Any],
    rules: Sequence[str],
) -> str:
    """Compose the common text envelope used for structured app-server calls."""
    prompt_parts = [
        f"目的: {purpose}",
        "",
        "出力は指定JSON Schemaに一致するJSONオブジェクトのみ。Markdown、説明文、コードブロックは禁止。",
        "個人情報、APIキー、アクセストークン、認証情報を要求・保存・推測しない。",
        "被験者に見える文面では内部研究ラベル M1/M2/M3/M4 を使わない。",
        "",
        "追加ルール:",
        *[f"- {rule}" for rule in rules],
    ]
    if payload.get("misconception_taxonomy"):
        prompt_parts.extend(
            [
                "",
                "内部taxonomy。診断と教授方略の判断にだけ使い、学習者向け出力へ転載しない:",
                json.dumps(payload["misconception_taxonomy"], ensure_ascii=False, indent=2),
            ]
        )
    prompt_payload = remove_routing_metadata(payload)
    prompt_parts.extend(["", "入力JSON:", json.dumps(prompt_payload, ensure_ascii=False, indent=2)])
    return "\n".join(prompt_parts)


def build_tutoring_prompt(
    payload: dict[str, Any],
    *,
    retry_context: dict[str, Any] | None = None,
    group: str,
    expected_type: str | None,
    term_label: str,
    teaching_strategies: Sequence[str],
) -> str:
    """Build the complete教材生成 prompt in one auditable place.

    The input payload has already been allowlisted by the caller.  This builder
    owns only the textual instruction order; output schemas and local
    validation remain separate contracts.
    """
    rules = [
        "学習セッション用の正確で読みやすい日本語教材を安全なMarkdownで作る。",
        f"教材の主題は現在の用語『{term_label}』とし、入力された用語説明を中心にする。",
        "入力JSONの term.description を教材の中心内容として使う。別用語の例題や固定例を主題にしない。",
        "rag_context.chunks がある場合は同じ用語の教材コンテキストを参照し、根拠のない断定を避ける。",
        "tutor_message には現在の用語の教材だけを書く。問題文、選択肢、正答、過去の回答やフィードバックは含めない。",
        "学習確認問題はbackendの固定問題バンクが表示・採点するため、問題や選択肢を生成しない。",
        "教材には定義、仕組みまたは役割、具体例、注意点を含める。一般的な誤解を正確に説明・訂正してよい。",
        f"教材本文はMarkdown記号を含めて{MATERIAL_TARGET_CHARACTERS}文字前後（{MATERIAL_MIN_CHARACTERS}〜{MATERIAL_MAX_CHARACTERS}文字）に統一する。定義、仕組み、具体例、注意点を保ち、不要な繰り返しで水増ししない。",
        "見出し、箇条書き、太字、短い段落を使う。表、HTML、コードブロック、画像、長大な連続段落は使わない。",
        "被験者ID、群名、内部識別子、M1〜M4などの内部ラベルを学習者向け本文に書かない。",
    ]

    # ``retry_context`` is server-side generation metadata.  It may contribute
    # a length-adjustment instruction, but it must never become model input.
    retry_source = retry_context or payload
    material_length_retry = retry_source.get("material_length_retry")
    if isinstance(material_length_retry, dict):
        actual_character_count = material_length_retry.get("actual_character_count")
        if isinstance(actual_character_count, int) and not isinstance(actual_character_count, bool):
            rules.append(
                f"前回の教材本文は{actual_character_count}文字で許容範囲外だった。今回は前回の内容を冗長に繰り返さず、Markdown記号を含めて{MATERIAL_TARGET_CHARACTERS}文字前後（{MATERIAL_MIN_CHARACTERS}〜{MATERIAL_MAX_CHARACTERS}文字）に必ず収める。"
            )
        else:
            rules.append(
                f"前回の教材本文が文字数の許容範囲外だった。今回はMarkdown記号を含めて{MATERIAL_TARGET_CHARACTERS}文字前後（{MATERIAL_MIN_CHARACTERS}〜{MATERIAL_MAX_CHARACTERS}文字）に必ず収める。"
            )

    if expected_type:
        headings = mandatory_element_headings(expected_type)
        heading_order = "、".join(f"### {heading}" for heading in headings.values())
        rules.extend(
            [
                f"tutor_message は必ず『## {term_label}』の後に {heading_order} の順で構成する。",
                "M1/M3/unknownでは『### 要点』『### 具体例』『### 注意点』を使わず、タイプ別の見出しを教材構造そのものにする。",
                "各タイプ別セクションには対応する必須教授要素を置き、他のタイプの必須要素や不要なセクションを追加しない。",
                "teaching_contractやmandatory_elementsのフィールド名（mechanism_explanation、transfer_check、definitionなど）をtutor_message本文に書かない。",
            ]
        )
        if expected_type in {"M1", "M3"}:
            rules.extend(
                [
                    "teaching_contractを必ず返し、現在のタイプに一致するpretest_targetsがある場合は、そのclaim_idだけをaddressed_claim_idsへ入れる。target_claim_idは主対象のclaim_idにする。",
                    "現在のタイプに一致するpretest_targetsがない場合は、target_claim_idをnull、addressed_claim_idsを空配列にし、研究者確認済みでない具体的な誤答主張を創作しない。",
                    "teaching_contractのcorrected_claim、mechanism_explanation、contrast_example、transfer_checkは、tutor_message本文にそのまま含める。",
                    "teaching_contractのtarget_addressedはtrueにする。M1のrefutation_modeはexplicitを標準とし、M3はcategory_comparisonにする。",
                ]
            )
        else:
            rules.extend(
                [
                    "unknownのteaching_contractはtarget_claim_idをnull、addressed_claim_idsを空配列、corrected_claimとcontrast_exampleをnullにする。",
                    "unknownでは反駁対象を創作せず、mechanism_explanationとtransfer_checkだけを教材本文に含め、refutation_modeはnoneにする。",
                    "teaching_contractのtarget_addressedはtrueにする。",
                ]
            )
    else:
        rules.extend(
            [
                "tutor_message は必ず『## 用語名』『### 要点』『### 具体例』『### 注意点』の順に構成する。",
                "各セクションは内容に応じた簡潔な箇条書き、または短い段落で書く。重要語は **太字** にしてよい。",
                "内容上必要な場合だけ『### 前提用語とのつながり』『### 何ではないか』を追加する。",
            ]
        )

    if expected_type:
        rules.append(mandatory_element_prompt(expected_type))
    if payload.get("mandatory_element_retry"):
        rules.append(
            "前回生成で必須教授要素またはteaching_contractが不足した。入力JSONの mandatory_element_retry.missing にある項目をすべて補い、契約フィールドの証拠文を教材本文へそのまま含める。"
        )

    if group == "control":
        rules.append("通常のAIチューターとして、入力された共通の用語情報と教材コンテキストだけから一般向けの説明を作る。個人の回答・診断・履歴・学習段階を推測したり前提にしたりしない。")
        rules.append("teaching_strategy は general_explanation に固定する。")
    else:
        rules.append("入力された事前診断、誤答対象、学習履歴を教授方略の選択に利用する。")
        rules.append("入力payloadのmisconception_taxonomyにあるM1〜M4の定義と教授方略を厳守する。M3ならカテゴリー再分類、M2なら説明モデルの再構成、M1なら誤信念の反証、M4なら不足スキーマの構築、unknownなら基礎知識の豊富化を優先する。")
        rules.append("diagnostic_evidence.selected_options がある場合、M1の誤った考えまたはM3の誤カテゴリーは選択肢本文に根拠を置き、学習者が示していない誤概念を創作しない。unknownでは誤った考えを推測しない。")
        rules.append("pretest_targetまたはpretest_targetsがある場合、それを今回の教授目標として優先する。観察された選択を確定した信念とは断定せず、選択された説明として扱う。")
        rules.append("M1は対象がある場合はその誤った命題を、対象がない場合は一般的な誤りの型を、正しい命題、誤りの仕組み、対比例、別事例への適用確認とともに明示する。M3も対象がある場合はその誤カテゴリーを、対象がない場合は一般的なカテゴリー境界を、正カテゴリー、境界、対比例、別事例への適用確認とともに明示する。unknownは反駁せず、定義・構成要素・役割・正例・非例と適用確認を示す。")
        rules.append("unknownはenrichment、M1/M3はconceptual_changeとして教材を提示し、固定3選択問題はbackendが表示する。")
    rules.append(f"teaching_strategy は次の識別子だけから選ぶ: {', '.join(teaching_strategies)}。")

    return compose_structured_prompt("tutoring_turn", payload, rules)


def remove_routing_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: remove_routing_metadata(item)
            for key, item in value.items()
            if key not in {"participant_id", "group_condition", "participant_code"}
        }
    if isinstance(value, list):
        return [remove_routing_metadata(item) for item in value]
    return value
