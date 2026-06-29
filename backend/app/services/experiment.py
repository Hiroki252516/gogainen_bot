from __future__ import annotations

import csv
import json
import random
import re
from datetime import UTC, datetime
from time import perf_counter
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerError
from app.ai.backend import lower_level, normalize_level, raise_level, strategy_for
from app.ai.factory import get_ai_backend
from app.core.config import get_settings
from app.rag.retriever import retrieve_rag_context
from app.models import (
    AICallLog,
    Attempt,
    EvaluationSummary,
    ExportJob,
    LearnerState,
    Participant,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
    RecurrenceEvent,
    Term,
    TermAssignment,
    TutorSession,
    TutorTurn,
    now,
)


PUBLIC_LEVEL = {"L3": "用語理解から確認", "L2": "概念理解を確認"}
PRETEST_TERM_ORDER = {"llm_training_process": 0, "transformer": 1}
PRETEST_TERM_SLUGS = set(PRETEST_TERM_ORDER)
LEARNING_STAGE_LABELS = {
    "term_understanding": "用語理解",
    "concept_understanding": "概念理解",
    "final_feedback": "教材フィードバック",
}
TEST_PHASES = {"pretest", "retest", "final_test"}
COMPONENT_TERMS = {
    "llm_training_process": ["事前学習", "インストラクションチューニング", "事後学習"],
    "transformer": ["Attentionレイヤー", "FFNレイヤー", "トークン間の関係性"],
}

