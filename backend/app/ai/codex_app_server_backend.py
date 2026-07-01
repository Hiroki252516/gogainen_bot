from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable

import websockets

from app.core.config import get_settings


class CodexAppServerError(RuntimeError):
    def __init__(self, code: str, user_message: str, detail: str | None = None) -> None:
        super().__init__(detail or user_message)
        self.code = code
        self.user_message = user_message
        self.detail = detail or user_message


class _CodexRpcClient:
    def __init__(self, url: str, token_file: str | None, timeout_sec: int) -> None:
        self.url = url
        self.token_file = token_file
        self.timeout_sec = timeout_sec
        self._next_id = 1
        self._ws: Any = None

    async def __aenter__(self) -> "_CodexRpcClient":
        headers = self._auth_headers()
        self._ws = await websockets.connect(
            self.url,
            open_timeout=min(10, self.timeout_sec),
            ping_interval=None,
            additional_headers=headers or None,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._ws:
            await self._ws.close()

    def _auth_headers(self) -> list[tuple[str, str]]:
        if not self.token_file:
            return []
        token_path = Path(self.token_file)
        if not token_path.exists():
            raise CodexAppServerError(
                "auth_token_missing",
                "Codex app-serverの認証トークンファイルが見つかりません。",
                str(token_path),
            )
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise CodexAppServerError("auth_token_empty", "Codex app-serverの認証トークンが空です。")
        return [("Authorization", f"Bearer {token}")]

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        notification_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> Any:
        request_id = self._next_id
        self._next_id += 1
        request: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        await self._ws.send(json.dumps(request, ensure_ascii=False))

        while True:
            message = await self.recv(notification_handler)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexAppServerError("jsonrpc_error", f"Codex app-serverで `{method}` が失敗しました。", json.dumps(message["error"], ensure_ascii=False))
            return message.get("result")

    async def recv(self, notification_handler: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        raw = await asyncio.wait_for(self._ws.recv(), timeout=self.timeout_sec)
        message = json.loads(raw)
        if "id" in message and "method" in message:
            await self._reject_server_request(message)
        elif notification_handler and "method" in message:
            notification_handler(message)
        return message

    async def _reject_server_request(self, message: dict[str, Any]) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": message["id"],
            "error": {"code": -32601, "message": f"Unsupported server request: {message.get('method')}"},
        }
        await self._ws.send(json.dumps(response, ensure_ascii=False))


class CodexAppServerBackend:
    provider = "codex_app_server"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def status(self) -> dict[str, Any]:
        try:
            async with self._client() as rpc:
                await self._initialize(rpc)
                account_result = await rpc.call("account/read", {"refreshToken": False})
            account = account_result.get("account") if isinstance(account_result, dict) else None
            return {
                "app_server_reachable": True,
                "logged_in": bool(account),
                "account_label": self._account_label(account),
                "plan_type": account.get("planType") if isinstance(account, dict) else None,
                "last_error": None,
            }
        except Exception as exc:  # pragma: no cover - depends on local app-server
            return {
                "app_server_reachable": False,
                "logged_in": False,
                "account_label": "Codex app-server",
                "plan_type": None,
                "last_error": str(exc),
            }

    async def start_login(self, login_type: str = "chatgpt") -> dict[str, Any]:
        if login_type not in {"chatgpt", "chatgptDeviceCode"}:
            raise CodexAppServerError("invalid_login_type", "ChatGPTログイン方式だけを利用できます。")
        async with self._client() as rpc:
            await self._initialize(rpc)
            params: dict[str, Any] = {"type": login_type}
            if login_type == "chatgpt":
                params["codexStreamlinedLogin"] = True
            return await rpc.call("account/login/start", params)

    async def cancel_login(self, login_id: str) -> dict[str, Any]:
        async with self._client() as rpc:
            await self._initialize(rpc)
            return await rpc.call("account/login/cancel", {"loginId": login_id})

    async def logout(self) -> dict[str, Any]:
        async with self._client() as rpc:
            await self._initialize(rpc)
            return await rpc.call("account/logout")

    async def diagnose_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "is_correct": {"type": "boolean"},
                "diagnosed_status": {"type": "string", "enum": ["misconception", "unknown", "unstable_correct", "stable_correct", "ambiguous"]},
                "misconception_type": {"type": ["string", "null"], "enum": ["M1", "M2", "M3", "M4", "unknown", None]},
                "secondary_misconception_type": {"type": ["string", "null"], "enum": ["M1", "M2", "M3", "M4", "unknown", None]},
                "diagnosis_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "natural_language_diagnosis": {"type": "string"},
                "evidence": {"type": "string"},
                "recommended_initial_scaffolding_level": {"type": "string", "enum": ["L0", "L1", "L2", "L3"]},
                "recommended_teaching_strategy": {"type": "string", "enum": _TEACHING_STRATEGIES},
                "requires_manual_review": {"type": "boolean"},
            },
            "required": [
                "is_correct",
                "diagnosed_status",
                "misconception_type",
                "secondary_misconception_type",
                "diagnosis_confidence",
                "natural_language_diagnosis",
                "evidence",
                "recommended_initial_scaffolding_level",
                "recommended_teaching_strategy",
                "requires_manual_review",
            ],
            "additionalProperties": False,
        }
        prompt = self._prompt(
            "pretest_diagnosis",
            payload,
            [
                "事前テストでは選択肢の正誤と内部選択肢ラベルから理解状態を診断する。reason_text と confidence が null の場合は欠損ではなく仕様通りとして扱う。",
                "正答選択肢なら diagnosed_status は stable_correct、recommended_initial_scaffolding_level は L1 にする。",
                "誤答または unknown なら recommended_initial_scaffolding_level は L3 にする。L4は使わない。",
                "誤概念タイプは内部研究ラベルとして M1/M2/M3/M4/unknown/null のみを使う。",
                "natural_language_diagnosis には M1/M2/M3/M4 という内部ラベルを絶対に書かない。",
                "統制群でも分類は保存してよいが、教授方略に使う推薦は general_explanation にする。",
                f"recommended_teaching_strategy は次の識別子だけから選ぶ: {', '.join(_TEACHING_STRATEGIES)}。",
            ],
        )
        result = await self._run_structured_turn("diagnose_answer", prompt, schema)
        if payload.get("group_condition") == "control":
            result["recommended_teaching_strategy"] = "general_explanation"
        result["natural_language_diagnosis"] = _strip_internal_labels(result["natural_language_diagnosis"])
        return result

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        group = payload.get("group_condition", "proposed")
        prompt_payload = payload if group == "proposed" else self._control_tutoring_payload(payload)
        schema = {
            "type": "object",
            "properties": {
                "tutor_message": {"type": "string"},
                "teaching_strategy": {"type": "string", "enum": _TEACHING_STRATEGIES},
                "scaffolding_level": {"type": "string", "enum": ["L0", "L1", "L2", "L3"]},
                "requires_learner_response": {"type": "boolean"},
                "learner_prompt": {"type": "string"},
                "practice_question": {
                    "type": "object",
                    "properties": {
                        "body": {"type": "string"},
                        "expected_answer": {"type": "string"},
                        "question_type": {"type": "string"},
                    },
                    "required": ["body", "expected_answer", "question_type"],
                    "additionalProperties": False,
                },
                "forbidden_help_given": {"type": "boolean"},
            },
            "required": [
                "tutor_message",
                "teaching_strategy",
                "scaffolding_level",
                "requires_learner_response",
                "learner_prompt",
                "practice_question",
                "forbidden_help_given",
            ],
            "additionalProperties": False,
        }
        rules = [
            "学習セッション用の短い日本語チュータ発話を作る。",
            "再テスト、L0確認、転移テストの具体的な正解を先取りして出さない。",
            "tutor_message, learner_prompt, practice_question.body に M1/M2/M3/M4 という内部ラベルを絶対に書かない。",
            "rag_context がある場合は教材コンテキストを優先し、教材にない内容は推測で断定しない。",
        ]
        if group == "control":
            rules.append("統制群なので、過去ログ、誤概念タイプ、足場掛け履歴に適応しない通常AIチューターとして説明する。teaching_strategy は general_explanation に固定する。")
        else:
            rules.append("提案群なので、誤概念タイプ、過去ログ、足場掛けレベルを教授方略へ反映する。")
        rules.append(f"teaching_strategy は次の識別子だけから選ぶ: {', '.join(_TEACHING_STRATEGIES)}。")
        result = await self._run_structured_turn("generate_tutoring_turn", self._prompt("tutoring_turn", prompt_payload, rules), schema)
        result["tutor_message"] = _strip_internal_labels(result["tutor_message"])
        result["learner_prompt"] = _strip_internal_labels(result["learner_prompt"])
        result["practice_question"]["body"] = _strip_internal_labels(result["practice_question"]["body"])
        if group == "control":
            result["teaching_strategy"] = "general_explanation"
        return result

    async def generate_prerequisite_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        group = payload.get("group_condition")
        prompt_payload = payload if group == "proposed" else self._control_learning_payload(payload)
        schema = {
            "type": "object",
            "properties": {
                "material": {"type": "string"},
                "examples": {"type": "array", "items": {"type": "string"}},
                "comparisons": {"type": "array", "items": {"type": "string"}},
                "counterexamples": {"type": "array", "items": {"type": "string"}},
                "rag_sources": {"type": "array", "items": {"type": "string"}},
                "general_knowledge_supplement": {"type": ["string", "null"]},
            },
            "required": ["material", "examples", "comparisons", "counterexamples", "rag_sources", "general_knowledge_supplement"],
            "additionalProperties": False,
        }
        rules = [
            "固定済みの前提用語について教材だけを生成する。問題文や選択肢は生成しない。",
            "例、比較、反例を使ってよい。教材の長さは理解に必要な範囲で判断する。",
            _LEARNER_MARKDOWN_RULE,
            "material は「要点」「具体例」「注意点」などの短い見出しと箇条書きを中心にする。",
            "未出題問題の正答文を推測して再現しない。",
            "rag_contextを優先し、一般知識を補足した場合はgeneral_knowledge_supplementへ分ける。",
            "M1/M2/M3/M4という内部ラベルを学習者向け文章に書かない。",
        ]
        if group == "control":
            rules.append("統制群なので事前診断、過去回答、累積誤概念、戻り履歴を利用しない。")
        else:
            rules.append("提案群なので、渡された事前診断と累積履歴を教材の焦点へ反映する。")
        result = await self._run_structured_turn(
            "generate_prerequisite_material",
            self._prompt("fixed_prerequisite_material", prompt_payload, rules),
            schema,
        )
        for key in ("material", "general_knowledge_supplement"):
            if result.get(key):
                result[key] = _strip_internal_labels(result[key])
        for key in ("examples", "comparisons", "counterexamples"):
            result[key] = [_strip_internal_labels(item) for item in result[key]]
        return result

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]:
        group = payload.get("group_condition")
        prompt_payload = payload if group == "proposed" else self._control_learning_payload(payload)
        schema = {
            "type": "object",
            "properties": {
                "feedback": {"type": "string"},
                "remediation_focus": {"type": "string"},
                "general_knowledge_supplement": {"type": ["string", "null"]},
            },
            "required": ["feedback", "remediation_focus", "general_knowledge_supplement"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "explain_selected_distractor",
            self._prompt(
                "selected_distractor_feedback",
                prompt_payload,
                [
                    "選択した説明のどこが対象概念と一致しないかを自然な日本語で説明する。",
                    _LEARNER_MARKDOWN_RULE,
                    "feedback は「どこが違うか」「見直す観点」を短い見出しと箇条書きで示す。",
                    "正答選択肢の本文、位置、正答そのものは教えない。",
                    "次に見直す観点を一つ以上示す。",
                    "M1/M2/M3/M4という内部ラベルを書かない。",
                ],
            ),
            schema,
        )
        return {
            key: _strip_internal_labels(value) if isinstance(value, str) else value
            for key, value in result.items()
        }

    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_correct_answer_summary",
            self._prompt(
                "correct_answer_summary",
                payload,
                [
                    "正答文をそのまま繰り返さず、学習上の要点を短く説明する。",
                    _LEARNER_MARKDOWN_RULE,
                    "summary は「今回の要点」だけを短く示す。",
                    "M1/M2/M3/M4という内部ラベルを書かない。",
                ],
            ),
            schema,
        )
        result["summary"] = _strip_internal_labels(result["summary"])
        return result

    async def generate_emergency_question_variant(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "body": {"type": "string"},
                "options": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "body": {"type": "string"},
                            "is_correct": {"type": "boolean"},
                            "misconception_type": {"type": ["string", "null"], "enum": ["M1", "M2", "M3", "unknown", None]},
                        },
                        "required": ["body", "is_correct", "misconception_type"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["body", "options"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_emergency_question_variant",
            self._prompt(
                "emergency_question_variant",
                payload,
                [
                    "固定問題バンクが枯渇した場合だけ使う追加5択問題を作る。",
                    "正答1件、M1、M2、M3、わからないを各1件にする。",
                    "既出問題と同じ文面を使わない。",
                    "選択肢本文へM1/M2/M3/M4という内部ラベルを書かない。",
                ],
            ),
            schema,
        )
        result["body"] = _strip_internal_labels(result["body"])
        for option in result["options"]:
            option["body"] = _strip_internal_labels(option["body"])
        return result

    async def generate_prerequisite_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "prerequisites": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "term_label": {"type": "string"},
                            "material": {"type": "string"},
                            "check_question": {"type": "string"},
                            "expected_answer": {"type": "string"},
                            "generation_reason": {"type": "string"},
                        },
                        "required": ["term_label", "material", "check_question", "expected_answer", "generation_reason"],
                        "additionalProperties": False,
                    },
                },
                "plan_rationale": {"type": "string"},
            },
            "required": ["prerequisites", "plan_rationale"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_prerequisite_plan",
            self._prompt(
                "prerequisite_plan",
                payload,
                [
                    "対象概念を理解するための前提用語をちょうど3件作る。",
                    "各前提用語について、短い教材、記述式確認質問、期待回答を日本語で作る。",
                    "pretest診断は提案群の支援方針にだけ使う。M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                ],
            ),
            schema,
        )
        for item in result["prerequisites"]:
            item["material"] = _strip_internal_labels(item["material"])
            item["check_question"] = _strip_internal_labels(item["check_question"])
            item["expected_answer"] = _strip_internal_labels(item["expected_answer"])
            item["generation_reason"] = _strip_internal_labels(item["generation_reason"])
        result["plan_rationale"] = _strip_internal_labels(result["plan_rationale"])
        return result

    async def generate_control_prerequisite_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        control_payload = self._control_learning_payload(payload)
        schema = {
            "type": "object",
            "properties": {
                "prerequisites": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "term_label": {"type": "string"},
                            "material": {"type": "string"},
                            "check_question": {"type": "string"},
                            "expected_answer": {"type": "string"},
                            "generation_reason": {"type": "string"},
                        },
                        "required": ["term_label", "material", "check_question", "expected_answer", "generation_reason"],
                        "additionalProperties": False,
                    },
                },
                "plan_rationale": {"type": "string"},
            },
            "required": ["prerequisites", "plan_rationale"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_control_prerequisite_plan",
            self._prompt(
                "control_prerequisite_plan",
                control_payload,
                [
                    "統制群用に、対象概念について一般的な確認小問をちょうど3件作る。",
                    "pretest診断、誤概念タイプ、過去ログ、戻り制御情報は使わない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                ],
            ),
            schema,
        )
        for item in result["prerequisites"]:
            item["material"] = _strip_internal_labels(item["material"])
            item["check_question"] = _strip_internal_labels(item["check_question"])
            item["expected_answer"] = _strip_internal_labels(item["expected_answer"])
            item["generation_reason"] = _strip_internal_labels(item["generation_reason"])
        result["plan_rationale"] = _strip_internal_labels(result["plan_rationale"])
        return result

    async def grade_prerequisite_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposed = payload.get("group_condition") == "proposed"
        schema = {
            "type": "object",
            "properties": {
                "is_passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "feedback": {"type": "string"},
                "remediation_material": {"type": ["string", "null"]},
                "core_elements_covered": {"type": "array", "items": {"type": "string"}},
                "major_errors": {"type": "array", "items": {"type": "string"}},
                "rubric_scores": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
            },
            "required": ["is_passed", "score", "feedback", "remediation_material", "core_elements_covered", "major_errors", "rubric_scores"],
            "additionalProperties": False,
        }
        if proposed:
            schema["properties"].update(_learning_diagnosis_properties())
            schema["required"].extend(_learning_diagnosis_required())
        result = await self._run_structured_turn(
            "grade_prerequisite_answer",
            self._prompt(
                "prerequisite_grading",
                payload,
                [
                    "前提用語理解の記述回答を採点する。",
                    "中核要素が含まれ重大な誤りがなければpassにする。",
                    "failなら、より簡単な再説明と具体例を remediation_material に書く。",
                    "提案群では回答対象の前提用語についてM1/M2/M3/unknown/ambiguous/resolvedを判定する。重大な誤概念があればpassにしない。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                ],
            ),
            schema,
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        if result.get("remediation_material"):
            result["remediation_material"] = _strip_internal_labels(result["remediation_material"])
        return result

    async def generate_concept_phase1_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "concept_material": {"type": "string"},
                "concept_prompt": {"type": "string"},
                "expected_answer": {"type": "string"},
            },
            "required": ["concept_material", "concept_prompt", "expected_answer"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_concept_phase1_material",
            self._prompt(
                "concept_phase1_material",
                payload,
                [
                    "前提用語または統制群小問を踏まえて、対象概念フェーズ1の教材を作る。",
                    "学習者に前提用語を使って対象概念を説明させるpromptを作る。",
                    "統制群payloadの場合はpretest診断や誤概念情報を使わず、一般説明にする。",
                    _LEARNER_MARKDOWN_RULE,
                    "concept_material は「要点」「前提用語とのつながり」「注意点」などの短い見出しと箇条書きを中心にする。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                ],
            ),
            schema,
        )
        return {key: _strip_internal_labels(value) for key, value in result.items()}

    async def generate_concept_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.generate_concept_phase1_material(payload)

    async def grade_concept_phase1_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposed = payload.get("group_condition") == "proposed"
        schema = {
            "type": "object",
            "properties": {
                "is_passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "feedback": {"type": "string"},
                "missing_prerequisite_labels": {"type": "array", "items": {"type": "string"}},
                "review_prerequisite_labels": {"type": "array", "items": {"type": "string"}},
                "core_elements_covered": {"type": "array", "items": {"type": "string"}},
                "major_errors": {"type": "array", "items": {"type": "string"}},
                "rubric_scores": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
                "confirmed_prerequisite_labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["is_passed", "score", "feedback", "missing_prerequisite_labels", "review_prerequisite_labels", "core_elements_covered", "major_errors", "rubric_scores", "confirmed_prerequisite_labels"],
            "additionalProperties": False,
        }
        if proposed:
            schema["properties"].update(_learning_diagnosis_properties())
            schema["required"].extend(_learning_diagnosis_required())
        result = await self._run_structured_turn(
            "grade_concept_phase1_answer",
            self._prompt(
                "concept_phase1_grading",
                payload,
                [
                    "教材あり概念理解フェーズ1の記述回答を採点する。",
                    "前提用語を使って対象概念の役割や仕組みを説明できていればpassにする。",
                    "提案群のfailなら不足している前提用語と、直前に確認すべき関連用語を返す。統制群では不足用語リストは空でもよい。",
                    "confirmed_prerequisite_labelsには回答中で意味のある形で正しく使われた前提用語だけを入れる。",
                    "提案群ではM1/M2/M3/unknown/ambiguous/resolvedを判定し、重大な誤概念があればpassにしない。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                ],
            ),
            schema,
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        return result

    async def grade_concept_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.grade_concept_phase1_answer(payload)

    async def generate_concept_phase2_prompt(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "phase2_prompt": {"type": "string"},
                "light_conditions": {"type": "string"},
                "expected_answer": {"type": "string"},
            },
            "required": ["phase2_prompt", "light_conditions", "expected_answer"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_concept_phase2_prompt",
            self._prompt(
                "concept_phase2_prompt",
                payload,
                [
                    "概念フェーズ2用に、教材本文なしで回答させる確認promptを作る。",
                    "light_conditions は軽い条件だけにし、教材本文や長い説明を含めない。",
                    "提案群payloadではphase1の結果を踏まえてよい。統制群payloadではRAGと対象概念だけを使う。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                ],
            ),
            schema,
        )
        return {key: _strip_internal_labels(value) for key, value in result.items()}

    async def grade_concept_phase2_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        proposed = payload.get("group_condition") == "proposed"
        schema = {
            "type": "object",
            "properties": {
                "is_passed": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "feedback": {"type": "string"},
                "independent_explanation_success": {"type": "boolean"},
                "return_to_phase1": {"type": "boolean"},
                "rubric_scores": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
            },
            "required": ["is_passed", "score", "feedback", "independent_explanation_success", "return_to_phase1", "rubric_scores"],
            "additionalProperties": False,
        }
        if proposed:
            schema["properties"].update(_learning_diagnosis_properties())
            schema["required"].extend(_learning_diagnosis_required())
        result = await self._run_structured_turn(
            "grade_concept_phase2_answer",
            self._prompt(
                "concept_phase2_grading",
                payload,
                [
                    "教材なし概念説明フェーズ2の回答を採点する。",
                    "対象概念の中核、前提用語の自然な利用、light_conditionsの充足、重大な誤りの有無で判断する。",
                    "提案群でfailなら return_to_phase1 を true にする。統制群は戻り制御を使わないが、採点結果としては true/false を返してよい。",
                    "提案群ではM1/M2/M3/unknown/ambiguous/resolvedを判定し、重大な誤概念があればpassにしない。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                ],
            ),
            schema,
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        return result

    async def generate_adaptive_support(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["remediation", "clarification"]},
                "feedback": {"type": "string"},
                "supplemental_material": {"type": ["string", "null"]},
                "next_check_question": {"type": "string"},
                "diagnostic_focus": {
                    "type": "object",
                    "properties": {
                        "core_elements": {"type": "array", "items": {"type": "string"}},
                        "M1_features": {"type": "array", "items": {"type": "string"}},
                        "M2_features": {"type": "array", "items": {"type": "string"}},
                        "M3_features": {"type": "array", "items": {"type": "string"}},
                        "unknown_criteria": {"type": "string"},
                    },
                    "required": ["core_elements", "M1_features", "M2_features", "M3_features", "unknown_criteria"],
                    "additionalProperties": False,
                },
                "rag_sources": {"type": "array", "items": {"type": "string"}},
                "general_knowledge_supplement": {"type": ["string", "null"]},
            },
            "required": [
                "mode",
                "feedback",
                "supplemental_material",
                "next_check_question",
                "diagnostic_focus",
                "rag_sources",
                "general_knowledge_supplement",
            ],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_adaptive_support",
            self._prompt(
                "adaptive_support",
                payload,
                [
                    "確定済みの誤概念診断と更新後状態に基づき、フィードバック、補助教材、別文面の次の確認質問を作る。",
                    "完成回答やそのまま提出できる模範回答は禁止する。観点、部分例、比較、反例だけを示す。",
                    "rag_contextを優先する。一般知識を補足した場合はgeneral_knowledge_supplementに分離する。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                ],
            ),
            schema,
        )
        for key in ["feedback", "supplemental_material", "next_check_question", "general_knowledge_supplement"]:
            if result.get(key):
                result[key] = _strip_internal_labels(result[key])
        return result

    async def generate_control_learning_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "tutor_message": {"type": "string"},
                "learner_prompt": {"type": "string"},
                "practice_question": {
                    "type": "object",
                    "properties": {
                        "body": {"type": "string"},
                        "expected_answer": {"type": "string"},
                    },
                    "required": ["body", "expected_answer"],
                    "additionalProperties": False,
                },
                "forbidden_help_given": {"type": "boolean"},
            },
            "required": ["tutor_message", "learner_prompt", "practice_question", "forbidden_help_given"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_control_learning_turn",
            self._prompt(
                "control_learning_turn",
                self._control_learning_payload(payload),
                [
                    "統制群用の通常AIチューターとして、一般的な説明と自己説明promptを作る。",
                    "過去ログ、誤概念タイプ、前提用語ゲートに基づく個別化は行わない。",
                    "rag_context を優先し、教材にない内容は断定しない。",
                    "再テストの正解や選択肢を直接教えない。",
                ],
            ),
            schema,
        )
        result["tutor_message"] = _strip_internal_labels(result["tutor_message"])
        result["learner_prompt"] = _strip_internal_labels(result["learner_prompt"])
        result["practice_question"]["body"] = _strip_internal_labels(result["practice_question"]["body"])
        return result

    async def grade_control_learning_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "feedback": {"type": "string"},
                "is_complete": {"type": "boolean"},
                "forbidden_help_given": {"type": "boolean"},
            },
            "required": ["feedback", "is_complete", "forbidden_help_given"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "grade_control_learning_answer",
            self._prompt(
                "control_learning_feedback",
                self._control_learning_payload(payload),
                [
                    "統制群の自己説明に一般的なフィードバックを返す。",
                    "誤概念タイプや過去ログに基づく個別化は行わない。",
                    "M1/M2/M3/M4という内部ラベルは学習者向け文面に書かない。",
                ],
            ),
            schema,
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        return result

    async def grade_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "is_correct": {"type": "boolean"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "misconception_type": {"type": ["string", "null"], "enum": ["M1", "M2", "M3", "M4", "unknown", None]},
                "secondary_misconception_type": {"type": ["string", "null"], "enum": ["M1", "M2", "M3", "M4", "unknown", None]},
                "diagnosed_status": {"type": "string", "enum": ["misconception", "unknown", "unstable_correct", "stable_correct", "ambiguous"]},
                "recurrence_flag": {"type": "boolean"},
                "l0_success": {"type": ["boolean", "null"]},
                "transfer_success": {"type": ["boolean", "null"]},
                "feedback_for_log": {"type": "string"},
                "evidence": {"type": "string"},
                "requires_manual_review": {"type": "boolean"},
            },
            "required": [
                "is_correct",
                "score",
                "misconception_type",
                "secondary_misconception_type",
                "diagnosed_status",
                "recurrence_flag",
                "l0_success",
                "transfer_success",
                "feedback_for_log",
                "evidence",
                "requires_manual_review",
            ],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "grade_response",
            self._prompt(
                "phase_grading",
                payload,
                [
                    "再テスト、L0確認、転移テストの回答を採点する。",
                    "学習者には即時正解やヒントを出さない前提なので、feedback_for_log は管理・分析ログ用に短く書く。",
                    "転移テストで文脈適用に失敗している場合は misconception_type を M4 にする。",
                ],
            ),
            schema,
        )
        result["feedback_for_log"] = _strip_internal_labels(result["feedback_for_log"])
        return result

    async def generate_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "feedback": {"type": "string"},
                "next_action": {"type": "string", "enum": ["continue", "move_next"]},
                "next_scaffolding_level": {"type": "string", "enum": ["L0", "L1", "L2", "L3"]},
                "strategy_changed": {"type": "boolean"},
                "state_update_reason": {"type": "string"},
            },
            "required": ["feedback", "next_action", "next_scaffolding_level", "strategy_changed", "state_update_reason"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_feedback",
            self._prompt(
                "learning_feedback",
                payload,
                [
                    "学習セッション中の自己説明に対して、日本語で短くフィードバックする。",
                    "rag_context がある場合は教材コンテキストを優先し、教材にない内容は推測で断定しない。",
                    "M1/M2/M3/M4 という内部ラベルを学習者向け文面に絶対に書かない。",
                    "理解が十分なら move_next、不十分なら continue にする。",
                ],
            ),
            schema,
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        result["state_update_reason"] = _strip_internal_labels(result["state_update_reason"])
        return result

    async def summarize_learner_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "summary_for_admin": {"type": "string"},
                "summary_for_learner": {"type": "string"},
                "risk_flags": {"type": "array", "items": {"type": "string"}},
                "recommended_next_focus": {"type": "string"},
            },
            "required": ["summary_for_admin", "summary_for_learner", "risk_flags", "recommended_next_focus"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "summarize_learner_state",
            self._prompt(
                "learner_state_summary",
                payload,
                [
                    "管理者用と学習者用の短い状態要約を作る。",
                    "学習者用要約には M1/M2/M3/M4 という内部ラベルを絶対に書かない。",
                ],
            ),
            schema,
        )
        result["summary_for_learner"] = _strip_internal_labels(result["summary_for_learner"])
        return result

    def _client(self) -> _CodexRpcClient:
        return _CodexRpcClient(
            self.settings.codex_app_server_url,
            self.settings.codex_ws_token_file,
            self.settings.codex_turn_timeout_sec,
        )

    async def _initialize(self, rpc: _CodexRpcClient) -> None:
        await rpc.call(
            "initialize",
            {
                "clientInfo": {
                    "name": "learning_log_ai_tutor",
                    "title": "Learning Log AI Tutor",
                    "version": "0.1.0",
                },
                "capabilities": {},
            },
        )

    async def _ensure_logged_in(self, rpc: _CodexRpcClient) -> dict[str, Any]:
        account_result = await rpc.call("account/read", {"refreshToken": False})
        account = account_result.get("account") if isinstance(account_result, dict) else None
        if not account:
            raise CodexAppServerError("not_logged_in", "Codex app-serverでChatGPT/Codexログインが確認できません。")
        return account

    async def _run_structured_turn(self, purpose: str, prompt: str, output_schema: dict[str, Any]) -> dict[str, Any]:
        text_chunks: list[str] = []
        completed_texts: list[str] = []
        turn_id: str | None = None

        def on_event(message: dict[str, Any]) -> None:
            method = message.get("method")
            params = message.get("params") or {}
            event_turn_id = params.get("turnId") or (params.get("turn") or {}).get("id")
            if turn_id and event_turn_id and event_turn_id != turn_id:
                return
            if method in {"item/agentMessage/delta", "agent/message/delta"}:
                text_chunks.append(params.get("delta", ""))
            if method == "item/completed":
                item = params.get("item") or {}
                if item.get("type") == "agentMessage" and item.get("text"):
                    completed_texts.append(item["text"])
            if method == "error":
                raise CodexAppServerError("turn_failed", "Codex app-serverからエラー通知が返りました。", json.dumps(params, ensure_ascii=False))

        try:
            async with self._client() as rpc:
                await self._initialize(rpc)
                await self._ensure_logged_in(rpc)
                thread = await rpc.call(
                    "thread/start",
                    {
                        "ephemeral": True,
                        "cwd": self.settings.codex_app_server_cwd,
                        "approvalPolicy": "never",
                        "sandbox": "read-only",
                        "baseInstructions": _BASE_INSTRUCTIONS,
                        "model": self.settings.codex_model or None,
                    },
                    notification_handler=on_event,
                )
                thread_id = thread["thread"]["id"]
                turn = await rpc.call(
                    "turn/start",
                    {
                        "threadId": thread_id,
                        "input": [{"type": "text", "text": prompt}],
                        "outputSchema": output_schema,
                        "approvalPolicy": "never",
                        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                        "model": self.settings.codex_model or None,
                        "effort": self.settings.codex_reasoning_effort,
                    },
                    notification_handler=on_event,
                )
                turn_id = turn["turn"]["id"]
                while True:
                    message = await rpc.recv(on_event)
                    if message.get("method") != "turn/completed":
                        continue
                    completed_turn = (message.get("params") or {}).get("turn") or {}
                    if completed_turn.get("id") != turn_id:
                        continue
                    if completed_turn.get("status") == "failed":
                        raise CodexAppServerError("turn_failed", "Codex app-serverのAI応答生成が失敗しました。", json.dumps(completed_turn.get("error"), ensure_ascii=False))
                    break
        except asyncio.TimeoutError as exc:
            raise CodexAppServerError("timeout", "Codex app-serverのAI応答がタイムアウトしました。", purpose) from exc
        except OSError as exc:
            raise CodexAppServerError("app_server_unreachable", "Codex app-serverに接続できません。", str(exc)) from exc

        raw_text = (completed_texts[-1] if completed_texts else "".join(text_chunks)).strip()
        if not raw_text:
            raise CodexAppServerError("empty_response", "Codex app-serverから空のAI応答が返りました。")
        return _parse_json_object(raw_text)

    def _prompt(self, purpose: str, payload: dict[str, Any], rules: list[str]) -> str:
        return "\n".join(
            [
                f"目的: {purpose}",
                "",
                "出力は指定JSON Schemaに一致するJSONオブジェクトのみ。Markdown、説明文、コードブロックは禁止。",
                "個人情報、APIキー、アクセストークン、認証情報を要求・保存・推測しない。",
                "被験者に見える文面では内部研究ラベル M1/M2/M3/M4 を使わない。",
                "",
                "追加ルール:",
                *[f"- {rule}" for rule in rules],
                "",
                "入力JSON:",
                json.dumps(payload, ensure_ascii=False, indent=2),
            ]
        )

    def _control_tutoring_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        return {
            "participant_id": payload.get("participant_id"),
            "group_condition": "control",
            "term": term,
            "learner_state": {
                "current_status": (payload.get("learner_state") or {}).get("current_status"),
                "scaffolding_level": (payload.get("learner_state") or {}).get("scaffolding_level"),
                "teaching_strategy": "general_explanation",
            },
            "rag_context": payload.get("rag_context"),
        }

    def _control_learning_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "participant_id": payload.get("participant_id"),
            "group_condition": "control",
            "target_term": payload.get("target_term"),
            "fixed_prerequisite": payload.get("fixed_prerequisite"),
            "focus_label": payload.get("focus_label"),
            "material_mode": payload.get("material_mode"),
            "cycle_index": payload.get("cycle_index"),
            "stage": payload.get("stage"),
            "slot_key": payload.get("slot_key"),
            "attempt_index": payload.get("attempt_index"),
            "question_body": payload.get("question_body"),
            "selected_option_body": payload.get("selected_option_body"),
            "existing_question_bodies": payload.get("existing_question_bodies"),
            "tutor_turn": payload.get("tutor_turn"),
            "learner_response": payload.get("learner_response"),
            "rag_context": payload.get("rag_context"),
        }

    def _account_label(self, account: dict[str, Any] | None) -> str:
        if not account:
            return "未ログイン"
        if account.get("type") == "chatgpt":
            plan = account.get("planType") or "unknown"
            return f"ChatGPTログイン済み ({plan})"
        return f"{account.get('type', 'unknown')} account"


_BASE_INSTRUCTIONS = """
You are the AI engine for a Japanese research prototype called Learning Log AI Tutor.
You must act only as a structured-output educational diagnosis and tutoring assistant.
Never modify files, run tools, browse, ask for API keys, or request authentication secrets.
Return only the JSON object requested by the caller's output schema.
""".strip()

_TEACHING_STRATEGIES = [
    "general_explanation",
    "category_reorientation",
    "boundary_comparison",
    "deep_structure_focus",
    "context_transfer_training",
    "foundational_explanation",
    "self_explanation_check",
    "diagnostic_clarification",
    "fading",
]

_LEARNER_MARKDOWN_RULE = (
    "学習者に表示する文章は日本語Markdownで返す。使える形式は ## 見出し、- 箇条書き、"
    "**太字**、短い段落だけ。表、HTML、コードブロック、長大な連続段落は禁止する。"
)


def _learning_diagnosis_properties() -> dict[str, Any]:
    return {
        "diagnosed_status": {
            "type": "string",
            "enum": ["misconception", "unknown", "ambiguous", "resolved"],
        },
        "primary_misconception_type": {
            "type": ["string", "null"],
            "enum": ["M1", "M2", "M3", "unknown", None],
        },
        "secondary_misconception_type": {
            "type": ["string", "null"],
            "enum": ["M1", "M2", "M3", None],
        },
        "diagnosis_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "diagnosis_evidence": {"type": "string"},
        "recommended_strategy": {"type": "string", "enum": _TEACHING_STRATEGIES},
        "strategy_override": {"type": "boolean"},
        "strategy_override_reason": {"type": ["string", "null"]},
        "requires_manual_review": {"type": "boolean"},
    }


def _learning_diagnosis_required() -> list[str]:
    return [
        "diagnosed_status",
        "primary_misconception_type",
        "secondary_misconception_type",
        "diagnosis_confidence",
        "diagnosis_evidence",
        "recommended_strategy",
        "strategy_override",
        "strategy_override_reason",
        "requires_manual_review",
    ]


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise CodexAppServerError("schema_validation_failed", "AI出力からJSONオブジェクトを抽出できませんでした。", raw_text)
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise CodexAppServerError("schema_validation_failed", "AI出力がJSONオブジェクトではありません。", raw_text)
    return value


def _strip_internal_labels(text: str) -> str:
    return re.sub(r"\bM[1-4]\b", "内部分類", text or "")
