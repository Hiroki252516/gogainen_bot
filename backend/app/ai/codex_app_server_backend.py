from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

import websockets

from app.core.config import get_settings
from app.core.runtime_config import normalize_reasoning_effort
from app.ai.mandatory_elements import (
    expected_mandatory_type,
    mandatory_element_prompt,
    mandatory_element_headings,
    mandatory_elements_schema,
    reconcile_mandatory_elements,
)
from app.ai.misconception_taxonomy import TAXONOMY_VERSION
from app.ai.teaching_contract import (
    MATERIAL_MAX_CHARACTERS,
    MATERIAL_MIN_CHARACTERS,
    MATERIAL_TARGET_CHARACTERS,
    PROMPT_CONTRACT_VERSION,
    reconcile_teaching_contract,
    teaching_contract_schema,
)


class CodexAppServerError(RuntimeError):
    def __init__(
        self,
        code: str,
        user_message: str,
        detail: str | None = None,
        *,
        raw_text: str | None = None,
        request_audit: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or user_message)
        self.code = code
        self.user_message = user_message
        self.detail = detail or user_message
        self.raw_text = raw_text
        self.request_audit = request_audit


class _StructuredModelResponse(dict):
    """Parsed model output that retains its exact app-server text for audit logs."""

    def __init__(self, value: dict[str, Any], raw_text: str, request_audit: dict[str, Any]) -> None:
        super().__init__(value)
        self.raw_text = raw_text
        self.request_audit = request_audit


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
        on_sent: Callable[[], None] | None = None,
    ) -> Any:
        request_id = self._next_id
        self._next_id += 1
        request: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        await self._ws.send(json.dumps(request, ensure_ascii=False))
        if on_sent:
            on_sent()

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

    def __init__(self, reasoning_effort: str | None = None) -> None:
        self.settings = get_settings()
        configured_effort = reasoning_effort or self.settings.codex_reasoning_effort
        self.reasoning_effort = normalize_reasoning_effort(configured_effort)

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
                "recommended_initial_scaffolding_level": {"type": "string", "enum": ["L2", "L3"]},
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
                "事前テスト診断では選択肢の正誤と誤答選択肢の初期ラベルだけから理解状態を診断する。",
                "natural_language_diagnosis では、入力欄の有無や未入力であることに絶対に触れず、選択内容から見える理解状態だけを書く。",
                "誤概念タイプの内部ラベルは、入力payloadのtaxonomy定義に従う。M1〜M4は学習者向け文面に出さない。",
                "natural_language_diagnosis には M1〜M4 という内部ラベルを絶対に書かない。",
                f"recommended_teaching_strategy は次の識別子だけから選ぶ: {', '.join(_TEACHING_STRATEGIES)}。",
            ],
        )
        result = await self._run_structured_turn(
            "diagnose_answer", prompt, schema, audit_context=self._audit_context(payload)
        )
        if payload.get("group_condition") == "control":
            result["recommended_teaching_strategy"] = "general_explanation"
        result["natural_language_diagnosis"] = _strip_pretest_input_mentions(_strip_internal_labels(result["natural_language_diagnosis"]))
        return result

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        group = payload.get("group_condition", "proposed")
        expected_type = (
            expected_mandatory_type({**payload, "group_condition": group})
            if group == "proposed"
            else None
        )
        prompt_payload = (
            self._proposed_tutoring_payload(payload)
            if group == "proposed"
            else self._control_tutoring_payload(payload)
        )
        if group == "proposed" and expected_type == "unknown":
            # Prevent stale M1/M3 observations from becoming an unknown learner's target.
            prompt_payload = {
                **prompt_payload,
                "pretest_target": None,
                "pretest_targets": [],
                "diagnostic_evidence": {
                    **(prompt_payload.get("diagnostic_evidence") or {}),
                    "pretest_targets": [],
                },
            }
        schema = {
            "type": "object",
            "properties": {
                "tutor_message": {"type": "string"},
                "teaching_strategy": {"type": "string", "enum": _TEACHING_STRATEGIES},
            },
            "required": ["tutor_message", "teaching_strategy"],
            "additionalProperties": False,
        }
        if expected_type:
            schema["properties"]["mandatory_elements"] = mandatory_elements_schema(expected_type)
            schema["required"].append("mandatory_elements")
            schema["properties"]["teaching_contract"] = teaching_contract_schema()
            schema["required"].append("teaching_contract")
        term_label = (payload.get("term") or {}).get("label", "この用語")
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
        material_length_retry = payload.get("material_length_retry")
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
        if prompt_payload.get("mandatory_element_retry"):
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
        rules.append(f"teaching_strategy は次の識別子だけから選ぶ: {', '.join(_TEACHING_STRATEGIES)}。")
        result = await self._run_structured_turn(
            "generate_tutoring_turn",
            self._prompt("tutoring_turn", prompt_payload, rules),
            schema,
            # Audit metadata comes from the full request; model input stays allowlisted.
            audit_context=self._audit_context(payload, generation=True),
        )
        result["tutor_message"] = _strip_internal_labels(result["tutor_message"])
        if isinstance(result.get("teaching_contract"), dict):
            for field in ("corrected_claim", "mechanism_explanation", "contrast_example", "transfer_check"):
                if isinstance(result["teaching_contract"].get(field), str):
                    result["teaching_contract"][field] = _strip_internal_labels(result["teaching_contract"][field])
        result = reconcile_mandatory_elements(result, expected_type)
        result = reconcile_teaching_contract(result, expected_type)
        if group == "control":
            result["teaching_strategy"] = "general_explanation"
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
                    "再テスト、確認テストの回答を採点する。",
                    "学習者には即時正解やヒントを出さない前提なので、feedback_for_log は管理・分析ログ用に短く書く。",
                ],
            ),
            schema,
            audit_context=self._audit_context(payload),
        )
        result["feedback_for_log"] = _strip_internal_labels(result["feedback_for_log"])
        return result

    async def generate_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "feedback": {"type": "string"},
                "is_sufficient": {"type": "boolean"},
                "next_action": {"type": "string", "enum": ["continue", "move_next"]},
                "next_scaffolding_level": {"type": "string", "enum": ["L2", "L3"]},
                "learning_misconception_type": {"type": ["string", "null"], "enum": ["M1", "M2", "M3", "M4", "unknown", None]},
                "learning_misconception_confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "learning_misconception_reason": {"type": "string"},
                "strategy_changed": {"type": "boolean"},
                "state_update_reason": {"type": "string"},
            },
            "required": ["feedback", "is_sufficient", "next_action", "next_scaffolding_level", "learning_misconception_type", "learning_misconception_confidence", "learning_misconception_reason", "strategy_changed", "state_update_reason"],
            "additionalProperties": False,
        }
        result = await self._run_structured_turn(
            "generate_feedback",
            self._prompt(
                "learning_feedback",
                payload,
                [
                    "学習セッション中の自己説明に対して、日本語で短くフィードバックする。",
                    "feedback は安全なMarkdownとして返す。複数の観点を含める場合は箇条書きにし、長い一段落にしない。重要語は **太字** にしてよい。",
                    "feedback では見出しを必須にしないが、見出し、箇条書き、太字、短い段落だけを使う。表、HTML、コードブロック、画像、長大な連続段落は使わない。",
                    "rag_context.chunks がある場合は、その教材コンテキストを優先して判定・フィードバックする。教材にない内容は推測で断定しない。",
                    "M1〜M4 という内部ラベルを学習者向け文面に絶対に書かない。",
                    "learning_misconception_type は、この学習セッション内の今回回答だけに対する内部診断として入力payloadのtaxonomyに従って選ぶ。事前テスト由来の primary_misconception を上書きしない。",
                    "十分回答なら learning_misconception_type は null にしてよい。不十分な場合は、taxonomyの診断cueと教授方略に沿ってM1〜M4またはunknownを選ぶ。",
                    "learning_misconception_reason は研究者向けログ用に短く書き、学習者向けfeedbackには内部ラベルを書かない。",
                    "learning_stage が enrichment の場合、知識不足を補う観点で十分性を判定する。",
                    "learning_stage が conceptual_change の場合、誤った捉え方から正しいカテゴリー・構造へ移行できているかを判定する。",
                    "理解が十分なら move_next、不十分なら continue にする。",
                    "next_scaffolding_level は参考値として L3/L2 のいずれかにし、指定外のレベルは使わない。最終更新はbackendが決める。",
                ],
            ),
            schema,
            audit_context=self._audit_context(payload),
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        result["learning_misconception_reason"] = _strip_internal_labels(result["learning_misconception_reason"])
        result["state_update_reason"] = _strip_internal_labels(result["state_update_reason"])
        return result

    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }
        prompt_payload = (
            self._proposed_feedback_payload(payload)
            if payload.get("group_condition") == "proposed"
            else self._control_feedback_payload(payload)
        )
        result = await self._run_structured_turn(
            "generate_correct_answer_summary",
            self._prompt(
                "correct_answer_summary",
                prompt_payload,
                [
                    "固定YAMLの採点結果は正答済みである。正答選択肢の本文をそのまま繰り返さず、学習上の要点だけを短く説明する。",
                    "summary は学習者向けの安全なMarkdownにする。冒頭に ## 今回の要点 を置き、箇条書き、**太字**、短い段落だけを使う。",
                    "HTML、表、コードブロック、画像、長大な連続段落は使わない。",
                    "rag_context.chunks がある場合はその本文を優先し、本文にない内容を推測で断定しない。",
                    "M1〜M4、unknown、taxonomy、足場掛け、研究者向け診断、AIの思考過程を出力しない。",
                    "summary には学習者の個人情報や内部識別子を含めない。",
                ],
            ),
            schema,
            audit_context=self._audit_context(payload),
        )
        result["summary"] = _strip_internal_labels(result["summary"])
        return result

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        prompt_payload = (
            self._proposed_feedback_payload(payload)
            if payload.get("group_condition") == "proposed"
            else self._control_feedback_payload(payload)
        )
        result = await self._run_structured_turn(
            "explain_selected_distractor",
            self._prompt(
                "selected_distractor_feedback",
                prompt_payload,
                [
                    "固定YAMLの採点結果は不正解である。選択された説明の問題点と、教材を見直す観点だけを説明する。",
                    "正答の選択肢本文、正答位置、正答そのものを直接示さない。",
                    "feedback は ## どこが違うか と ## 見直す観点を中心に、箇条書き、**太字**、短い段落だけを使う安全なMarkdownにする。",
                    "remediation_focus は学習者が次に確認する観点を一文で返し、general_knowledge_supplement は追加説明が不要なら null にする。",
                    "taxonomyや誤概念タイプが入力されている場合は教授方略の判断に使うが、M1〜M4などのラベルを出力しない。",
                    "HTML、表、コードブロック、画像、長大な連続段落、AIの思考過程は出力しない。",
                    "rag_context.chunks がある場合はその本文を優先し、本文にない内容を推測で断定しない。",
                    "選択内容が空なら、前提知識不足として定義と判断基準の確認を促す。",
                ],
            ),
            schema,
            audit_context=self._audit_context(payload),
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        result["remediation_focus"] = _strip_internal_labels(result["remediation_focus"])
        if result.get("general_knowledge_supplement"):
            result["general_knowledge_supplement"] = _strip_internal_labels(result["general_knowledge_supplement"])
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
                    "学習者用要約には M1〜M4 という内部ラベルを絶対に書かない。",
                ],
            ),
            schema,
            audit_context=self._audit_context(payload),
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

    async def _run_structured_turn(
        self,
        purpose: str,
        prompt: str,
        output_schema: dict[str, Any],
        *,
        audit_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text_chunks: list[str] = []
        completed_texts: list[str] = []
        turn_id: str | None = None
        thread_start_params = {
            "ephemeral": True,
            "cwd": self.settings.codex_app_server_cwd,
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "baseInstructions": _BASE_INSTRUCTIONS,
            "model": self.settings.codex_model or None,
        }
        turn_start_params: dict[str, Any] = {
            "threadId": None,
            "input": [{"type": "text", "text": prompt}],
            "outputSchema": output_schema,
            "approvalPolicy": "never",
            "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
            "model": self.settings.codex_model or None,
            "effort": self.reasoning_effort,
        }
        audit = {
            "purpose": purpose,
            "thread_start_method": "thread/start",
            "turn_start_method": "turn/start",
            "prompt_contract_version": (audit_context or {}).get("prompt_contract_version"),
            "taxonomy_version": (audit_context or {}).get("taxonomy_version"),
            "generation_attempt": (audit_context or {}).get("generation_attempt"),
            "model": self.settings.codex_model,
            "reasoning_effort": self.reasoning_effort,
            "thread_start_params": thread_start_params,
            "turn_start_params": turn_start_params,
            "prompt": prompt,
            "output_schema": output_schema,
            "output_schema_sha256": hashlib.sha256(
                json.dumps(output_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "rag_retrieval": (audit_context or {}).get("rag_retrieval"),
            "transmission": {
                "websocket_connected": False,
                "initialize_completed": False,
                "account_verified": False,
                "thread_start_attempted": False,
                "thread_start_sent": False,
                "thread_started": False,
                "thread_id": None,
                "turn_start_attempted": False,
                "turn_start_sent": False,
                "turn_started": False,
                "turn_id": None,
                "turn_completed": False,
            },
        }

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
                audit["transmission"]["websocket_connected"] = True
                await self._initialize(rpc)
                audit["transmission"]["initialize_completed"] = True
                await self._ensure_logged_in(rpc)
                audit["transmission"]["account_verified"] = True

                def thread_sent() -> None:
                    audit["transmission"]["thread_start_sent"] = True

                audit["transmission"]["thread_start_attempted"] = True
                thread = await rpc.call(
                    "thread/start", thread_start_params,
                    notification_handler=on_event, on_sent=thread_sent,
                )
                thread_id = thread["thread"]["id"]
                audit["transmission"]["thread_started"] = True
                audit["transmission"]["thread_id"] = thread_id
                turn_start_params["threadId"] = thread_id

                def turn_sent() -> None:
                    audit["transmission"]["turn_start_sent"] = True

                audit["transmission"]["turn_start_attempted"] = True
                turn = await rpc.call(
                    "turn/start", turn_start_params,
                    notification_handler=on_event, on_sent=turn_sent,
                )
                turn_id = turn["turn"]["id"]
                audit["transmission"]["turn_started"] = True
                audit["transmission"]["turn_id"] = turn_id
                while True:
                    message = await rpc.recv(on_event)
                    if message.get("method") != "turn/completed":
                        continue
                    completed_turn = (message.get("params") or {}).get("turn") or {}
                    if completed_turn.get("id") != turn_id:
                        continue
                    audit["transmission"]["turn_completed"] = True
                    if completed_turn.get("status") == "failed":
                        raise CodexAppServerError("turn_failed", "Codex app-serverのAI応答生成が失敗しました。", json.dumps(completed_turn.get("error"), ensure_ascii=False))
                    break
        except asyncio.TimeoutError as exc:
            raise CodexAppServerError("timeout", "Codex app-serverのAI応答がタイムアウトしました。", purpose, request_audit=audit) from exc
        except OSError as exc:
            raise CodexAppServerError("app_server_unreachable", "Codex app-serverに接続できません。", str(exc), request_audit=audit) from exc
        except CodexAppServerError as exc:
            exc.request_audit = audit
            raise
        except Exception as exc:
            setattr(exc, "request_audit", audit)
            raise

        raw_text = completed_texts[-1] if completed_texts else "".join(text_chunks)
        if not raw_text.strip():
            raise CodexAppServerError(
                "empty_response", "Codex app-serverから空のAI応答が返りました。", raw_text=raw_text, request_audit=audit
            )
        try:
            parsed = _parse_json_object(raw_text)
        except CodexAppServerError as exc:
            exc.request_audit = audit
            raise
        return _StructuredModelResponse(parsed, raw_text, audit)

    def _prompt(self, purpose: str, payload: dict[str, Any], rules: list[str]) -> str:
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
        prompt_payload = self._remove_routing_metadata(payload)
        prompt_parts.extend(["", "入力JSON:", json.dumps(prompt_payload, ensure_ascii=False, indent=2)])
        return "\n".join(prompt_parts)

    def _remove_routing_metadata(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self._remove_routing_metadata(item)
                for key, item in value.items()
                if key not in {"participant_id", "group_condition", "participant_code"}
            }
        if isinstance(value, list):
            return [self._remove_routing_metadata(item) for item in value]
        return value

    def _audit_context(self, payload: dict[str, Any], *, generation: bool = False) -> dict[str, Any]:
        rag = payload.get("rag_context") or {}
        retry_attempt = (payload.get("mandatory_element_retry") or {}).get("attempt")
        attempt = payload.get("generation_attempt")
        if attempt is None:
            attempt = retry_attempt if retry_attempt is not None else 1
        return {
            "prompt_contract_version": payload.get("prompt_contract_version") or PROMPT_CONTRACT_VERSION,
            "taxonomy_version": payload.get("taxonomy_version") or (TAXONOMY_VERSION if payload.get("misconception_taxonomy") else None),
            "generation_attempt": attempt if generation else None,
            "rag_retrieval": {
                "source": rag.get("source"),
                "topic_slug": rag.get("topic_slug"),
                "query": rag.get("query"),
                "allowed_sections": rag.get("allowed_sections"),
                "chunks": [
                    {
                        "chunk_id": chunk.get("chunk_id"),
                        "text_sha256": hashlib.sha256(str(chunk.get("text") or "").encode("utf-8")).hexdigest(),
                    }
                    for chunk in rag.get("chunks") or []
                ],
            } if rag else None,
        }

    def _proposed_tutoring_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "term", "learning_stage", "learning_stage_label", "component_term", "component_index",
            "component_total", "component_terms", "prompt_contract_version", "taxonomy_version",
            "pretest_target", "pretest_targets", "learner_state", "previous_answer",
            "previous_diagnosis_for_learner", "previous_practice_question", "previous_learner_response",
            "previous_learning_misconception", "session_misconception_history",
            "misconception_scaffolding_guidance", "misconception_taxonomy", "active_misconception_type",
            "mandatory_teaching_elements", "diagnostic_evidence", "rag_context", "mandatory_element_retry",
        }
        return {key: payload[key] for key in allowed if key in payload}

    def _control_tutoring_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"term", "component_term", "component_index", "component_total", "component_terms", "rag_context"}
        return {key: payload[key] for key in allowed if key in payload}

    def _proposed_feedback_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "term", "learning_stage", "component_term", "question_body", "selected_option_body",
            "selected_option_bodies", "material", "rag_context", "learner_state",
            "learning_misconception_type", "misconception_scaffolding_guidance", "misconception_taxonomy",
            "session_misconception_history",
        }
        return {key: payload[key] for key in allowed if key in payload}

    def _control_feedback_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "term", "component_term", "question_body", "selected_option_body",
            "selected_option_bodies", "material", "rag_context",
        }
        return {key: payload[key] for key in allowed if key in payload}

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
    "belief_revision",
    "category_reorientation",
    "boundary_comparison",
    "deep_structure_focus",
    "context_transfer_training",
    "foundational_explanation",
    "self_explanation_check",
]


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise CodexAppServerError(
                "schema_validation_failed",
                "AI出力からJSONオブジェクトを抽出できませんでした。",
                raw_text,
                raw_text=raw_text,
            )
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise CodexAppServerError(
                "schema_validation_failed",
                "AI出力からJSONオブジェクトを抽出できませんでした。",
                raw_text,
                raw_text=raw_text,
            ) from exc
    if not isinstance(value, dict):
        raise CodexAppServerError(
            "schema_validation_failed",
            "AI出力がJSONオブジェクトではありません。",
            raw_text,
            raw_text=raw_text,
        )
    return value


def _strip_internal_labels(text: str) -> str:
    cleaned = re.sub(r"(?<![A-Za-z0-9])M[1-4](?![A-Za-z0-9])", "内部分類", text or "")
    return re.sub(
        r"(?m)(^|。|\n)\s*(?:target_claim_id|addressed_claim_ids|refutation_mode|corrected_claim|mechanism_explanation|contrast_example|transfer_check|mandatory_elements|definition|components|role|decision_criterion|positive_example|non_example|wrong_belief|correct_belief|counterexample|reason|wrong_category|correct_category|boundary_criterion)\s*[:：]\s*",
        r"\1",
        cleaned,
    )


def _strip_pretest_input_mentions(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないため、?", "", cleaned)
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないので、?", "", cleaned)
    cleaned = re.sub(r"理由記述や自信度", "回答内容", cleaned)
    cleaned = re.sub(r"理由記述", "回答内容", cleaned)
    cleaned = re.sub(r"自信度", "", cleaned)
    cleaned = re.sub(r"、{2,}", "、", cleaned)
    return cleaned.strip("、 ")
