from app.models import RuntimeSetting


def current_setting(db) -> bool:
    row = db.get(RuntimeSetting, 1)
    # The feature is enabled by default until the administrator saves a value.
    return row.show_question_reviews is not False if row else True


def save_setting(db, value: bool) -> bool:
    row = db.get(RuntimeSetting, 1)
    if row is None:
        row = RuntimeSetting(id=1)
        db.add(row)
    row.show_question_reviews = value
    db.commit()
    return value
