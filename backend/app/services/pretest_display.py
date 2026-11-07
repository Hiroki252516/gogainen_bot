from fastapi import HTTPException


def enabled(value) -> bool:
    return value is not False


def skip_review(db, participant) -> bool:
    from app.services.experiment import post_pretest_tests_completed
    if post_pretest_tests_completed(db, participant) == 0:
        return not enabled(participant.show_pretest_results)
    return not enabled(participant.show_retest_results)


def next_url(db, participant) -> str:
    from app.services.experiment import _next_url, learning_targets
    if participant.current_step == "learning_targets" and skip_review(db, participant):
        targets = learning_targets(db, participant.id)
        if targets:
            return f"/learning/{targets[0]['term_slug']}"
        raise HTTPException(status_code=503, detail={"error_code": "learning_navigation_unavailable", "message": "学習対象と進行状態に不整合があります。管理者に連絡してください。"})
    return _next_url(participant.current_step)
