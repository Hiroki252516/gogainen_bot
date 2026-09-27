from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Lock

from app.db.session import SessionLocal
from app.services.experiment import generate_prefetched_tutor_turn, prepare_prefetch_sessions


class PrefetchCoordinator:
    """Best-effort response-after workers for learning material prefetching.

    The worker owns its SQLAlchemy sessions and never shares the request
    session.  Correctness does not depend on this in-process coordinator:
    pending/generating rows fall back to synchronous generation when the
    participant reaches them, including after an application restart.
    """

    def __init__(self, *, max_workers: int = 4) -> None:
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
        self._lock = Lock()
        self._active_keys: set[tuple[str, str]] = set()
        self._futures: set[Future] = set()

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="tutor-prefetch")
        return self._executor

    def schedule(self, participant_id: str, source_session_id: str) -> bool:
        key = (participant_id, source_session_id)
        with self._lock:
            if key in self._active_keys:
                return False
            self._active_keys.add(key)
            future = self._ensure_executor().submit(self._run_batch, participant_id, source_session_id)
            self._futures.add(future)
            future.add_done_callback(lambda completed: self._finished(key, completed))
        return True

    def _finished(self, key: tuple[str, str], future: Future) -> None:
        # The worker is best-effort.  Its failure is represented in the
        # session/AICallLog state and must not become a participant request
        # error or an unobserved-future warning.
        try:
            future.exception()
        except Exception:
            pass
        with self._lock:
            self._active_keys.discard(key)
            self._futures.discard(future)

    @staticmethod
    def _run_one(session_id: str) -> None:
        db = SessionLocal()
        try:
            asyncio.run(generate_prefetched_tutor_turn(db, session_id))
        finally:
            db.close()

    def _run_batch(self, participant_id: str, source_session_id: str) -> None:
        db = SessionLocal()
        try:
            session_ids = prepare_prefetch_sessions(db, participant_id, source_session_id)
        finally:
            db.close()
        if not session_ids:
            return

        # Each target gets a separate worker and a separate SessionLocal.  The
        # active MVP has at most three terms, so this remains bounded.
        with ThreadPoolExecutor(max_workers=min(3, len(session_ids)), thread_name_prefix="tutor-prefetch-term") as executor:
            futures = [executor.submit(self._run_one, session_id) for session_id in session_ids]
            wait(futures)

    def wait_for_idle(self, timeout: float = 10.0) -> None:
        """Test/support hook; production requests never wait on this method."""
        with self._lock:
            futures = list(self._futures)
        if futures:
            wait(futures, timeout=timeout)

    def shutdown(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
            self._active_keys.clear()
            self._futures.clear()
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)


prefetch_coordinator = PrefetchCoordinator()


def schedule_prefetch(participant_id: str, source_session_id: str) -> bool:
    return prefetch_coordinator.schedule(participant_id, source_session_id)


def wait_for_prefetch_tasks(timeout: float = 10.0) -> None:
    prefetch_coordinator.wait_for_idle(timeout)
