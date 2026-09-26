from __future__ import annotations

from copy import deepcopy
from typing import Any


TAXONOMY_VERSION = "m1-m3-unknown-v1"


MISCONCEPTION_TAXONOMY: dict[str, Any] = {
    "M1": {
        "label": "誤信念型",
        "definition": "対象概念について、単一の命題や考えを誤って信じている状態。",
        "diagnostic_cues": ["一つの誤った説明文で表現できる", "他の説明構造を変えなくても局所的に修正できる"],
        "teaching_guidelines": ["誤った信念を明示する", "反証または反対事例と正しい説明を対比する", "修正後の信念を短く再説明させる"],
        "avoid": ["誤りを曖昧にしたまま情報を追加する", "学習者を責める", "内部ラベルを学習者に見せる"],
        "learning_outcome": "belief_revision",
        "research_basis": "Chi (2009), belief revision",
    },
    "M2": {
        "label": "欠陥メンタルモデル型",
        "definition": "複数の信念が因果関係や説明モデルとしてつながっているが、そのモデル全体または中核前提が誤っている状態。",
        "diagnostic_cues": ["複数の説明が一つの誤った仕組みとして連鎖する", "一つの事実訂正だけでは説明全体が変わらない"],
        "teaching_guidelines": ["モデルを構成する信念と関係を分解する", "中核前提を複数の反証で修正する", "正しい仕組みを図式または因果の順序で再構成させる"],
        "avoid": ["一つの用語の定義だけで解決したとみなす", "表面的な言い換えだけで終える", "誤った因果関係を温存する"],
        "learning_outcome": "mental_model_transformation",
        "research_basis": "Chi (2009), mental model transformation",
    },
    "M3": {
        "label": "カテゴリー誤り型",
        "definition": "対象概念を、本来属する上位カテゴリーとは異なる種類のものとして捉えている状態。",
        "diagnostic_cues": ["対象を別の種類・存在論的カテゴリーとして説明する", "細部を追加しても説明の土台がずれ続ける"],
        "teaching_guidelines": ["誤ったカテゴリーへの分類を明示する", "正しいカテゴリーの特徴と境界を示す", "複数の対比例で正しいカテゴリーへ再分類させる"],
        "avoid": ["誤カテゴリーのまま細部だけを補足する", "表層的なキーワード一致で理解したとみなす", "カテゴリー移行前に専門用語を増やしすぎる"],
        "learning_outcome": "categorical_shift",
        "research_basis": "Chi (2009), categorical shift",
    },
    "M4": {
        "label": "欠如したスキーマ型",
        "definition": "正しい分類先や関係を判断するために必要な知識構造・スキーマが不足している状態。",
        "diagnostic_cues": ["誤った信念やカテゴリーを積極的に主張するより、判断に必要な枠組みが欠けている", "新しい事例の関係を説明できない"],
        "teaching_guidelines": ["不足しているカテゴリー・関係・手順を特定する", "具体例から新しいスキーマを段階的に構築する", "新しいスキーマを別事例へ適用させる"],
        "avoid": ["知識不足を誤信念として反証する", "一度に大量の用語を提示する", "新しいスキーマの適用確認を省く"],
        "learning_outcome": "schema_formation",
        "research_basis": "Chi (2013), missing schema subtype",
    },
    "unknown": {
        "label": "知識不足",
        "definition": "誤った信念やカテゴリーを特定できる根拠がなく、対象概念の基礎知識が不足している状態。",
        "diagnostic_cues": ["わからないを単独選択する", "具体的な誤った説明が確認できない"],
        "teaching_guidelines": ["短い定義から始める", "構成要素と最小限の判断基準を示す", "簡単な例で理解を確認する"],
        "avoid": ["誤概念があると断定する", "反証を先に提示する", "学習者へ内部分類を示す"],
        "learning_outcome": "foundational_explanation",
        "research_basis": "operational knowledge-gap category for this study",
    },
}


def taxonomy_for_prompt() -> dict[str, Any]:
    return deepcopy(MISCONCEPTION_TAXONOMY)
