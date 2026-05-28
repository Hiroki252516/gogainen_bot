import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import init_db, SessionLocal
from app.seed.seed_questions import seed_database

init_db()
db = SessionLocal()
try:
    seed_database(db)
finally:
    db.close()
