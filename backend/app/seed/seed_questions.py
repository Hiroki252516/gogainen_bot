from sqlalchemy.orm import Session

from app.content import sync_content_bundle
from app.db.session import SessionLocal, init_db


def seed_database(db: Session) -> None:
    sync_content_bundle(db)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
