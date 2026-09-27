"""In-process coordination for learning-turn pre-generation.

The coordinator deliberately keeps no database state.  A generated turn is
only persisted by the worker after the request that answered the previous
turn has committed successfully.  This keeps the existing database schema and
the answer endpoint's transaction boundary intact.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable


logger = logging.getLogger(__name__)


PrefetchWorker = Callable[["PrefetchHandle"], Awaitable[None]]


@dataclass
class PrefetchHandle:
    session_id: str
    participant_id: str
    _registry: "TutorPrefetchRegistry"
    _decision: asyncio.Future[bool]
    _task: asyncio.Task[None] | None = None
    _started: bool = False

    def start(self, worker: PrefetchWorker) -> bool:
        """Start one worker unless another worker already owns the session."""
        if self._started:
            return True
        if self._registry._active_job(self.session_id) is not None:
            return False
        self._started = True
        self._registry._jobs[self.session_id] = self
        self._task = asyncio.create_task(self._run(worker))
        return True

    async def _run(self, worker: PrefetchWorker) -> None:
        try:
            await worker(self)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A prefetch failure is intentionally invisible to the answer
            # response. The next-turn endpoint will generate synchronously.
            logger.exception("learning turn prefetch failed for session %s", self.session_id)
        finally:
            self._registry._remove(self)

    def confirm(self) -> None:
        """Allow a successfully answered request to publish the turn."""
        if not self._decision.done():
            self._decision.set_result(True)

    def abort(self, *, cancel: bool = True) -> None:
        """Discard the generated result and optionally stop the AI call."""
        if not self._decision.done():
            self._decision.set_result(False)
        if cancel and self._task is not None and not self._task.done():
            self._task.cancel()

    async def wait_for_decision(self) -> bool:
        return await self._decision


class TutorPrefetchRegistry:
    """Track at most one prefetch worker per tutor session."""

    def __init__(self) -> None:
        self._jobs: dict[str, PrefetchHandle] = {}

    def prepare(self, session_id: str, participant_id: str) -> PrefetchHandle:
        return PrefetchHandle(
            session_id=session_id,
            participant_id=participant_id,
            _registry=self,
            _decision=asyncio.get_running_loop().create_future(),
        )

    async def wait_for(self, session_id: str) -> None:
        handle = self._active_job(session_id)
        if handle is None or handle._task is None:
            return
        task = handle._task
        # A cancelled client request must not cancel the worker that is still
        # responsible for either publishing or discarding its generated turn.
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # ``shield`` keeps the worker alive when the waiting request is
            # cancelled. Only cancellation of the worker itself is a normal
            # completion; cancellation of the caller must propagate so the
            # route does not start a duplicate synchronous generation.
            if task.cancelled():
                return
            raise

    async def cancel_for_participant(self, participant_id: str) -> None:
        handles = [handle for handle in self._jobs.values() if handle.participant_id == participant_id]
        for handle in handles:
            handle.abort()
        if handles:
            await asyncio.gather(
                *(handle._task for handle in handles if handle._task is not None),
                return_exceptions=True,
            )

    def _active_job(self, session_id: str) -> PrefetchHandle | None:
        handle = self._jobs.get(session_id)
        if handle is None:
            return None
        if handle._task is not None and handle._task.done():
            self._remove(handle)
            return None
        return handle

    def _remove(self, handle: PrefetchHandle) -> None:
        if self._jobs.get(handle.session_id) is handle:
            self._jobs.pop(handle.session_id, None)


tutor_prefetch_registry = TutorPrefetchRegistry()
