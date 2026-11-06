"""Opt-in integration check. Requires an explicitly isolated SQLite database."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("sqlite:///") or not os.environ.get("PLAN_VERIFY_ISOLATED") == "1":
        raise SystemExit("Use PLAN_VERIFY_ISOLATED=1 and an explicit isolated SQLite DATABASE_URL; never use the study DB.")
    if os.environ.get("AI_BACKEND") != "codex_app_server":
        raise SystemExit("AI_BACKEND must be codex_app_server; no Mock fallback is permitted.")
    if not os.environ.get("IDENTITY_MAPPING_PATH"):
        raise SystemExit("Set an isolated IDENTITY_MAPPING_PATH as well.")
    from app.db.session import init_db, SessionLocal
    from app.seed.seed_questions import seed_database
    from app.main import app
    from app.models import AICallLog

    init_db()
    with SessionLocal() as db:
        seed_database(db)
    async def post(client, url, body=None):
        response = await client.post(url, json=body or {})
        response.raise_for_status()
        return response.json()

    async def case(group, kind, labels):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated-verification", timeout=600) as client:
            participant = await post(client, "/api/participants", {"assignment_code": group, "consent_checked": True, "student_number": "VERIFY-SYNTHETIC"})
            pid = participant["participant_id"]
            questions = (await client.get(f"/api/experiment/{pid}/pretest")).json()["questions"]
            for question in questions:
                ids = {option["label"]: option["option_id"] for option in question["options"]}
                await post(client, "/api/attempts", {"participant_id": pid, "question_id": question["question_id"], "selected_option_ids": [ids[label] for label in labels]})
            await post(client, f"/api/participants/{pid}/diagnose-pretest")
            session = await post(client, "/api/tutor-sessions", {"participant_id": pid, "term_slug": "llm_knowledge"})
            turn = await post(client, f"/api/tutor-sessions/{session['tutor_session_id']}/turns")
            viewed = await post(client, f"/api/tutor-turns/{turn['turn_id']}/material-view")
            assert viewed["recorded"]
            assert 600 <= len(turn["tutor_message"]) <= 800
            if kind == "M1":
                wrong_ids = {option["label"]: option["option_id"] for option in turn["practice_question"]["options"]}
                wrong = await post(client, f"/api/tutor-turns/{turn['turn_id']}/respond", {"selected_option_ids": [wrong_ids[label] for label in "GHI"]})
                assert not wrong["is_sufficient"] and wrong["feedback"]
                turn = await post(client, f"/api/tutor-sessions/{session['tutor_session_id']}/turns")
                assert 600 <= len(turn["tutor_message"]) <= 800
                await post(client, f"/api/tutor-turns/{turn['turn_id']}/material-view")
            ids = {option["label"]: option["option_id"] for option in turn["practice_question"]["options"]}
            await post(client, f"/api/tutor-turns/{turn['turn_id']}/respond", {"selected_option_ids": [ids[label] for label in "ABC"]})
            logs = (await client.get(f"/api/admin/participants/{pid}/logs")).json()
            saved = next(session for session in logs["tutor_sessions"] if session["term_slug"] == "llm_knowledge")["turns"][0]
            assert saved["material_viewed_at"]
            if group == "A":
                assert saved["mandatory_elements_validation"]["valid"]
                assert saved["teaching_contract_validation"]["valid"]
                if kind == "unknown":
                    assert set(saved["mandatory_elements"]) == {"type", "definition"}
            print(json.dumps({"group": group, "kind": kind, "characters": len(turn["tutor_message"]), "material_and_correct_feedback": "passed"}), flush=True)

    # Run one case first so connection/contract failures do not launch six retries.
    await case("A", "unknown", "J")
    for group, kind, labels in (("B", "unknown", "J"), ("A", "M1", "DEF"), ("B", "M1", "DEF"), ("A", "M3", "GHI"), ("B", "M3", "GHI")):
        await case(group, kind, labels)
    with SessionLocal() as db:
        calls = db.query(AICallLog).all()
        assert calls and all(call.provider == "codex_app_server" for call in calls)
        assert all((call.request_payload or {}).get("reasoning_effort") == "low" for call in calls)
        for call in calls:
            payload = call.request_payload or {}
            effective = payload.get("effective_request") or {}
            assert effective.get("model") == "gpt-5.6-luna"
            assert effective.get("reasoning_effort") == "low"
            if payload.get("group_condition") == "control":
                actual = effective.get("actual_ai_input") or {}
                assert not {"misconception_taxonomy", "learner_state", "active_misconception_type", "pretest_targets", "learning_stage"}.intersection(actual)
    print("real AI checks passed; records remain in the isolated verification DB", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
