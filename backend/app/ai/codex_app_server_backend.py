from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

import websockets
from app.ai.backend import strategy_for
from app.ai.interaction_history import SHARED_QUESTION_ROUTE_VERSION, interaction_history_audit, project_model_payload
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID

from app.core.config import get_settings
from app.core.runtime_config import normalize_reasoning_effort
from app.ai.mandatory_elements import (
    expected_mandatory_type,
    mandatory_elements_schema,
)
from app.ai.misconception_taxonomy import TAXONOMY_VERSION
from app.ai.teaching_contract import (
    PROMPT_CONTRACT_VERSION,
    teaching_contract_schema,
)
from app.ai.tutoring_prompt import (
    build_tutoring_prompt,
    compose_structured_prompt,
    remove_routing_metadata,
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
        options = dict(
            open_timeout=min(10, self.timeout_sec),
            ping_interval=None,
            additional_headers=headers or None,
        )
        if self.url.startswith("unix://"):
            socket_path = self.url.removeprefix("unix://")
            if not socket_path.startswith("/"):
                raise CodexAppServerError(
                    "invalid_app_server_url",
                    "Unix socketの接続先には絶対パスを指定してください。",
                )
            self._ws = await websockets.unix_connect(path=socket_path, **options)
        else:
            self._ws = await websockets.connect(self.url, **options)
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

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._ws.send(json.dumps({"method": method, "params": params}))

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
        selected_strategy = strategy_for(expected_type, None, group)
        schema = {
            "type": "object",
            "properties": {
                "tutor_message": {"type": "string"},
                "teaching_strategy": {"type": "string", "enum": [selected_strategy]},
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
        result = await self._run_structured_turn(
            "generate_tutoring_turn",
            build_tutoring_prompt(
                prompt_payload,
                retry_context=payload,
                group=group,
                expected_type=expected_type,
                term_label=term_label,
                teaching_strategies=[selected_strategy],
            ),
            schema,
            # Audit metadata comes from the full request; model input stays allowlisted.
            audit_context=self._audit_context(payload, generation=True),
        )
        result["tutor_message"] = _strip_internal_labels(result["tutor_message"])
        if isinstance(result.get("teaching_contract"), dict):
            for field in ("corrected_claim", "mechanism_explanation", "contrast_example", "transfer_check"):
                if isinstance(result["teaching_contract"].get(field), str):
                    result["teaching_contract"][field] = _strip_internal_labels(result["teaching_contract"][field])
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
                    "interaction_historyは現在回答より前の同じ用語の採点済み履歴である。履歴を踏まえて要点を具体化してよいが、過去の問題や回答をそのまま転載しない。",
                    "summary は学習者向けの安全なMarkdownにする。冒頭に ## 今回の要点 を置き、箇条書き、**太字**、短い段落だけを使う。",
                    "HTML、表、コードブロック、画像、長大な連続段落は使わない。",
                    "rag_context.chunks がある場合はその本文を優先し、本文にない内容を推測で断定しない。",
                    "M1/M3/unknown、taxonomy、研究者向け診断、AIの思考過程を出力しない。",
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
                    "interaction_historyは現在回答より前の同じ用語の採点済み履歴である。履歴の回答・正誤を見直す観点に利用してよいが、履歴にない診断結果をbackendの判定として断定しない。",
                    "正答の選択肢本文、正答位置、正答そのものを直接示さない。",
                    "feedback は ## どこが違うか と ## 見直す観点を中心に、箇条書き、**太字**、短い段落だけを使う安全なMarkdownにする。",
                    "remediation_focus は学習者が次に確認する観点を一文で返し、general_knowledge_supplement は追加説明が不要なら null にする。",
                    "taxonomyや誤概念タイプが入力されている場合は解説の具体化に使うが、M1/M3/unknownなどのラベルを出力しない。",
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
        await rpc.notify("initialized", {})

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
            "experiment_spec_version": (audit_context or {}).get("experiment_spec_version"),
            "protocol_id": (audit_context or {}).get("protocol_id"),
            "interaction_history": (audit_context or {}).get("interaction_history"),
            "question_route_version": (audit_context or {}).get("question_route_version"),
            "actual_ai_input": (audit_context or {}).get("actual_ai_input"),
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
        return compose_structured_prompt(purpose, payload, rules)

    def _remove_routing_metadata(self, value: Any) -> Any:
        return remove_routing_metadata(value)

    def _audit_context(self, payload: dict[str, Any], *, generation: bool = False) -> dict[str, Any]:
        rag = payload.get("rag_context") or {}
        retry_attempt = (payload.get("mandatory_element_retry") or {}).get("attempt")
        attempt = payload.get("generation_attempt")
        if attempt is None:
            attempt = retry_attempt if retry_attempt is not None else 1
        return {
            "experiment_spec_version": CURRENT_EXPERIMENT_SPEC_VERSION,
            "protocol_id": CURRENT_PROTOCOL_ID,
            "interaction_history": interaction_history_audit(payload),
            "question_route_version": SHARED_QUESTION_ROUTE_VERSION,
            "actual_ai_input": project_model_payload(payload, proposed=payload.get("group_condition", "proposed") == "proposed", feedback=not generation),
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
        return project_model_payload(payload, proposed=True)

    def _control_tutoring_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return project_model_payload(payload, proposed=False)

    def _proposed_feedback_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return project_model_payload(payload, proposed=True, feedback=True)

    def _control_feedback_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return project_model_payload(payload, proposed=False, feedback=True)

    def _account_label(self, account: dict[str, Any] | None) -> str:
        if not account:
            return "未ログイン"
        if account.get("type") == "chatgpt":
            plan = account.get("planType") or "unknown"
            return f"ChatGPTログイン済み ({plan})"
        return f"{account.get('type', 'unknown')} account"


_BASE_INSTRUCTIONS = """
You are the AI engine for a Japanese research prototype called Learning Log AI Tutor.
You must act only as a structured-output tutoring and answer-feedback assistant.
Never modify files, run tools, browse, ask for API keys, or request authentication secrets.
Return only the JSON object requested by the caller's output schema.
""".strip()


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
