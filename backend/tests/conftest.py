import os
import sys
from pathlib import Path

os.environ["AI_BACKEND"] = "mock"
test_dir = Path(os.environ.get("TEST_DATABASE_DIR", Path(__file__).resolve().parents[1] / ".local"))
test_db = test_dir / "test.db"
test_db.parent.mkdir(parents=True, exist_ok=True)
test_db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
os.environ["EXPORT_DIR"] = str(test_db.parent / "exports")
identity_test_db = test_db.parent / "test-identities.sqlite3"
identity_test_db.unlink(missing_ok=True)
os.environ["IDENTITY_MAPPING_PATH"] = str(identity_test_db)
os.environ["RAG_BASE_DIR"] = str(Path(__file__).resolve().parents[2] / "rag_agent_knowledge_base")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import init_db, SessionLocal
from app.seed.seed_questions import seed_database
import pytest

init_db()
db = SessionLocal()
try:
    seed_database(db)
finally:
    db.close()


@pytest.fixture
def ten_choice_api():
    """The supported easy bank still exercises the three-item API contract."""
    from admin_client import AuthenticatedTestClient
    from app.main import app
    from app.services.prefetch import wait_for_prefetch_tasks

    client = AuthenticatedTestClient(app)
    previous = {name: client.get(f"/api/admin/{name}").json()["mode"] for name in ("question-set", "option-order")}
    assert client.put("/api/admin/question-set", json={"mode": "easy"}).status_code == 200
    assert client.put("/api/admin/option-order", json={"mode": "debug_fixed"}).status_code == 200
    yield
    wait_for_prefetch_tasks()
    for name, mode in previous.items():
        assert client.put(f"/api/admin/{name}", json={"mode": mode}).status_code == 200
