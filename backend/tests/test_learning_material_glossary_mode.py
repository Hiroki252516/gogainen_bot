from fastapi.testclient import TestClient as UnauthenticatedTestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin_client import AuthenticatedTestClient
from app.main import app
from app.models import Base, Participant, RuntimeSetting
from app.services.learning_material_glossary_mode import (
    ANNOTATION_ONLY,
    INTEGRATED_MATERIAL,
    current_setting,
    normalize_mode,
    save_setting,
)
from app.db.session import SessionLocal


client = AuthenticatedTestClient(app)


@pytest.fixture
def reset_material_glossary_setting():
    with SessionLocal() as db:
        row = db.get(RuntimeSetting, 1)
        original = row.learning_material_glossary_mode if row else None
        if row:
            row.learning_material_glossary_mode = None
            db.commit()
    yield
    with SessionLocal() as db:
        row = db.get(RuntimeSetting, 1)
        if row is None:
            row = RuntimeSetting(id=1)
            db.add(row)
        row.learning_material_glossary_mode = original
        db.commit()


def create_participant(code: str, student_number: str):
    response = client.post("/api/participants", json={
        "assignment_code": code,
        "consent_checked": True,
        "student_number": student_number,
    })
    assert response.status_code == 200, response.text
    return response.json()["participant_id"]


def test_admin_mode_defaults_validates_and_is_snapshotted_for_new_participants(reset_material_glossary_setting):
    unauthorized = UnauthenticatedTestClient(app)
    assert unauthorized.get("/api/admin/learning-material-glossary-mode").status_code == 401
    assert unauthorized.put("/api/admin/learning-material-glossary-mode", json={"mode": INTEGRATED_MATERIAL}).status_code == 401

    initial = client.get("/api/admin/learning-material-glossary-mode")
    assert initial.status_code == 200
    assert initial.json() == {"mode": ANNOTATION_ONLY, "applies_to": "new_participants_only"}
    assert initial.headers["cache-control"] == "no-store"
    assert client.put("/api/admin/learning-material-glossary-mode", json={"mode": "invalid"}).status_code == 422
    assert client.put("/api/admin/learning-material-glossary-mode", json={"mode": ANNOTATION_ONLY, "extra": True}).status_code == 422

    assert client.put("/api/admin/learning-material-glossary-mode", json={"mode": INTEGRATED_MATERIAL}).json()["mode"] == INTEGRATED_MATERIAL
    integrated_id = create_participant("A", "GLOSSARY-SNAPSHOT-A")
    assert client.put("/api/admin/learning-material-glossary-mode", json={"mode": ANNOTATION_ONLY}).json()["mode"] == ANNOTATION_ONLY
    annotation_id = create_participant("B", "GLOSSARY-SNAPSHOT-B")

    with SessionLocal() as db:
        assert db.get(Participant, integrated_id).learning_material_glossary_mode == INTEGRATED_MATERIAL
        assert db.get(Participant, annotation_id).learning_material_glossary_mode == ANNOTATION_ONLY
        legacy = Participant(
            display_code="GLOSSARY-LEGACY-NULL",
            group_condition="control",
            current_step="finish",
            learning_material_glossary_mode=None,
        )
        db.add(legacy)
        db.commit()
        assert legacy.learning_material_glossary_mode is None
        assert normalize_mode(legacy.learning_material_glossary_mode) == ANNOTATION_ONLY


def test_setting_default_and_saved_value_survive_database_reopen(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'material-mode.db'}", future=True)
    Base.metadata.create_all(engine)
    isolated_sessions = sessionmaker(bind=engine, autoflush=False, future=True)
    with isolated_sessions() as db:
        assert current_setting(db) == ANNOTATION_ONLY
        assert save_setting(db, INTEGRATED_MATERIAL) == INTEGRATED_MATERIAL
    with isolated_sessions() as db:
        assert current_setting(db) == INTEGRATED_MATERIAL
    engine.dispose()