LEARNING_CHOICE_BANK = {
    "llm_training_process": {
        "事前学習": {
            "material": "今回はLLMの学習段階を理解するための構成用語として、事前学習を確認します。事前学習とは、大量のテキストなどから言語パターンや知識の基盤を学び、後続の調整の土台となる能力を獲得する段階です。インストラクションチューニングや事後学習とは目的が異なります。",
            "body": "LLMにおける事前学習の説明として、最も適切なものはどれか。",
            "expected_answer": "大量のテキストなどから言語パターンや知識の基盤を学び、後続の調整の土台となる能力を獲得する段階。",
            "question_type": "component_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "大量のテキストなどから言語パターンや知識の基盤を学び、後続の調整の土台となる能力を獲得する段階。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "大量の文章を読んで意味を理解し、モデルの内部で人間のような知識や意図を形成する段階。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "指示と望ましい応答の例を使い、ユーザーの命令に沿った回答をしやすくする調整段階。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "モデルを使う前に、プロンプトや条件をあらかじめ設定して回答の方向性を決める段階。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
        "インストラクションチューニング": {
            "material": "今回はLLMの学習段階を理解するための構成用語として、インストラクションチューニングを確認します。インストラクションチューニングとは、指示と望ましい応答の例を使い、LLMがユーザーの指示に沿った回答をしやすくする調整段階です。事前学習で作った基盤能力を、指示応答に使いやすくします。",
            "body": "インストラクションチューニングの説明として、最も適切なものはどれか。",
            "expected_answer": "指示と望ましい応答の例を使い、LLMがユーザーの指示に沿った回答をしやすくする調整段階。",
            "question_type": "component_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "指示と望ましい応答の例を使い、LLMがユーザーの指示に沿った回答をしやすくする調整段階。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "ユーザーの指示文を読んで意図を理解し、内部で考えた内容を会話として表現する段階。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "大量の未ラベルテキストから、言語パターンや知識の基盤を最初に獲得する段階。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "temperatureや最大トークン数などを設定し、出力の長さやランダム性を調整すること。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
        "事後学習": {
            "material": "今回はLLMの学習段階を理解するための構成用語として、事後学習を確認します。事後学習とは、人間評価や報酬モデルなどを使い、出力をより安全で有用なものに近づける調整段階です。回答後の反省や単なる評価テストではありません。",
            "body": "LLMにおける事後学習の説明として、最も適切なものはどれか。",
            "expected_answer": "人間評価や報酬モデルなどを使い、出力をより安全で有用なものに近づける調整段階。",
            "question_type": "component_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "人間評価や報酬モデルなどを使い、出力をより安全で有用なものに近づける調整段階。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "モデルが回答後に自分の出力を振り返り、次回の会話で同じ失敗を避けるように反省する段階。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "指示と望ましい応答の例を使い、ユーザーの命令に沿った回答をしやすくする調整段階。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "学習が終わった後に、性能を測るテストやアンケートを実施して結果を比較する段階。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
        "__concept__": {
            "material": "LLMの主な学習プロセスは、事前学習、インストラクションチューニング、事後学習に分けて考えます。事前学習で言語パターンを学び、インストラクションチューニングで指示に従う応答へ調整し、事後学習で出力の望ましさを高めます。",
            "body": "対象範囲で説明されているLLMの主な学習プロセスの組み合わせとして、最も適切なものはどれか。",
            "expected_answer": "大量のテキストで言語パターンを学ぶ事前学習、指示に従う応答へ調整するインストラクションチューニング、出力の望ましさを高める事後学習。",
            "question_type": "concept_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "大量のテキストで言語パターンを学ぶ事前学習、指示に従う応答へ調整するインストラクションチューニング、出力の望ましさを高める事後学習。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "入力された文章を理解する事前学習、内部で思考するインストラクションチューニング、必要に応じて意図を形成してから会話として出力する事後学習。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "ユーザーがプロンプトを入力する事前学習、コンテキストウィンドウに情報を保持するインストラクションチューニング、必要に応じてFunction Callingで外部処理を行う事後学習。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "学習前の性能を測定する事前学習、学習後の性能をテストするインストラクションチューニング、前後比較を行う評価手順である事後学習。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
    },
    "transformer": {
        "Attentionレイヤー": {
            "material": "今回はTransformerを理解するための構成用語として、Attentionレイヤーを確認します。Attentionレイヤーは、入力中の各トークンが他のトークンとどの程度関係するかを重み付けし、文脈上参照すべき情報を扱う仕組みです。文章全体を人間のように意識して判断する仕組みではありません。",
            "body": "TransformerにおけるAttentionレイヤーの説明として、最も適切なものはどれか。",
            "expected_answer": "入力中の各トークンが他のトークンとどの程度関係するかを重み付けし、文脈上参照すべき情報を扱う仕組み。",
            "question_type": "component_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "入力中の各トークンが他のトークンとどの程度関係するかを重み付けし、文脈上参照すべき情報を扱う仕組み。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "文章全体の意味を理解し、重要な内容に意識を向けて判断する仕組み。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "各トークンの表現を個別に変換し、Attention後の特徴を加工する層。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "重要そうな単語を検索し、その単語を正しい意味や正しい語に置き換える仕組み。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
        "FFNレイヤー": {
            "material": "今回はTransformerを理解するための構成用語として、FFNレイヤーを確認します。FFNレイヤーは、Attention後の各トークン表現を個別に変換し、特徴を加工する層です。トークン同士の関係性を計算するAttentionとは役割が異なります。",
            "body": "TransformerにおけるFFNレイヤーの説明として、最も適切なものはどれか。",
            "expected_answer": "Attention後の各トークン表現を個別に変換し、特徴を加工する層。",
            "question_type": "component_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "Attention後の各トークン表現を個別に変換し、特徴を加工する層。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "Attentionで得た文章全体の意味をもとに、モデルが内部で思考して最終判断を行う層。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "各トークンが他のトークンとどの程度関係するかを計算し、参照すべき情報を重み付けする層。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "入力文を前から後ろへ流し、正しい語順や正しい単語になるように並べ替える層。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
        "トークン間の関係性": {
            "material": "今回はTransformerを理解するための構成用語として、トークン間の関係性を確認します。トークン間の関係性とは、文中の各トークンが他のトークンとどの程度関連しているかを表す情報です。Transformerはこの関係性をAttentionで扱います。",
            "body": "Transformerで扱うトークン間の関係性の説明として、最も適切なものはどれか。",
            "expected_answer": "文中の各トークンが、他のトークンとどの程度関連しているかを表す情報。",
            "question_type": "component_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "文中の各トークンが、他のトークンとどの程度関連しているかを表す情報。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "文章全体を読んだときに人間が感じ取る意味、意図、文脈のまとまり。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "各トークンの表現を個別に変換し、特徴量を加工する処理。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "文中で近くにある単語だけを順番に結びつけ、前の単語から次の単語へ意味を渡すこと。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
        "__concept__": {
            "material": "Transformerは、Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換する構造です。RNNのように前から順番に隠れ状態だけを渡す構造とは異なります。",
            "body": "Transformerの構造の説明として、最も適切なものはどれか。",
            "expected_answer": "Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換する構造。",
            "question_type": "concept_choice",
            "options": [
                {"option_id": "A", "label": "A", "body": "Attentionレイヤーでトークン間の関係性を扱い、FFNレイヤーで各トークンの特徴を変換する構造。", "is_correct": True, "misconception_type": None},
                {"option_id": "B", "label": "B", "body": "Attentionレイヤーが文章全体の意味を理解し、FFNレイヤーが思考して判断を行う構造。", "is_correct": False, "misconception_type": "M1"},
                {"option_id": "C", "label": "C", "body": "入力文を先頭から順番に処理し、前の単語の隠れ状態を次の単語へ渡しながら文脈を保持する構造。", "is_correct": False, "misconception_type": "M2"},
                {"option_id": "D", "label": "D", "body": "Attentionレイヤーで単語の意味を検索し、FFNレイヤーで正しい単語に置き換える構造。", "is_correct": False, "misconception_type": "M3"},
                {"option_id": "E", "label": "E", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"},
            ],
        },
    },
}


def _component_terms(term_slug: str, term_label: str) -> list[str]:
    return COMPONENT_TERMS.get(term_slug, [term_label])


def _learning_question_spec(term_slug: str, learning_stage: str, component_term: str | None) -> dict[str, Any]:
    bank = LEARNING_CHOICE_BANK.get(term_slug)
    if not bank:
        raise HTTPException(status_code=400, detail="fixed learning questions not found")
    key = component_term if learning_stage == "term_understanding" else "__concept__"
    spec = bank.get(key or "")
    if not spec:
        raise HTTPException(status_code=400, detail="fixed learning question not found")
    return spec


def _learning_question_item(term_slug: str, component_term: str) -> dict[str, Any]:
    spec = _learning_question_spec(term_slug, "term_understanding", component_term)
    return {
        "component_term": component_term,
        "material": spec["material"],
        "body": spec["body"],
        "expected_answer": spec["expected_answer"],
        "question_type": spec["question_type"],
        "options": _public_learning_options(spec),
    }


def _public_learning_options(spec: dict[str, Any]) -> list[dict[str, str]]:
    return [{"option_id": option["option_id"], "label": option["label"], "body": option["body"]} for option in spec["options"]]


def _learning_option_meta(spec: dict[str, Any], option_id: str | None) -> dict[str, Any] | None:
    if not option_id:
        return None
    return next((option for option in spec["options"] if option["option_id"] == option_id), None)


def _selected_fixed_option(spec: dict[str, Any], selected_option_id: str | None, response: str) -> dict[str, Any] | None:
    option = _learning_option_meta(spec, selected_option_id)
    if option:
        return option
    cleaned = (response or "").strip()
    if not cleaned:
        return None
    expected = spec.get("expected_answer") or ""
    if any(word in cleaned for word in expected.split("、") if word):
        return _learning_option_meta(spec, "A")
    markers = [
        word
        for word in ["事前学習", "インストラクション", "事後学習", "基盤", "指示", "応答", "安全", "有用", "Attention", "FFN", "トークン", "関係", "特徴", "変換"]
        if word in expected
    ]
    if markers and any(word in cleaned for word in markers):
        return _learning_option_meta(spec, "A")
    return next((item for item in spec["options"] if item["body"] == cleaned), None)


def _fixed_feedback(option: dict[str, Any] | None, spec: dict[str, Any]) -> dict[str, Any]:
    if not option:
        return {
            "feedback": "選択肢を選んでください。",
            "is_sufficient": False,
            "next_action": "continue",
            "next_scaffolding_level": "L3",
            "learning_misconception_type": "unknown",
            "learning_misconception_confidence": 0.8,
            "learning_misconception_reason": "固定選択式問題で未選択または判定不能でした。",
            "state_update_reason": "fixed_choice_unselected",
        }
    is_correct = bool(option["is_correct"])
    return {
        "feedback": "選択内容は十分です。次の確認へ進みます。" if is_correct else "選択内容はまだ不十分です。教材を確認して、もう一度同じ観点を選び直してください。",
        "is_sufficient": is_correct,
        "next_action": "move_next" if is_correct else "continue",
        "next_scaffolding_level": "L2" if is_correct else "L3",
        "learning_misconception_type": None if is_correct else option["misconception_type"],
        "learning_misconception_confidence": 0.95,
        "learning_misconception_reason": "固定選択式問題で正解選択肢を選びました。" if is_correct else f"固定選択式問題で{option['misconception_type']}相当の選択肢を選びました。",
        "state_update_reason": "fixed_choice_correct" if is_correct else "fixed_choice_incorrect",
    }


def _fixed_item_result(component_term: str, selected_option_id: str | None, response: str, spec: dict[str, Any]) -> dict[str, Any]:
    option = _selected_fixed_option(spec, selected_option_id, response)
    correct_option = next((item for item in spec["options"] if item["is_correct"]), None)
    is_correct = bool(option and option["is_correct"])
    misconception_type = None if is_correct else ((option or {}).get("misconception_type") or "unknown")
    return {
        "component_term": component_term,
        "question_body": spec["body"],
        "selected_option_id": option.get("option_id") if option else selected_option_id,
        "selected_option_body": option.get("body") if option else response,
        "correct_option_id": correct_option.get("option_id") if correct_option else None,
        "correct_answer": correct_option.get("body") if correct_option else spec.get("expected_answer"),
        "is_correct": is_correct,
        "is_sufficient": is_correct,
        "learning_misconception_type": misconception_type,
        "feedback": "正解です。要点を押さえられています。" if is_correct else "不正解です。正解文と教材を確認して、次の確認で選び直してください。",
    }


def _feedback_text_from_item_results(item_results: list[dict[str, Any]]) -> str:
    lines = ["回答結果"]
    for item in item_results:
        status = "正解" if item["is_correct"] else "不正解"
        lines.append(f"【{item['component_term']}】{status}")
        lines.append(f"あなたの回答: {item.get('selected_option_body') or '未選択'}")
        lines.append(f"正解: {item.get('correct_answer') or ''}")
        lines.append(f"フィードバック: {item['feedback']}")
    return "\n".join(lines)


def _previous_turn_prefix(previous_turn: TutorTurn | None) -> str:
    if not previous_turn:
        return ""
    parts = []
    previous_question = (previous_turn.practice_question_json or {}).get("body")
    if previous_question:
        parts.append(f"前の問題: {previous_question}")
    if previous_turn.learner_response:
        parts.append(f"あなたの回答: {previous_turn.learner_response}")
    if previous_turn.ai_feedback:
        parts.append(f"前の回答を踏まえて、{previous_turn.ai_feedback}")
    return "\n".join(parts) + ("\n\n" if parts else "")


def _practice_question_text(practice_question: dict[str, Any] | None) -> str:
    if not practice_question:
        return ""
    if practice_question.get("body"):
        return practice_question["body"]
    items = practice_question.get("items") or []
    return " / ".join(item.get("body", "") for item in items if item.get("body"))


def _misconception_scaffolding_guidance(misconception_type: str | None) -> str:
    return {
        "M1": "概念を人間の理解・思考など別カテゴリとして捉えないよう、専門用語としてのカテゴリと役割を捉え直させる。",
        "M2": "似ている概念との境界を比較し、どちらが何を扱うかを短く対比させる。",
        "M3": "語感や表面的なキーワードではなく、構造・役割・判断基準に注目させる。",
        "unknown": "基礎定義と構成要素を短く確認し、最小限の判断基準を示す。",
    }.get(misconception_type, "現在の構成用語の定義、役割、判断基準を短く整理する。")


def _practice_meta(turn: TutorTurn | None) -> dict[str, Any]:
    if not turn or not isinstance(turn.practice_question_json, dict):
        return {}
    return turn.practice_question_json.get("stage_meta") or {}


def _learning_position(db: Session, session: TutorSession, term: Term, participant: Participant) -> dict[str, Any]:
    components = _component_terms(term.slug, term.label)
    turns = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id)
        .order_by(TutorTurn.turn_index)
        .all()
    )
    if participant.group_condition == "control":
        for turn in turns:
            if turn.learner_response and bool((turn.grading_json or {}).get("is_sufficient")):
                return {
                    "learning_stage": "final_feedback",
                    "learning_stage_label": LEARNING_STAGE_LABELS["final_feedback"],
                    "component_term": None,
                    "component_index": 1,
                    "component_total": 1,
                }
        return {
            "learning_stage": "concept_understanding",
            "learning_stage_label": LEARNING_STAGE_LABELS["concept_understanding"],
            "component_term": None,
            "component_index": 1,
            "component_total": 1,
        }
    stage = "term_understanding"
    component_index = 0
    sufficient_components: set[str] = set()
    for turn in turns:
        if not turn.learner_response:
            continue
        meta = _practice_meta(turn)
        turn_stage = meta.get("learning_stage") or "term_understanding"
        turn_component_index = int(meta.get("component_index") or 0)
        is_sufficient = bool((turn.grading_json or {}).get("is_sufficient"))
        if turn_stage == "term_understanding":
            item_results = (turn.grading_json or {}).get("item_results") or []
            if item_results:
                for item in item_results:
                    if item.get("is_sufficient") and item.get("component_term"):
                        sufficient_components.add(item["component_term"])
                pending = [component for component in components if component not in sufficient_components]
                if pending:
                    stage = "term_understanding"
                    component_index = components.index(pending[0])
                else:
                    stage = "concept_understanding"
                    component_index = len(components)
            elif is_sufficient and turn_component_index + 1 >= len(components):
                sufficient_components.add(meta.get("component_term") or components[turn_component_index])
                stage = "concept_understanding"
                component_index = len(components)
            elif is_sufficient:
                sufficient_components.add(meta.get("component_term") or components[turn_component_index])
                stage = "term_understanding"
                component_index = turn_component_index + 1
            else:
                stage = "term_understanding"
                component_index = min(turn_component_index, len(components) - 1)
        elif turn_stage == "concept_understanding":
            if is_sufficient:
                stage = "final_feedback"
                component_index = len(components)
            else:
                stage = "term_understanding"
                component_index = 0
                sufficient_components.clear()
    pending_components = [component for component in components if component not in sufficient_components]
    return {
        "learning_stage": stage,
        "learning_stage_label": LEARNING_STAGE_LABELS[stage],
        "component_term": components[component_index] if stage == "term_understanding" else None,
        "component_index": component_index if stage == "term_understanding" else len(components),
        "component_total": len(components),
        "component_terms": pending_components if stage == "term_understanding" else components,
    }


def _merge_stage_meta(practice_question: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    practice_question = dict(practice_question or {})
    practice_question["stage_meta"] = {
        "learning_stage": position["learning_stage"],
        "learning_stage_label": position["learning_stage_label"],
        "component_term": position["component_term"],
        "component_index": position["component_index"],
        "component_total": position["component_total"],
        "component_terms": position.get("component_terms") or [],
    }
    return practice_question


def session_misconception_history(db: Session, session_id: str) -> list[dict[str, Any]]:
    turns = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session_id)
        .order_by(TutorTurn.turn_index)
        .all()
    )
    history: list[dict[str, Any]] = []
    for turn in turns:
        grading = turn.grading_json or {}
        if not grading or "learning_misconception_type" not in grading:
            continue
        meta = _practice_meta(turn)
        stage = grading.get("learning_stage") or meta.get("learning_stage") or "term_understanding"
        label = grading.get("component_term") or meta.get("component_term") or ("概念理解" if stage == "concept_understanding" else "用語理解")
        history.append(
            {
                "turn_id": turn.id,
                "turn_index": turn.turn_index,
                "learning_stage": stage,
                "label": label,
                "component_term": grading.get("component_term") or meta.get("component_term"),
                "component_index": grading.get("component_index", meta.get("component_index")),
                "misconception_type": grading.get("learning_misconception_type"),
                "confidence": grading.get("learning_misconception_confidence"),
                "reason": grading.get("learning_misconception_reason"),
                "is_sufficient": grading.get("is_sufficient"),
            }
        )
    return history


def latest_learning_misconception(db: Session, session_id: str) -> dict[str, Any] | None:
    history = session_misconception_history(db, session_id)
    return history[-1] if history else None


def _rag_query(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _rag_context(*parts: str | None) -> dict[str, Any]:
    return retrieve_rag_context(_rag_query(*parts), top_k=3)


def get_participant(db: Session, participant_id: str) -> Participant:
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="participant not found")
    return participant


def next_display_code(db: Session) -> str:
    count = db.query(func.count(Participant.id)).scalar() or 0
    return f"P{count + 1:03d}"


def create_participant(db: Session, group_condition: str | None, assignment_method: str, consent_checked: bool) -> Participant:
    if group_condition not in {"control", "proposed"}:
        group_condition = random.choice(["control", "proposed"])
        assignment_method = "random"
    participant = Participant(
        display_code=next_display_code(db),
        group_condition=group_condition,
        assignment_method=assignment_method,
        consent_checked=consent_checked,
        current_step="pretest",
        started_at=now(),
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant



def _source_question_phase(phase: str) -> str:
    return phase


def _question_query_for_phase(db: Session, participant: Participant, phase: str):
    source_phase = _source_question_phase(phase)
    query = db.query(Question).join(Term, Question.term_id == Term.id).filter(Question.phase == source_phase, Question.is_active.is_(True), Term.is_active.is_(True))
    if phase == "pretest":
        query = query.filter(Term.slug.in_(PRETEST_TERM_SLUGS))
    if phase == "retest":
        query = query.filter(Term.slug.in_(PRETEST_TERM_SLUGS))
    return query.order_by(Term.display_order, Question.variant_key)


def _displayed_options(db: Session, participant: Participant, question: Question) -> list[dict[str, str]]:
    options = db.query(QuestionOption).filter(QuestionOption.question_id == question.id).order_by(QuestionOption.default_order).all()
    if not options:
        return []
    display = db.query(QuestionDisplayOrder).filter_by(participant_id=participant.id, question_id=question.id).one_or_none()
    if not display:
        seed = f"{get_settings().random_seed}:{participant.id}:{question.id}"
        rng = random.Random(seed)
        option_ids = [option.id for option in options]
        rng.shuffle(option_ids)
        display = QuestionDisplayOrder(participant_id=participant.id, question_id=question.id, option_order=option_ids, random_seed=seed)
        db.add(display)
        db.commit()
    option_by_id = {option.id: option for option in options}
    public_options = []
    for index, option_id in enumerate(display.option_order):
        option = option_by_id[option_id]
        public_options.append({"option_id": option.id, "label": chr(65 + index), "body": option.body})
    return public_options


def question_payloads(db: Session, participant_id: str, phase: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    questions = _question_query_for_phase(db, participant, phase).all()
    if phase == "pretest":
        questions = sorted(questions, key=lambda question: PRETEST_TERM_ORDER.get(db.get(Term, question.term_id).slug, 99))
    out = []
    for question in questions:
        term = db.get(Term, question.term_id)
        public_options = _displayed_options(db, participant, question)
        out.append(
            {
                "question_id": question.id,
                "term_slug": term.slug,
                "term_label": term.label,
                "body": _variant_body_for_round(db, participant.id, question, phase),
                "question_type": question.question_type,
                "options": public_options,
                "requires_reason": phase not in {"pretest", "retest", "final_test"},
            }
        )
    return out


def _variant_body_for_round(db: Session, participant_id: str, question: Question, phase: str) -> str:
    return question.body


def _naive_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def submit_attempt(db: Session, payload: dict[str, Any], idempotency_key: str | None = None) -> Attempt:
    question = db.get(Question, payload["question_id"])
    if not question:
        raise HTTPException(status_code=404, detail="question not found")
    participant = get_participant(db, payload["participant_id"])
    if idempotency_key:
        existing = db.query(Attempt).filter_by(participant_id=participant.id, idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    phase = payload.get("phase") or question.phase
    is_pretest = phase == "pretest"
    attempt_index = (
        db.query(func.count(Attempt.id))
        .filter_by(participant_id=participant.id, question_id=question.id, phase=phase)
        .scalar()
        or 0
    ) + 1
    attempt = Attempt(
        participant_id=participant.id,
        term_id=question.term_id,
        question_id=question.id,
        phase=phase,
        attempt_index=attempt_index,
        selected_option_id=payload.get("selected_option_id"),
        free_text_answer=None if is_pretest else payload.get("free_text_answer"),
        reason_text=None if is_pretest else payload.get("reason_text"),
        confidence=None,
        response_time_sec=payload.get("response_time_sec"),
        question_shown_at=_naive_datetime(payload.get("question_shown_at")),
        answered_at=_naive_datetime(payload.get("answered_at")),
        question_body_snapshot=_variant_body_for_round(db, participant.id, question, phase),
        option_order_snapshot=_displayed_options(db, participant, question),
        idempotency_key=idempotency_key,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


async def _ai_call(db: Session, purpose: str, payload: dict[str, Any]) -> dict[str, Any]:
    backend = get_ai_backend()
    started = datetime.now(UTC)
    try:
        result = await getattr(backend, purpose)(payload)
        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        db.add(
            AICallLog(
                provider=backend.provider,
                fallback_provider=result.pop("_fallback_provider", None),
                purpose=purpose,
                request_payload=payload,
                response_payload=result,
                status="success",
                latency_ms=latency,
            )
        )
        db.commit()
        return result
    except CodexAppServerError as exc:
        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        db.add(
            AICallLog(
                provider=getattr(backend, "provider", "unknown"),
                purpose=purpose,
                request_payload=payload,
                status="failed",
                error_code=exc.code,
                error_message=exc.detail,
                latency_ms=latency,
            )
        )
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": exc.code,
                "message": exc.user_message,
                "hint": "ホストで `codex app-server --listen ws://127.0.0.1:4500` を起動し、Codex/ChatGPTログイン状態を確認してください。",
            },
        ) from exc
    except Exception as exc:
        db.add(AICallLog(provider=getattr(backend, "provider", "unknown"), purpose=purpose, request_payload=payload, status="failed", error_code="ai_call_failed", error_message=str(exc)))
        db.commit()
        raise


def _selected_option(db: Session, attempt: Attempt) -> QuestionOption | None:
    return db.get(QuestionOption, attempt.selected_option_id) if attempt.selected_option_id else None


def _diagnosis_payload(db: Session, participant: Participant, attempt: Attempt) -> dict[str, Any]:
    question = db.get(Question, attempt.question_id)
    term = db.get(Term, attempt.term_id)
    option = _selected_option(db, attempt)
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "definition": term.description},
        "question": {"id": question.id, "phase": question.phase, "question_type": question.question_type, "body": question.body, "expected_answer": question.expected_answer},
        "selected_option": None
        if not option
        else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
        "history": {"previous_attempts": []},
    }
    if question.phase != "pretest":
        payload["learner_response"] = {"reason_text": attempt.reason_text, "free_text_answer": attempt.free_text_answer}
    return payload


def _public_summary(text: str | None) -> str:
    cleaned = text or "この用語を重点的に確認します。"
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないため、?", "", cleaned)
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないので、?", "", cleaned)
    cleaned = re.sub(r"理由記述や自信度", "回答内容", cleaned)
    cleaned = re.sub(r"理由記述", "回答内容", cleaned)
    cleaned = re.sub(r"自信度", "", cleaned)
    cleaned = re.sub(r"、{2,}", "、", cleaned)
    cleaned = re.sub(r"。{2,}", "。", cleaned)
    return cleaned.strip("、 ") or "この用語を重点的に確認します。"


def _priority(attempt: Attempt) -> tuple[float, str]:
    term_order_bonus = 0
    if attempt.diagnosed_status == "misconception":
        score = 70 + term_order_bonus
        if attempt.misconception_type in {"M1", "M2"}:
            score += 20
        elif attempt.misconception_type == "M3":
            score += 10
        return score, f"{attempt.misconception_type}を重点確認"
    if attempt.diagnosed_status == "unknown":
        return 55 + term_order_bonus, "基礎理解を確認"
    if attempt.diagnosed_status == "unstable_correct":
        return 45 + term_order_bonus, "理解を確認"
    return 10 + term_order_bonus, "転移準備"


async def diagnose_pretest(db: Session, participant_id: str) -> int:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase="pretest").all()
    if not attempts:
        raise HTTPException(status_code=400, detail="pretest attempts not found")

    scored_attempts: list[Attempt] = []
    for attempt in attempts:
        result = await _ai_call(db, "diagnose_answer", _diagnosis_payload(db, participant, attempt))
        attempt.is_correct = result["is_correct"]
        attempt.score = 1.0 if result["is_correct"] else 0.0
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        attempt.secondary_misconception_type = result["secondary_misconception_type"]
        attempt.misconception_confidence = result["diagnosis_confidence"]
        attempt.natural_language_diagnosis = result["natural_language_diagnosis"]
        attempt.requires_manual_review = result["requires_manual_review"]
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if not state:
            state = LearnerState(participant_id=participant.id, term_id=attempt.term_id, current_status=result["diagnosed_status"], primary_misconception=result["misconception_type"], secondary_misconception=result["secondary_misconception_type"], scaffolding_level=result["recommended_initial_scaffolding_level"], teaching_strategy=result["recommended_teaching_strategy"], last_attempt_id=attempt.id, state_summary=result["natural_language_diagnosis"])
            db.add(state)
        scored_attempts.append(attempt)
    db.commit()

    for attempt in scored_attempts:
        existing = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        score, reason = _priority(attempt)
        if not existing:
            db.add(TermAssignment(participant_id=participant.id, term_id=attempt.term_id, group_condition=participant.group_condition, priority_score=score, selection_reason=reason))
        else:
            existing.priority_score = score
            existing.selection_reason = reason
    db.commit()

    assignments = (
        db.query(TermAssignment)
        .filter_by(participant_id=participant.id)
        .order_by(TermAssignment.priority_score.desc())
        .all()
    )
    latest_attempt_by_term = {attempt.term_id: attempt for attempt in scored_attempts}
    for index, assignment in enumerate(assignments):
        latest_attempt = latest_attempt_by_term.get(assignment.term_id)
        assignment.is_learning_target = bool(latest_attempt and not latest_attempt.is_correct and index < get_settings().max_learning_targets)
    remaining = sum(1 for assignment in assignments if assignment.is_learning_target)
    participant.current_step = "learning_targets" if remaining else "final_test"
    db.commit()
    return remaining


def learning_targets(db: Session, participant_id: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    rows = (
        db.query(TermAssignment, Term, LearnerState)
        .join(Term, TermAssignment.term_id == Term.id)
        .join(LearnerState, (LearnerState.term_id == Term.id) & (LearnerState.participant_id == participant.id))
        .filter(TermAssignment.participant_id == participant.id, TermAssignment.is_learning_target.is_(True))
        .order_by(TermAssignment.priority_score.desc())
        .all()
    )
    return [
        {
            "term_slug": term.slug,
            "term_label": term.label,
            "summary_for_learner": _public_summary(state.state_summary),
            "current_stage_for_display": PUBLIC_LEVEL.get(normalize_level(state.scaffolding_level), "概念理解を確認"),
        }
        for _, term, state in rows
    ]


def create_tutor_session(db: Session, participant_id: str, term_slug: str) -> TutorSession:
    participant = get_participant(db, participant_id)
    term = db.query(Term).filter_by(slug=term_slug).one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="term not found")
    count = db.query(func.count(TutorSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
    session = TutorSession(participant_id=participant.id, term_id=term.id, session_index=count + 1, group_condition=participant.group_condition)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


async def generate_tutor_turn(db: Session, session_id: str) -> TutorTurn:
    session = db.get(TutorSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=term.id).one()
    previous_attempt = db.get(Attempt, state.last_attempt_id) if state.last_attempt_id else None
    previous_turn = db.get(TutorTurn, state.last_tutor_turn_id) if state.last_tutor_turn_id else None
    turn_count = db.query(func.count(TutorTurn.id)).filter_by(tutor_session_id=session.id).scalar() or 0
    position = _learning_position(db, session, term, participant)
    if position["learning_stage"] == "final_feedback":
        raise HTTPException(status_code=400, detail="learning session already completed")

    current_level = normalize_level(state.scaffolding_level)
    misconception_history = session_misconception_history(db, session.id)
    previous_learning_misconception = misconception_history[-1] if misconception_history else None
    effective_misconception = (previous_learning_misconception or {}).get("misconception_type") or state.primary_misconception
    effective_status = "unknown" if effective_misconception == "unknown" else ("misconception" if effective_misconception else state.current_status)
    effective_strategy = strategy_for(effective_misconception, effective_status, participant.group_condition)
    if participant.group_condition == "control":
        effective_strategy = "general_explanation"

    l3_batch = participant.group_condition == "proposed" and position["learning_stage"] == "term_understanding"
    if l3_batch:
        items = [_learning_question_item(term.slug, component) for component in position.get("component_terms") or _component_terms(term.slug, term.label)]
        practice_question = {
            "body": "次の構成用語について、それぞれ最も適切な説明を選んでください。",
            "question_type": "component_choice_set",
            "items": items,
        }
        tutor_message = _previous_turn_prefix(previous_turn) + "\n\n".join(f"【{item['component_term']}】\n{item['material']}" for item in items)
        spec = {
            "body": practice_question["body"],
            "expected_answer": " / ".join(item["expected_answer"] for item in items),
            "material": tutor_message,
            "question_type": "component_choice_set",
        }
        question_type = "component_choice_set"
    else:
        spec = _learning_question_spec(term.slug, position["learning_stage"], position["component_term"])
        question_type = spec["question_type"]
        if participant.group_condition == "control" and position["learning_stage"] == "concept_understanding":
            question_type = "control_l2_check"
        practice_question = {
            "body": spec["body"],
            "expected_answer": spec["expected_answer"],
            "question_type": question_type,
            "options": _public_learning_options(spec),
        }
        tutor_message = _previous_turn_prefix(previous_turn) + spec["material"]
    teaching_strategy = effective_strategy
    material_source = "fixed"
    material_generation_ms = None
    if participant.group_condition == "proposed":
        payload = {
            "participant_id": participant.id,
            "group_condition": participant.group_condition,
            "term": {"slug": term.slug, "label": term.label, "description": term.description},
            "learning_stage": position["learning_stage"],
            "learning_stage_label": position["learning_stage_label"],
            "component_term": position["component_term"],
            "component_index": position["component_index"],
            "component_total": position["component_total"],
            "component_terms": _component_terms(term.slug, term.label),
            "learner_state": {
                "current_status": state.current_status,
                "primary_misconception": state.primary_misconception,
                "scaffolding_level": current_level,
                "teaching_strategy": effective_strategy,
                "recurrence_count": state.recurrence_count,
            },
            "previous_answer": previous_attempt.reason_text if previous_attempt else "",
            "previous_diagnosis_for_learner": state.state_summary,
            "previous_practice_question": _practice_question_text(previous_turn.practice_question_json if previous_turn else None),
            "previous_learner_response": previous_turn.learner_response if previous_turn else "",
            "previous_feedback_for_learner": previous_turn.ai_feedback if previous_turn else "",
            "previous_learning_misconception": previous_learning_misconception,
            "session_misconception_history": misconception_history,
            "misconception_scaffolding_guidance": _misconception_scaffolding_guidance(effective_misconception),
            "fixed_practice_question": {
                "body": spec["body"],
                "expected_answer": spec["expected_answer"],
                "question_type": question_type,
            },
            "fixed_practice_question_items": practice_question.get("items") or [],
            "rag_context": _rag_context(
                term.label,
                term.description,
                position["component_term"],
                previous_attempt.reason_text if previous_attempt else "",
                _practice_question_text(previous_turn.practice_question_json if previous_turn else None),
                previous_turn.learner_response if previous_turn else "",
            ),
        }
        started = perf_counter()
        result = await _ai_call(db, "generate_tutoring_turn", payload)
        material_generation_ms = int((perf_counter() - started) * 1000)
        material_source = "ai"
        if l3_batch:
            fixed_material = "\n\n".join(f"【{item['component_term']}】\n{item['material']}" for item in practice_question["items"])
            tutor_message = f"{result['tutor_message']}\n\n{fixed_material}"
        else:
            tutor_message = result["tutor_message"]
        teaching_strategy = result["teaching_strategy"]

    turn = TutorTurn(
        tutor_session_id=session.id,
        turn_index=turn_count + 1,
        scaffolding_level=current_level,
        teaching_strategy=teaching_strategy,
        previous_teaching_strategy=state.previous_teaching_strategy,
        strategy_changed=False,
        tutor_message=tutor_message,
        learner_prompt=spec["body"],
        practice_question_json=_merge_stage_meta(practice_question, position),
        diagnosis_json={"material_source": material_source, "material_generation_ms": material_generation_ms},
        forbidden_help_given=False,
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn

async def respond_tutor_turn(db: Session, turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    turn = db.get(TutorTurn, turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail="turn not found")
    session = db.get(TutorSession, turn.tutor_session_id)
    state = db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one()
    response = payload.get("learner_response") or ""
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    meta = _practice_meta(turn)
    learning_stage = meta.get("learning_stage") or "term_understanding"
    component_index = int(meta.get("component_index") or 0)
    component_total = int(meta.get("component_total") or len(_component_terms(term.slug, term.label)))
    component_term = meta.get("component_term")
    practice_question = turn.practice_question_json or {}
    selected_item_option_ids = payload.get("selected_item_option_ids") or {}
    item_results: list[dict[str, Any]] = []
    if learning_stage == "term_understanding" and practice_question.get("items"):
        response_parts = []
        for item in practice_question.get("items") or []:
            item_component = item["component_term"]
            item_spec = _learning_question_spec(term.slug, "term_understanding", item_component)
            item_result = _fixed_item_result(item_component, selected_item_option_ids.get(item_component), "", item_spec)
            item_results.append(item_result)
            response_parts.append(f"{item_component}: {item_result.get('selected_option_body') or '未選択'}")
        response = "\n".join(response_parts)
        is_sufficient = all(item["is_sufficient"] for item in item_results)
        first_incorrect = next((item for item in item_results if not item["is_sufficient"]), None)
        result = {
            "feedback": _feedback_text_from_item_results(item_results),
            "is_sufficient": is_sufficient,
            "next_action": "move_next" if is_sufficient else "continue",
            "next_scaffolding_level": "L2" if is_sufficient else "L3",
            "learning_misconception_type": first_incorrect.get("learning_misconception_type") if first_incorrect else None,
            "learning_misconception_confidence": 0.95,
            "learning_misconception_reason": "L3複数構成用語の固定選択式問題で項目別に判定しました。",
            "state_update_reason": "fixed_choice_set_correct" if is_sufficient else "fixed_choice_set_incomplete",
        }
        option = None
    else:
        spec = _learning_question_spec(term.slug, learning_stage, component_term)
        option = _selected_fixed_option(spec, payload.get("selected_option_id"), response)
        if option:
            response = option["body"]
        result = _fixed_feedback(option, spec)
    is_sufficient = bool(result.get("is_sufficient"))
    learning_misconception_type = result.get("learning_misconception_type")
    if learning_misconception_type not in {"M1", "M2", "M3", "M4", "unknown", None}:
        learning_misconception_type = "unknown"
    learning_misconception_confidence = result.get("learning_misconception_confidence")
    learning_misconception_reason = result.get("learning_misconception_reason") or result.get("state_update_reason") or ""
    next_level = normalize_level(lower_level(state.scaffolding_level) if is_sufficient else raise_level(state.scaffolding_level))
    if learning_stage == "term_understanding":
        stage_completed = is_sufficient and (bool(item_results) or component_index + 1 >= component_total)
        next_learning_stage = "concept_understanding" if stage_completed else "term_understanding"
        if item_results and not is_sufficient:
            components = _component_terms(term.slug, term.label)
            first_pending = next((item["component_term"] for item in item_results if not item["is_sufficient"]), component_term)
            next_component_index = components.index(first_pending) if first_pending in components else component_index
        else:
            next_component_index = component_total if stage_completed else (component_index + 1 if is_sufficient else component_index)
        session_completed = False
        next_action = "continue"
    elif learning_stage == "concept_understanding":
        stage_completed = is_sufficient
        next_learning_stage = "final_feedback" if is_sufficient else ("concept_understanding" if participant.group_condition == "control" else "term_understanding")
        next_component_index = component_total if is_sufficient else (component_total if participant.group_condition == "control" else 0)
        session_completed = is_sufficient
        next_action = "move_next" if is_sufficient else "continue"
    else:
        stage_completed = True
        next_learning_stage = "final_feedback"
        next_component_index = component_total
        session_completed = True
        next_action = "move_next"
    turn.learner_response = response
    turn.learner_confidence = None
    turn.question_shown_at = _naive_datetime(payload.get("question_shown_at"))
    turn.answered_at = _naive_datetime(payload.get("answered_at"))
    turn.response_time_sec = payload.get("response_time_sec")
    turn.next_scaffolding_level = next_level
    turn.ai_feedback = result["feedback"]
    turn.grading_json = {
        "is_sufficient": is_sufficient,
        "selected_option_id": option.get("option_id") if option else payload.get("selected_option_id"),
        "selected_option_body": option.get("body") if option else response,
        "learning_stage": learning_stage,
        "component_term": component_term,
        "component_index": component_index,
        "component_total": component_total,
        "item_results": item_results,
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "next_component_index": next_component_index,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "ai_next_action": result.get("next_action"),
        "response_time_sec": payload.get("response_time_sec"),
        "material_source": (turn.diagnosis_json or {}).get("material_source"),
        "material_generation_ms": (turn.diagnosis_json or {}).get("material_generation_ms"),
    }
    state.scaffolding_level = next_level
    state.stable_correct_count += 1 if is_sufficient else 0
    state.current_status = "stable_correct" if session_completed else ("learning_in_progress" if is_sufficient else "needs_review")
    state.updated_reason = result["state_update_reason"]
    state.last_tutor_turn_id = turn.id
    if session_completed:
        session.ended_at = now()
    db.commit()
    return {
        "feedback": turn.ai_feedback,
        "next_action": next_action,
        "is_sufficient": is_sufficient,
        "session_completed": session_completed,
        "learning_stage": learning_stage,
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "component_term": component_term,
        "component_index": component_index,
        "component_total": component_total,
        "next_component_index": next_component_index,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "next_scaffolding_level": next_level,
        "turn_index": turn.turn_index,
        "max_turns": get_settings().max_turns_per_term,
        "item_results": item_results,
    }

async def score_phase(db: Session, participant_id: str, phase: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase, is_correct=None).all()
    if not attempts:
        raise HTTPException(status_code=400, detail=f"{phase} attempts not found")
    for attempt in attempts:
        question = db.get(Question, attempt.question_id)
        option = _selected_option(db, attempt)
        payload = {
            "participant_id": participant.id,
            "group_condition": participant.group_condition,
            "question": {"id": question.id, "phase": phase, "body": question.body, "expected_answer": question.expected_answer, "expected_keywords": question.expected_keywords},
            "selected_option": None if not option else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
            "free_text_answer": attempt.free_text_answer,
            "reason_text": attempt.reason_text,
        }
        if phase in {"retest", "final_test"} and option:
            result = {
                "is_correct": bool(option.is_correct),
                "score": 1.0 if option.is_correct else 0.0,
                "diagnosed_status": "stable_correct" if option.is_correct else ("unknown" if option.misconception_type == "unknown" else "misconception"),
                "misconception_type": None if option.is_correct else option.misconception_type,
                "secondary_misconception_type": None,
                "l0_success": bool(option.is_correct),
            }
        else:
            result = await _ai_call(db, "grade_response", payload)
        attempt.is_correct = result["is_correct"]
        attempt.score = result["score"]
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        attempt.secondary_misconception_type = result["secondary_misconception_type"]
        attempt.l0_success = result["l0_success"] if result.get("l0_success") is not None else (result["is_correct"] if phase == "final_test" else None)
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if not state:
            continue
        if phase == "retest":
            previous = db.query(Attempt).filter_by(participant_id=participant.id, term_id=attempt.term_id, phase="pretest").order_by(Attempt.created_at.desc()).first()
            if previous and previous.misconception_type in {"M1", "M2", "M3"} and previous.misconception_type == attempt.misconception_type:
                attempt.recurrence_flag = True
                state.recurrence_count += 1
                state.previous_teaching_strategy = state.teaching_strategy
                state.teaching_strategy = strategy_for(attempt.misconception_type, "misconception", participant.group_condition)
                db.add(RecurrenceEvent(participant_id=participant.id, term_id=attempt.term_id, previous_attempt_id=previous.id, current_attempt_id=attempt.id, previous_misconception_type=previous.misconception_type, current_misconception_type=attempt.misconception_type, is_same_type=True, phase=phase))
            state.scaffolding_level = lower_level(state.scaffolding_level) if attempt.is_correct else state.scaffolding_level
            assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
            if assignment:
                assignment.is_learning_target = not bool(attempt.is_correct)
                if attempt.is_correct:
                    assignment.priority_score = 0
                    assignment.selection_reason = "正解したため次周回から除外"
                else:
                    assignment.priority_score, assignment.selection_reason = _priority(attempt)
        if phase in {"l0_check", "final_test"}:
            state.l0_success_count += 1 if attempt.is_correct else 0
            state.scaffolding_level = "L2" if attempt.is_correct else "L3"
        state.current_status = "stable_correct" if attempt.is_correct else "misconception"
        state.last_attempt_id = attempt.id
    if phase == "retest":
        db.flush()
        remaining = db.query(func.count(TermAssignment.id)).filter_by(participant_id=participant.id, is_learning_target=True).scalar() or 0
        participant.current_step = "learning_targets" if remaining else "final_test"
    elif phase == "l0_check":
        participant.current_step = "finish"
        participant.completed_at = now()
    elif phase == "final_test":
        participant.current_step = "survey"
    db.commit()
    return {"status": "completed", "next_step": participant.current_step, "next_url": _next_url(participant.current_step)}


def _next_url(step: str) -> str:
    return {
        "pretest": "/pretest",
        "learning_targets": "/learning-targets",
        "final_test": "/final-test",
        "survey": "/survey",
        "finish": "/finish",
    }.get(step, "/start")


def _rate(items: list[Attempt], predicate) -> float | None:
    if not items:
        return None
    return sum(1 for item in items if predicate(item)) / len(items)


def recalculate_evaluation(db: Session, participant_id: str) -> EvaluationSummary:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).all()
    by_phase = {phase: [a for a in attempts if a.phase == phase] for phase in ["pretest", "retest", "l0_check", "final_test"]}
    final_items = by_phase["final_test"] or by_phase["l0_check"]
    initial_m = [a for a in by_phase["pretest"] if a.misconception_type in {"M1", "M2", "M3"}]
    same_rec = [a for a in by_phase["retest"] if a.recurrence_flag]
    def m_rate(m: str) -> float | None:
        denom = [a for a in initial_m if a.misconception_type == m]
        if not denom:
            return None
        rec_terms = {a.term_id for a in by_phase["retest"] if a.recurrence_flag and a.misconception_type == m}
        return len(rec_terms) / len(denom)

    summary = EvaluationSummary(
        participant_id=participant.id,
        group_condition=participant.group_condition,
        pretest_score=_rate(by_phase["pretest"], lambda a: bool(a.is_correct)),
        retest_score=_rate(by_phase["retest"], lambda a: bool(a.is_correct)),
        l0_correct_rate=_rate(final_items, lambda a: bool(a.l0_success)),
        transfer_correct_rate=None,
        same_misconception_recurrence_rate=(len(same_rec) / len(initial_m)) if initial_m else None,
        m1_recurrence_rate=m_rate("M1"),
        m2_recurrence_rate=m_rate("M2"),
        m3_recurrence_rate=m_rate("M3"),
        m4_failure_rate=None,
        unknown_persistence_rate=None,
        learning_target_count=db.query(func.count(TermAssignment.id)).filter_by(participant_id=participant.id, is_learning_target=True).scalar() or 0,
        completed=participant.completed_at is not None,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def admin_summary(db: Session) -> dict[str, Any]:
    participants = db.query(Participant).all()
    rows = []
    for group in ["control", "proposed"]:
        group_participants = [p for p in participants if p.group_condition == group]
        latest_summaries = []
        for p in group_participants:
            s = db.query(EvaluationSummary).filter_by(participant_id=p.id).order_by(EvaluationSummary.created_at.desc()).first()
            if s:
                latest_summaries.append(s)
        def avg(attr: str):
            vals = [getattr(s, attr) for s in latest_summaries if getattr(s, attr) is not None]
            return sum(vals) / len(vals) if vals else None
        rows.append(
            {
                "group_condition": group,
                "participant_count": len(group_participants),
                "same_misconception_recurrence_rate": avg("same_misconception_recurrence_rate"),
                "l0_correct_rate": avg("l0_correct_rate"),
            }
        )
    return {"groups": rows}


EXPORTS = {
    "participants": (Participant, ["id", "display_code", "group_condition", "assignment_method", "current_step", "started_at", "completed_at"]),
    "attempts": (Attempt, ["id", "participant_id", "term_id", "phase", "question_id", "selected_option_id", "reason_text", "free_text_answer", "response_time_sec", "question_shown_at", "answered_at", "question_body_snapshot", "option_order_snapshot", "is_correct", "score", "diagnosed_status", "misconception_type", "recurrence_flag", "l0_success", "requires_manual_review", "created_at"]),
    "learner_states": (LearnerState, ["participant_id", "term_id", "current_status", "primary_misconception", "scaffolding_level", "teaching_strategy", "stable_correct_count", "recurrence_count", "l0_success_count", "updated_at"]),
    "tutor_sessions": (TutorSession, ["id", "participant_id", "term_id", "session_index", "group_condition", "started_at", "ended_at"]),
    "tutor_turns": (TutorTurn, ["id", "tutor_session_id", "turn_index", "scaffolding_level", "teaching_strategy", "strategy_changed", "tutor_message", "learner_response", "ai_feedback", "next_scaffolding_level", "forbidden_help_given", "question_shown_at", "answered_at", "response_time_sec", "created_at"]),
    "recurrence_events": (RecurrenceEvent, ["id", "participant_id", "term_id", "previous_attempt_id", "current_attempt_id", "previous_misconception_type", "current_misconception_type", "is_same_type", "phase", "created_at"]),
    "ai_call_logs": (AICallLog, ["id", "provider", "fallback_provider", "purpose", "status", "error_code", "latency_ms", "created_at"]),
    "evaluation_summary": (EvaluationSummary, ["participant_id", "group_condition", "pretest_score", "retest_score", "l0_correct_rate", "same_misconception_recurrence_rate", "m1_recurrence_rate", "m2_recurrence_rate", "m3_recurrence_rate", "learning_target_count", "completed", "created_at"]),
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _term_map(db: Session) -> dict[str, Term]:
    return {term.id: term for term in db.query(Term).all()}


def _participant_map(db: Session) -> dict[str, Participant]:
    return {participant.id: participant for participant in db.query(Participant).all()}


def _option_map(db: Session) -> dict[str, QuestionOption]:
    return {option.id: option for option in db.query(QuestionOption).all()}


def _question_map(db: Session) -> dict[str, Question]:
    return {question.id: question for question in db.query(Question).all()}


def _attempt_log_row(
    attempt: Attempt,
    participants: dict[str, Participant],
    terms: dict[str, Term],
    questions: dict[str, Question],
    options: dict[str, QuestionOption],
) -> dict[str, Any]:
    participant = participants.get(attempt.participant_id)
    term = terms.get(attempt.term_id)
    question = questions.get(attempt.question_id)
    option = options.get(attempt.selected_option_id or "")
    return {
        "attempt_id": attempt.id,
        "participant_id": attempt.participant_id,
        "display_code": participant.display_code if participant else None,
        "group_condition": participant.group_condition if participant else None,
        "phase": attempt.phase,
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "question_body": question.body if question else None,
        "selected_option_body": option.body if option else None,
        "question_body_snapshot": attempt.question_body_snapshot,
        "option_order_snapshot": attempt.option_order_snapshot,
        "response_time_sec": attempt.response_time_sec,
        "question_shown_at": _iso(attempt.question_shown_at),
        "answered_at": _iso(attempt.answered_at),
        "free_text_answer": attempt.free_text_answer,
        "reason_text": attempt.reason_text,
        "is_correct": attempt.is_correct,
        "score": attempt.score,
        "diagnosed_status": attempt.diagnosed_status,
        "misconception_type": attempt.misconception_type,
        "recurrence_flag": attempt.recurrence_flag,
        "l0_success": attempt.l0_success,
        "requires_manual_review": attempt.requires_manual_review,
        "created_at": _iso(attempt.created_at),
    }


def _turn_log_row(turn: TutorTurn, session: TutorSession, participant: Participant | None, term: Term | None) -> dict[str, Any]:
    stage_meta = (turn.practice_question_json or {}).get("stage_meta") or {}
    grading = turn.grading_json or {}
    practice_question = turn.practice_question_json or {}
    return {
        "tutor_turn_id": turn.id,
        "tutor_session_id": turn.tutor_session_id,
        "participant_id": session.participant_id,
        "display_code": participant.display_code if participant else None,
        "group_condition": session.group_condition,
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "session_index": session.session_index,
        "turn_index": turn.turn_index,
        "scaffolding_level": turn.scaffolding_level,
        "learning_stage": stage_meta.get("learning_stage"),
        "learning_stage_label": stage_meta.get("learning_stage_label"),
        "component_term": stage_meta.get("component_term"),
        "component_index": stage_meta.get("component_index"),
        "component_total": stage_meta.get("component_total"),
        "next_learning_stage": grading.get("next_learning_stage"),
        "teaching_strategy": turn.teaching_strategy,
        "strategy_changed": turn.strategy_changed,
        "tutor_message": turn.tutor_message,
        "learner_prompt": turn.learner_prompt,
        "question_body": practice_question.get("body"),
        "selected_option_body": grading.get("selected_option_body"),
        "learner_response": turn.learner_response,
        "is_sufficient": grading.get("is_sufficient"),
        "learning_misconception_type": grading.get("learning_misconception_type"),
        "ai_feedback": turn.ai_feedback,
        "practice_question": practice_question,
        "grading_json": turn.grading_json,
        "response_time_sec": turn.response_time_sec if turn.response_time_sec is not None else grading.get("response_time_sec"),
        "question_shown_at": _iso(turn.question_shown_at),
        "answered_at": _iso(turn.answered_at),
        "forbidden_help_given": turn.forbidden_help_given,
        "created_at": _iso(turn.created_at),
    }


def _answer_event_time(row: dict[str, Any]) -> str:
    return row.get("answered_at") or row.get("created_at") or ""


def _answer_history_attempt_row(attempt_row: dict[str, Any]) -> dict[str, Any]:
    return {
        **attempt_row,
        "answer_log_id": f"attempt:{attempt_row['attempt_id']}",
        "source_type": "test_attempt",
        "source_id": attempt_row["attempt_id"],
        "learning_stage": None,
        "component_term": None,
        "component_index": None,
        "component_total": None,
        "turn_index": None,
        "is_sufficient": None,
        "teaching_strategy": None,
        "learner_response": attempt_row.get("selected_option_body") or attempt_row.get("free_text_answer") or attempt_row.get("reason_text"),
    }


def _answer_history_turn_row(turn_row: dict[str, Any]) -> dict[str, Any]:
    return {
        **turn_row,
        "answer_log_id": f"tutor_turn:{turn_row['tutor_turn_id']}",
        "source_type": "learning_turn",
        "source_id": turn_row["tutor_turn_id"],
        "phase": "learning",
        "is_correct": None,
        "misconception_type": turn_row.get("learning_misconception_type"),
        "recurrence_flag": None,
        "question_body_snapshot": turn_row.get("question_body"),
        "option_order_snapshot": (turn_row.get("practice_question") or {}).get("options"),
        "free_text_answer": None,
        "reason_text": None,
        "learner_response": turn_row.get("selected_option_body") or turn_row.get("learner_response"),
    }


def _answer_history_turn_rows(turn_row: dict[str, Any]) -> list[dict[str, Any]]:
    item_results = (turn_row.get("grading_json") or {}).get("item_results") or []
    if not item_results:
        return [_answer_history_turn_row(turn_row)]
    rows = []
    for index, item in enumerate(item_results):
        rows.append(
            {
                **turn_row,
                "answer_log_id": f"tutor_turn:{turn_row['tutor_turn_id']}:item:{index}",
                "source_type": "learning_turn",
                "source_id": turn_row["tutor_turn_id"],
                "phase": "learning",
                "is_correct": item.get("is_correct"),
                "misconception_type": item.get("learning_misconception_type"),
                "recurrence_flag": None,
                "question_body": item.get("question_body"),
                "question_body_snapshot": item.get("question_body"),
                "option_order_snapshot": next(
                    (practice_item.get("options") for practice_item in (turn_row.get("practice_question") or {}).get("items", []) if practice_item.get("component_term") == item.get("component_term")),
                    None,
                ),
                "free_text_answer": None,
                "reason_text": None,
                "learner_response": item.get("selected_option_body"),
                "selected_option_body": item.get("selected_option_body"),
                "is_sufficient": item.get("is_sufficient"),
                "learning_misconception_type": item.get("learning_misconception_type"),
                "component_term": item.get("component_term"),
                "component_index": index,
                "component_total": len(item_results),
            }
        )
    return rows


def _answer_history_rows(attempt_rows: list[dict[str, Any]], turn_rows: list[dict[str, Any]], *, reverse: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    rows = [_answer_history_attempt_row(row) for row in attempt_rows]
    for row in turn_rows:
        if not row.get("learner_response") and not row.get("grading_json"):
            continue
        rows.extend(_answer_history_turn_rows(row))
    rows.sort(key=_answer_event_time, reverse=reverse)
    return rows[:limit] if limit is not None else rows


def _ai_log_belongs_to(log: AICallLog, participant_id: str) -> bool:
    payload = log.request_payload or {}
    return payload.get("participant_id") == participant_id


def admin_logs_overview(db: Session) -> dict[str, Any]:
    participants = db.query(Participant).order_by(Participant.created_at.desc()).all()
    participant_by_id = {participant.id: participant for participant in participants}
    terms = _term_map(db)
    questions = _question_map(db)
    options = _option_map(db)
    attempts = db.query(Attempt).order_by(Attempt.created_at.desc()).limit(50).all()
    sessions = {session.id: session for session in db.query(TutorSession).all()}
    recent_turns = db.query(TutorTurn).order_by(TutorTurn.created_at.desc()).limit(30).all()
    ai_logs = db.query(AICallLog).order_by(AICallLog.created_at.desc()).limit(50).all()
    recurrences = db.query(RecurrenceEvent).order_by(RecurrenceEvent.created_at.desc()).limit(30).all()
    summaries = db.query(EvaluationSummary).order_by(EvaluationSummary.created_at.desc()).limit(30).all()
    recent_attempt_rows = [_attempt_log_row(row, participant_by_id, terms, questions, options) for row in attempts]
    recent_turn_rows = [
        _turn_log_row(row, sessions[row.tutor_session_id], participant_by_id.get(sessions[row.tutor_session_id].participant_id), terms.get(sessions[row.tutor_session_id].term_id))
        for row in recent_turns
        if row.tutor_session_id in sessions
    ]
    return {
        "participant_count": len(participants),
        "groups": admin_summary(db)["groups"],
        "participants": [
            {
                "participant_id": row.id,
                "display_code": row.display_code,
                "group_condition": row.group_condition,
                "current_step": row.current_step,
                "completed_at": _iso(row.completed_at),
                "created_at": _iso(row.created_at),
            }
            for row in participants
        ],
        "recent_attempts": recent_attempt_rows,
        "recent_tutor_turns": recent_turn_rows,
        "recent_answer_history": _answer_history_rows(recent_attempt_rows, recent_turn_rows, reverse=True, limit=50),
        "recent_ai_call_logs": [
            {
                "id": row.id,
                "provider": row.provider,
                "purpose": row.purpose,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "created_at": _iso(row.created_at),
            }
            for row in ai_logs
        ],
        "recurrence_events": [
            {
                "id": row.id,
                "participant_id": row.participant_id,
                "display_code": participant_by_id.get(row.participant_id).display_code if participant_by_id.get(row.participant_id) else None,
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "previous_misconception_type": row.previous_misconception_type,
                "current_misconception_type": row.current_misconception_type,
                "phase": row.phase,
                "created_at": _iso(row.created_at),
            }
            for row in recurrences
        ],
        "evaluation_summaries": [
            {
                "participant_id": row.participant_id,
                "display_code": participant_by_id.get(row.participant_id).display_code if participant_by_id.get(row.participant_id) else None,
                "group_condition": row.group_condition,
                "pretest_score": row.pretest_score,
                "retest_score": row.retest_score,
                "l0_correct_rate": row.l0_correct_rate,
                "same_misconception_recurrence_rate": row.same_misconception_recurrence_rate,
                "completed": row.completed,
                "created_at": _iso(row.created_at),
            }
            for row in summaries
        ],
    }


def participant_logs(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    participants = {participant.id: participant}
    terms = _term_map(db)
    questions = _question_map(db)
    options = _option_map(db)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).order_by(Attempt.created_at).all()
    states = db.query(LearnerState).filter_by(participant_id=participant.id).order_by(LearnerState.updated_at).all()
    assignments = db.query(TermAssignment).filter_by(participant_id=participant.id).all()
    sessions = db.query(TutorSession).filter_by(participant_id=participant.id).order_by(TutorSession.started_at).all()
    session_ids = [session.id for session in sessions]
    turns = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids or ["__none__"])).order_by(TutorTurn.created_at).all()
    turns_by_session: dict[str, list[TutorTurn]] = {}
    for turn in turns:
        turns_by_session.setdefault(turn.tutor_session_id, []).append(turn)
    recurrences = db.query(RecurrenceEvent).filter_by(participant_id=participant.id).order_by(RecurrenceEvent.created_at).all()
    ai_logs = [row for row in db.query(AICallLog).order_by(AICallLog.created_at).all() if _ai_log_belongs_to(row, participant.id)]
    summary = db.query(EvaluationSummary).filter_by(participant_id=participant.id).order_by(EvaluationSummary.created_at.desc()).first()
    attempt_rows = [_attempt_log_row(row, participants, terms, questions, options) for row in attempts]
    tutor_sessions = [
        {
            "tutor_session_id": session.id,
            "term_slug": terms.get(session.term_id).slug if terms.get(session.term_id) else None,
            "term_label": terms.get(session.term_id).label if terms.get(session.term_id) else None,
            "session_index": session.session_index,
            "group_condition": session.group_condition,
            "started_at": _iso(session.started_at),
            "ended_at": _iso(session.ended_at),
            "turns": [_turn_log_row(turn, session, participant, terms.get(session.term_id)) for turn in turns_by_session.get(session.id, [])],
        }
        for session in sessions
    ]
    turn_rows = [turn for session in tutor_sessions for turn in session["turns"]]
    return {
        "participant": {
            "participant_id": participant.id,
            "display_code": participant.display_code,
            "group_condition": participant.group_condition,
            "assignment_method": participant.assignment_method,
            "current_step": participant.current_step,
            "started_at": _iso(participant.started_at),
            "completed_at": _iso(participant.completed_at),
            "created_at": _iso(participant.created_at),
        },
        "attempts": attempt_rows,
        "answer_history": _answer_history_rows(attempt_rows, turn_rows),
        "learner_states": [
            {
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "term_label": terms.get(row.term_id).label if terms.get(row.term_id) else None,
                "current_status": row.current_status,
                "primary_misconception": row.primary_misconception,
                "scaffolding_level": row.scaffolding_level,
                "current_stage_for_display": PUBLIC_LEVEL.get(normalize_level(row.scaffolding_level), "概念理解を確認"),
                "teaching_strategy": row.teaching_strategy,
                "stable_correct_count": row.stable_correct_count,
                "recurrence_count": row.recurrence_count,
                "l0_success_count": row.l0_success_count,
                "state_summary": row.state_summary,
                "updated_at": _iso(row.updated_at),
            }
            for row in states
        ],
        "term_assignments": [
            {
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "term_label": terms.get(row.term_id).label if terms.get(row.term_id) else None,
                "is_learning_target": row.is_learning_target,
                "selection_reason": row.selection_reason,
                "priority_score": row.priority_score,
                "created_at": _iso(row.created_at),
            }
            for row in assignments
        ],
        "tutor_sessions": tutor_sessions,
        "recurrence_events": [
            {
                "id": row.id,
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "previous_misconception_type": row.previous_misconception_type,
                "current_misconception_type": row.current_misconception_type,
                "is_same_type": row.is_same_type,
                "phase": row.phase,
                "created_at": _iso(row.created_at),
            }
            for row in recurrences
        ],
        "ai_call_logs": [
            {
                "id": row.id,
                "provider": row.provider,
                "purpose": row.purpose,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "request_payload": row.request_payload,
                "response_payload": row.response_payload,
                "created_at": _iso(row.created_at),
            }
            for row in ai_logs
        ],
        "latest_evaluation_summary": None
        if not summary
        else {
            "pretest_score": summary.pretest_score,
            "retest_score": summary.retest_score,
            "l0_correct_rate": summary.l0_correct_rate,
            "same_misconception_recurrence_rate": summary.same_misconception_recurrence_rate,
            "m1_recurrence_rate": summary.m1_recurrence_rate,
            "m2_recurrence_rate": summary.m2_recurrence_rate,
            "m3_recurrence_rate": summary.m3_recurrence_rate,
            "learning_target_count": summary.learning_target_count,
            "completed": summary.completed,
            "created_at": _iso(summary.created_at),
        },
    }


LOG_CSV_COLUMNS = [
    "record_type",
    "source_type",
    "participant_id",
    "display_code",
    "phase",
    "term_slug",
    "event_time",
    "question_shown_at",
    "answered_at",
    "response_time_sec",
    "question_body",
    "selected_option_body",
    "question_body_snapshot",
    "option_order_snapshot",
    "summary",
    "value_json",
]


def _csv_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _log_csv_rows_from_participant_logs(logs: dict[str, Any]) -> list[dict[str, Any]]:
    participant = logs["participant"]
    rows: list[dict[str, Any]] = []
    base = {"participant_id": participant["participant_id"], "display_code": participant["display_code"]}
    for answer in logs["answer_history"]:
        if answer["source_type"] == "test_attempt":
            summary = f"{answer['term_label']} {answer['phase']} correct={answer['is_correct']} m={answer['misconception_type']}"
        else:
            summary = f"{answer['term_label']} learning turn {answer['turn_index']} stage={answer['learning_stage']} component={answer['component_term']} sufficient={answer['is_sufficient']} strategy={answer['teaching_strategy']}"
        rows.append({**base, "record_type": "answer", "source_type": answer["source_type"], "phase": answer["phase"], "term_slug": answer["term_slug"], "event_time": _answer_event_time(answer), "question_shown_at": answer.get("question_shown_at"), "answered_at": answer.get("answered_at"), "response_time_sec": answer.get("response_time_sec"), "question_body": answer.get("question_body"), "selected_option_body": answer.get("selected_option_body"), "question_body_snapshot": answer.get("question_body_snapshot"), "option_order_snapshot": _csv_value(answer.get("option_order_snapshot")), "summary": summary, "value_json": _csv_value(answer)})
    for state in logs["learner_states"]:
        rows.append({**base, "record_type": "learner_state", "phase": "state", "term_slug": state["term_slug"], "event_time": state["updated_at"], "summary": f"{state['term_label']} status={state['current_status']} stage={state['current_stage_for_display']} strategy={state['teaching_strategy']}", "value_json": _csv_value(state)})
    for session in logs["tutor_sessions"]:
        rows.append({**base, "record_type": "tutor_session", "phase": "learning", "term_slug": session["term_slug"], "event_time": session["started_at"], "summary": f"{session['term_label']} session {session['session_index']}", "value_json": _csv_value({k: v for k, v in session.items() if k != "turns"})})
    for event in logs["recurrence_events"]:
        rows.append({**base, "record_type": "recurrence", "phase": event["phase"], "term_slug": event["term_slug"], "event_time": event["created_at"], "summary": f"{event['previous_misconception_type']} -> {event['current_misconception_type']}", "value_json": _csv_value(event)})
    for call in logs["ai_call_logs"]:
        rows.append({**base, "record_type": "ai_call", "phase": "", "term_slug": "", "event_time": call["created_at"], "summary": f"{call['purpose']} {call['status']} {call['error_code'] or ''}".strip(), "value_json": _csv_value(call)})
    if logs["latest_evaluation_summary"]:
        rows.append({**base, "record_type": "evaluation_summary", "phase": "summary", "term_slug": "", "event_time": logs["latest_evaluation_summary"]["created_at"], "summary": "latest evaluation summary", "value_json": _csv_value(logs["latest_evaluation_summary"])})
    return rows


def _write_log_csv(path: Path, rows: list[dict[str, Any]], *, encoding: str) -> Path:
    with path.open("w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=LOG_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_participant_logs_csv(db: Session, participant_id: str) -> Path:
    logs = participant_logs(db, participant_id)
    participant = logs["participant"]
    path = Path(get_settings().export_dir) / f"{participant['display_code']}_logs.csv"
    rows = _log_csv_rows_from_participant_logs(logs)
    return _write_log_csv(path, rows, encoding="utf-8")


def export_participant_logs_excel_csv(db: Session, participant_id: str) -> Path:
    logs = participant_logs(db, participant_id)
    participant = logs["participant"]
    path = Path(get_settings().export_dir) / f"{participant['display_code']}_logs_excel.csv"
    rows = _log_csv_rows_from_participant_logs(logs)
    return _write_log_csv(path, rows, encoding="utf-8-sig")


def export_overview_logs_csv(db: Session) -> Path:
    path = Path(get_settings().export_dir) / "overview.csv"
    rows: list[dict[str, Any]] = []
    for participant in db.query(Participant).order_by(Participant.created_at).all():
        rows.extend(_log_csv_rows_from_participant_logs(participant_logs(db, participant.id)))
    return _write_log_csv(path, rows, encoding="utf-8")


def export_overview_logs_excel_csv(db: Session) -> Path:
    path = Path(get_settings().export_dir) / "overview_excel.csv"
    rows: list[dict[str, Any]] = []
    for participant in db.query(Participant).order_by(Participant.created_at).all():
        rows.extend(_log_csv_rows_from_participant_logs(participant_logs(db, participant.id)))
    return _write_log_csv(path, rows, encoding="utf-8-sig")


def export_csv(db: Session, name: str) -> Path:
    if name not in EXPORTS:
        raise HTTPException(status_code=404, detail="unknown export")
    model, columns = EXPORTS[name]
    path = Path(get_settings().export_dir) / f"{name}.csv"
    rows = db.query(model).all()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: getattr(row, col) for col in columns})
    db.add(ExportJob(export_name=name, file_path=str(path), status="success", row_count=len(rows)))
    db.commit()
    return path
