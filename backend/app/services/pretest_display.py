from app.models import RuntimeSetting


def enabled(value) -> bool:
    return value is not False


def current_setting(db) -> bool:
    row = db.get(RuntimeSetting, 1)
    return enabled(row.show_pretest_results if row else None)


def save_setting(db, value: bool) -> bool:
    row = db.get(RuntimeSetting, 1)
    if row is None:
        row = RuntimeSetting(id=1)
        db.add(row)
    row.show_pretest_results = value
    db.commit()
    return value


def skip_review(db, participant) -> bool:
    from app.services.experiment import post_pretest_tests_completed
    return not enabled(participant.show_pretest_results) and post_pretest_tests_completed(db, participant) == 0


def next_url(db, participant) -> str:
    from app.services.experiment import _next_url, learning_targets
    if participant.current_step == "learning_targets" and skip_review(db, participant):
        targets = learning_targets(db, participant.id)
        if targets:
            return f"/learning/{targets[0]['term_slug']}"
    return _next_url(participant.current_step)
