from __future__ import annotations

from copy import deepcopy
from typing import Any


TAXONOMY_VERSION = "m1-m3-unknown-v2"


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
    "M3": {
        "label": "カテゴリー誤り型",
        "definition": "対象概念を、本来属する上位カテゴリーとは異なる種類のものとして捉えている状態。",
        "diagnostic_cues": ["対象を別の種類・存在論的カテゴリーとして説明する", "細部を追加しても説明の土台がずれ続ける"],
        "teaching_guidelines": ["誤ったカテゴリーへの分類を明示する", "正しいカテゴリーの特徴と境界を示す", "複数の対比例で正しいカテゴリーへ再分類させる"],
        "avoid": ["誤カテゴリーのまま細部だけを補足する", "表層的なキーワード一致で理解したとみなす", "カテゴリー移行前に専門用語を増やしすぎる"],
        "learning_outcome": "categorical_shift",
        "research_basis": "Chi (2009), categorical shift",
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
