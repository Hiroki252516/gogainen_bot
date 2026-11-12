from fastapi.testclient import TestClient as UnauthenticatedTestClient
import pytest

from admin_client import AuthenticatedTestClient
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID, can_resume
from app.db.session import SessionLocal
from app.main import app
from app.models import Participant, RuntimeSetting
from app.services.learning_material_glossary_mode import ANNOTATION_ONLY, INTEGRATED_MATERIAL, normalize_mode
from split_api_support import new_research_code


client = AuthenticatedTestClient(app)


@pytest.fixture
def restore_legacy_runtime_mode():
    with SessionLocal() as db:
        row = db.get(RuntimeSetting, 1)
        original = row.learning_material_glossary_mode if row else None
        if row is None:
            row = RuntimeSetting(id=1)
            db.add(row)
        db.commit()
    yield
    with SessionLocal() as db:
        row = db.get(RuntimeSetting, 1)
        if row is not None:
            row.learning_material_glossary_mode = original
            db.commit()


def create_participant(code: str, _fixture_label: str):
    response = client.post("/api/participants", json={
        "assignment_code": code,
        "consent_checked": True,
        "research_code": new_research_code(),
    })
    assert response.status_code == 200, response.text
    return response.json()["participant_id"]


@pytest.mark.parametrize("legacy_mode", [ANNOTATION_ONLY, INTEGRATED_MATERIAL, None])
def test_new_participants_are_integrated_and_old_setting_is_ignored(restore_legacy_runtime_mode, legacy_mode):
    with SessionLocal() as db:
        setting = db.get(RuntimeSetting, 1)
        setting.learning_material_glossary_mode = legacy_mode
        db.commit()

    for group in ("A", "B"):
        participant_id = create_participant(group, f"GLOSSARY-FIXED-{legacy_mode or 'NULL'}-{group}")
        with SessionLocal() as db:
            participant = db.get(Participant, participant_id)
            assert participant.learning_material_glossary_mode == INTEGRATED_MATERIAL
            assert participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION == 51
            assert participant.protocol_id == CURRENT_PROTOCOL_ID == "experiment-plan-2026-11-12-perfect-test-early-exit-v1"
            assert can_resume(participant)
            setting = db.get(RuntimeSetting, 1)
            assert setting.learning_material_glossary_mode == legacy_mode

    assert normalize_mode(None) == ANNOTATION_ONLY
    assert normalize_mode(INTEGRATED_MATERIAL) == INTEGRATED_MATERIAL


def test_glossary_mode_admin_api_is_removed():
    unauthenticated = UnauthenticatedTestClient(app)
    for method in ("get", "put"):
        path = "/api/admin/learning-material-glossary-mode"
        response = getattr(unauthenticated, method)(path, json={"mode": INTEGRATED_MATERIAL}) if method == "put" else getattr(unauthenticated, method)(path)
        assert response.status_code == 404
        response = getattr(client, method)(path, json={"mode": ANNOTATION_ONLY}) if method == "put" else getattr(client, method)(path)
        assert response.status_code == 404


def test_historical_participant_mode_remains_readable_and_read_only():
    with SessionLocal() as db:
        legacy = Participant(
            display_code="GLOSSARY-LEGACY-MODE",
            group_condition="control",
            current_step="finish",
            experiment_spec_version=38,
            protocol_id="experiment-plan-2026-11-05-presurvey-baseline-v2-rag-glossary-v1",
            learning_material_glossary_mode=ANNOTATION_ONLY,
        )
        db.add(legacy)
        db.commit()
        participant_id = legacy.id
        assert not can_resume(legacy)

    response = client.get(f"/api/admin/participants/{participant_id}/logs")
    assert response.status_code == 200, response.text
    assert response.json()["participant"]["learning_material_glossary_mode"] == ANNOTATION_ONLY
    csv_response = client.get("/api/admin/export/participants.csv")
    assert csv_response.status_code == 200
    assert "GLOSSARY-LEGACY-MODE" in csv_response.text
    assert ANNOTATION_ONLY in csv_response.text
