import os
import sys
from pathlib import Path

os.environ["AI_BACKEND"] = "mock"
test_db = Path(__file__).resolve().parents[1] / ".local" / "test.db"
test_db.parent.mkdir(parents=True, exist_ok=True)
test_db.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
os.environ["EXPORT_DIR"] = str(test_db.parent / "exports")
os.environ["RAG_BASE_DIR"] = str(Path(__file__).resolve().parents[2] / "rag_agent_knowledge_base")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import init_db, SessionLocal
from app.seed.seed_questions import seed_database

init_db()
db = SessionLocal()
try:
    seed_database(db)
finally:
    db.close()
