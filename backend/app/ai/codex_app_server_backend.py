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
                "誤概念タイプは内部研究ラベルとして M1/M2/M3/M4/unknown/null のみを使う。",
                "natural_language_diagnosis には M1/M2/M3/M4 という内部ラベルを絶対に書かない。",
                "統制群でも分類は保存してよいが、教授方略に使う推薦は general_explanation にする。",
                f"recommended_teaching_strategy は次の識別子だけから選ぶ: {', '.join(_TEACHING_STRATEGIES)}。",
            ],
        )
        result = await self._run_structured_turn("diagnose_answer", prompt, schema)
        if payload.get("group_condition") == "control":
            result["recommended_teaching_strategy"] = "general_explanation"
        result["natural_language_diagnosis"] = _strip_pretest_input_mentions(_strip_internal_labels(result["natural_language_diagnosis"]))
        return result

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        group = payload.get("group_condition", "proposed")
        prompt_payload = payload if group == "proposed" else self._control_tutoring_payload(payload)
        schema = {
            "type": "object",
            "properties": {
                "tutor_message": {"type": "string"},
                "teaching_strategy": {"type": "string", "enum": _TEACHING_STRATEGIES},
                "scaffolding_level": {"type": "string", "enum": ["L2", "L3"]},
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
        term_label = (payload.get("term") or {}).get("label", "この用語")
        rules = [
            "学習セッション用の短い日本語チュータ発話を作る。",
            "足場掛けレベルは L3/L2 のみを使い、指定外のレベルは使わない。",
            f"教材、問い返し、practice_question は必ず現在の用語『{term_label}』だけを主題にする。",
            "入力JSONの learning_stage が term_understanding の場合は、component_terms と fixed_practice_question_items に含まれる複数構成用語を今回の主題にし、それぞれの教材観点を説明する。",
            "入力JSONの learning_stage が concept_understanding の場合は、component_terms を使って対象概念全体を説明させる問題を1つ作る。",
            "misconception_scaffolding_guidance があれば、その方略を最優先で教材本文へ反映する。",
            "入力JSONの term.description を教材の中心内容として使う。別用語の例題や固定例を主題にしない。",
            "rag_context.chunks がある場合は、その教材コンテキストを優先して教材と問題を作る。教材にない内容は推測で断定しない。",
            "previous_practice_question が空でなければ、tutor_message の冒頭に『前の問題: ...』を入れる。",
            "previous_learner_response が空でなければ、tutor_message の冒頭に『あなたの回答: ...』を入れる。",
            "previous_feedback_for_learner が空でなければ、前の問題・回答の後に『前の回答を踏まえて、... 今回は...』という短い振り返りを自然に入れる。",
            "教材本文には、現在の主題の定義、役割、よくある誤解との違い、短い具体例または判断基準を必ず含める。",
            "問題文は、教材で説明した内容を学習者が自分の言葉で再説明する記述問題にする。答えだけの丸写しではなく、役割や判断基準を含めて説明させる。",
            "通常群と提案群で教材量の差が主効果にならないよう、指定されたL3/L2教材量の条件を守る。",
            "practice_question.body はbackend固定問題の補助として短く書く。L3の実際の複数確認問題と選択肢は fixed_practice_question_items をbackendが表示する。",
            "practice_question.expected_answer は現在の用語の期待回答にする。",
            "再テスト、確認テストの具体的な正解を先取りして出さない。",
            "tutor_message, learner_prompt, practice_question.body に M1/M2/M3/M4 という内部ラベルを絶対に書かない。",
        ]
        if group == "control":
            rules.append("統制群なので、過去ログ、誤概念タイプ、足場掛け履歴に適応しない通常AIチューターとして説明する。teaching_strategy は general_explanation に固定する。")
            rules.append("統制群では、L3相当の基礎教材とL2相当の観点教材を両方tutor_messageに含める。ただし質問はL2相当の1問だけにし、L3質問は出さない。")
        else:
            rules.append("提案群なので、誤概念タイプ、過去ログ、足場掛けレベルを教授方略へ反映する。")
            rules.append("M1ならカテゴリ捉え直し、M2なら境界比較、M3なら表層語から構造・判断基準への誘導、unknownなら基礎定義確認を優先する。")
            rules.append("提案群では、term_understandingをL3複数構成用語教材+L3複数質問、concept_understandingをL2教材+L2質問として段階的に提示する。")
        rules.append(f"teaching_strategy は次の識別子だけから選ぶ: {', '.join(_TEACHING_STRATEGIES)}。")
        result = await self._run_structured_turn("generate_tutoring_turn", self._prompt("tutoring_turn", prompt_payload, rules), schema)
        result["tutor_message"] = _strip_internal_labels(result["tutor_message"])
        result["learner_prompt"] = _strip_internal_labels(result["learner_prompt"])
        result["practice_question"]["body"] = _strip_internal_labels(result["practice_question"]["body"])
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
                    "rag_context.chunks がある場合は、その教材コンテキストを優先して判定・フィードバックする。教材にない内容は推測で断定しない。",
                    "M1/M2/M3/M4 という内部ラベルを学習者向け文面に絶対に書かない。",
                    "learning_misconception_type は、この学習セッション内の今回回答だけに対する内部診断として M1/M2/M3/M4/unknown/null から選ぶ。事前テスト由来の primary_misconception を上書きしない。",
                    "十分回答なら learning_misconception_type は null にしてよい。不十分な場合は、カテゴリー誤分類はM1、類似概念境界混同はM2、表層語反応はM3、知識不足はunknownにする。M4は今回の学習セッション教材方略では使わない。",
                    "learning_misconception_reason は研究者向けログ用に短く書き、学習者向けfeedbackには内部ラベルを書かない。",
                    "learning_stage が term_understanding の場合、is_sufficient は component_term の意味と対象概念内での役割が十分に説明されている場合だけ true にする。",
                    "learning_stage が concept_understanding の場合、is_sufficient は component_terms を使って対象概念全体を十分に説明できている場合だけ true にする。",
                    "理解が十分なら move_next、不十分なら continue にする。",
                    "next_scaffolding_level は参考値として L3/L2 のいずれかにし、指定外のレベルは使わない。最終更新はbackendが決める。",
                ],
            ),
            schema,
        )
        result["feedback"] = _strip_internal_labels(result["feedback"])
        result["learning_misconception_reason"] = _strip_internal_labels(result["learning_misconception_reason"])
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
            "learning_stage": payload.get("learning_stage"),
            "learning_stage_label": payload.get("learning_stage_label"),
            "component_terms": payload.get("component_terms"),
            "previous_practice_question": payload.get("previous_practice_question"),
            "previous_learner_response": payload.get("previous_learner_response"),
            "previous_feedback_for_learner": payload.get("previous_feedback_for_learner"),
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


def _strip_pretest_input_mentions(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないため、?", "", cleaned)
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないので、?", "", cleaned)
    cleaned = re.sub(r"理由記述や自信度", "回答内容", cleaned)
    cleaned = re.sub(r"理由記述", "回答内容", cleaned)
    cleaned = re.sub(r"自信度", "", cleaned)
    cleaned = re.sub(r"、{2,}", "、", cleaned)
    return cleaned.strip("、 ")
