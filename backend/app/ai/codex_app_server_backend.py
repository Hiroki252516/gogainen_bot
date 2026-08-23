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
                "誤概念タイプの内部ラベルは、入力payloadのtaxonomy定義に従う。M1〜M4は学習者向け文面に出さない。",
                "natural_language_diagnosis には M1〜M4 という内部ラベルを絶対に書かない。",
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
            "学習セッション用の短い日本語チュータ発話を、安全なMarkdownとして作る。",
            "足場掛けレベルは L3/L2 のみを使い、指定外のレベルは使わない。",
            f"教材、問い返し、practice_question は必ず現在の用語『{term_label}』だけを主題にする。",
            "入力JSONの learning_stage が enrichment の場合は、不足知識を補う基礎教材として説明する。",
            "入力JSONの learning_stage が conceptual_change の場合は、誤信念またはカテゴリー錯誤を修正する教材として説明する。",
            "misconception_scaffolding_guidance があれば、その方略を最優先で教材本文へ反映する。",
            "入力JSONの term.description を教材の中心内容として使う。別用語の例題や固定例を主題にしない。",
            "rag_context.chunks がある場合は、その教材コンテキストを優先して教材と問題を作る。教材にない内容は推測で断定しない。",
            "previous_practice_question が空でなければ、tutor_message の冒頭に『前の問題: ...』を短いMarkdown段落として入れる。",
            "previous_learner_response が空でなければ、tutor_message の冒頭に『あなたの回答: ...』を短いMarkdown段落として入れる。",
            "previous_feedback_for_learner が空でなければ、前の問題・回答の後に短いMarkdown段落で振り返りを入れる。",
            "tutor_message は必ず『## 用語名』『### 要点』『### 具体例』『### 注意点』の順に構成する。",
            "教材本文には、現在の主題の定義、役割、よくある誤解との違い、短い具体例または判断基準を必ず含める。",
            "各セクションは2〜4個程度の簡潔な箇条書き、または短い段落で書く。重要語は **太字** にしてよい。",
            "内容上必要な場合だけ『### 前提用語とのつながり』『### 何ではないか』を追加する。",
            "教材Markdownでは見出し、箇条書き、太字、短い段落だけを使う。表、HTML、コードブロック、画像、長大な連続段落は使わない。",
            "問題文は、教材で説明した内容を学習者が自分の言葉で再説明する記述問題にする。答えだけの丸写しではなく、役割や判断基準を含めて説明させる。",
            "通常群と提案群で教材量の差が主効果にならないよう、指定されたL3/L2教材量の条件を守る。",
            "practice_question.body はbackend固定問題の補助として短く書く。L3の実際の複数確認問題と選択肢は fixed_practice_question_items をbackendが表示する。",
            "practice_question.expected_answer は現在の用語の期待回答にする。",
            "再テスト、確認テストの具体的な正解を先取りして出さない。",
            "tutor_message, learner_prompt, practice_question.body に M1〜M4 という内部ラベルを絶対に書かない。",
        ]
        if group == "control":
            rules.append("統制群なので、過去ログ、誤概念タイプ、足場掛け履歴に適応しない通常AIチューターとして説明する。teaching_strategy は general_explanation に固定する。")
            rules.append("統制群では、L3相当の基礎教材とL2相当の観点教材を両方tutor_messageに含める。ただし質問はL2相当の1問だけにし、L3質問は出さない。")
        else:
            rules.append("提案群なので、誤概念タイプ、過去ログ、足場掛けレベルを教授方略へ反映する。")
            rules.append("入力payloadのmisconception_taxonomyにあるM1〜M4の定義と教授方略を厳守する。M3ならカテゴリー再分類、M2なら説明モデルの再構成、M1なら誤信念の反証、M4なら不足スキーマの構築、unknownなら基礎知識の豊富化を優先する。")
            rules.append("提案群では、unknownはenrichment、M1/M3はconceptual_changeとして教材を提示し、固定3選択問題はbackendが表示する。")
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
        result = await self._run_structured_turn(
            "generate_correct_answer_summary",
            self._prompt(
                "correct_answer_summary",
                payload,
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
        prompt_payload = payload if payload.get("group_condition") == "proposed" else self._control_feedback_payload(payload)
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
                    "提案群でtaxonomyや誤概念タイプが入力されている場合は教授方略の判断に使うが、M1〜M4などのラベルを出力しない。",
                    "HTML、表、コードブロック、画像、長大な連続段落、AIの思考過程は出力しない。",
                    "rag_context.chunks がある場合はその本文を優先し、本文にない内容を推測で断定しない。",
                    "選択内容が空なら、前提知識不足として定義と判断基準の確認を促す。",
                ],
            ),
            schema,
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
                    "提案群専用の内部taxonomy。診断と教授方略の判断にだけ使い、学習者向け出力へ転載しない:",
                    json.dumps(payload["misconception_taxonomy"], ensure_ascii=False, indent=2),
                ]
            )
        prompt_parts.extend(["", "入力JSON:", json.dumps(payload, ensure_ascii=False, indent=2)])
        return "\n".join(prompt_parts)

    def _control_tutoring_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        term = payload.get("term") or {}
        return {
            "participant_id": payload.get("participant_id"),
            "group_condition": "control",
            "term": term,
            "learning_stage": payload.get("learning_stage"),
            "learning_stage_label": payload.get("learning_stage_label"),
            "component_term": payload.get("component_term"),
            "component_index": payload.get("component_index"),
            "component_total": payload.get("component_total"),
            "component_terms": payload.get("component_terms"),
            "fixed_practice_question": payload.get("fixed_practice_question"),
            "fixed_practice_question_items": payload.get("fixed_practice_question_items"),
            "rag_context": payload.get("rag_context"),
        }

    def _control_feedback_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "group_condition": "control",
            "term": payload.get("term"),
            "learning_stage": payload.get("learning_stage"),
            "component_term": payload.get("component_term"),
            "question_body": payload.get("question_body"),
            "selected_option_body": payload.get("selected_option_body"),
            "selected_option_bodies": payload.get("selected_option_bodies"),
            "material": payload.get("material"),
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
