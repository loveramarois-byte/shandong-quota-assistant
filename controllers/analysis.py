from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading


class TaskPhase(str, Enum):
    IDLE = "idle"
    SEARCHING = "searching"
    LOCAL_READY = "local_ready"
    AI_RUNNING = "ai_running"
    CANCELLING = "cancelling"
    ERROR = "error"
    CLOSED = "closed"


@dataclass(frozen=True)
class Capabilities:
    new: bool
    switch: bool
    rename: bool
    delete: bool
    send: bool
    cancel: bool
    export: bool = True


CAPABILITIES = {
    TaskPhase.IDLE: Capabilities(True, True, True, True, True, False),
    TaskPhase.SEARCHING: Capabilities(False, False, False, False, False, True),
    TaskPhase.LOCAL_READY: Capabilities(True, True, True, True, True, False),
    TaskPhase.AI_RUNNING: Capabilities(True, True, True, True, True, True),
    # Cancellation immediately releases the foreground UI. The worker is
    # isolated by its cancelled token until it exits.
    TaskPhase.CANCELLING: Capabilities(True, True, True, True, True, False),
    TaskPhase.ERROR: Capabilities(True, True, True, True, True, False),
    TaskPhase.CLOSED: Capabilities(False, False, False, False, False, False, False),
}


@dataclass(frozen=True)
class TaskToken:
    session_id: str
    turn_id: str
    request_id: int
    revision: int


@dataclass
class AnalysisTask:
    token: TaskToken
    cancel_event: threading.Event
    phase: TaskPhase


class AnalysisTaskRegistry:
    """Thread-safe identity and lifecycle gate for per-turn async work."""

    def __init__(self) -> None:
        self._tasks: dict[int, AnalysisTask] = {}
        self._lock = threading.RLock()

    def start(
        self,
        *,
        session_id: str,
        turn_id: str,
        request_id: int,
        revision: int,
        cancel_event: threading.Event,
        phase: TaskPhase = TaskPhase.SEARCHING,
    ) -> AnalysisTask:
        if phase not in {TaskPhase.SEARCHING, TaskPhase.AI_RUNNING}:
            raise ValueError(f"invalid task start phase: {phase}")
        task = AnalysisTask(TaskToken(session_id, turn_id, request_id, revision), cancel_event, phase)
        with self._lock:
            if request_id in self._tasks:
                raise ValueError(f"duplicate request_id: {request_id}")
            self._tasks[request_id] = task
        return task

    def get(self, request_id: int) -> AnalysisTask | None:
        with self._lock:
            return self._tasks.get(request_id)

    def accepts(self, token: TaskToken) -> AnalysisTask | None:
        with self._lock:
            task = self._tasks.get(token.request_id)
            if task is None or task.token != token:
                return None
            if task.phase in {TaskPhase.CANCELLING, TaskPhase.CLOSED} or task.cancel_event.is_set():
                return None
            return task

    def transition(self, request_id: int, phase: TaskPhase) -> AnalysisTask | None:
        with self._lock:
            task = self._tasks.get(request_id)
            if task is None:
                return None
            if task.phase in {TaskPhase.CANCELLING, TaskPhase.CLOSED}:
                return task
            task.phase = phase
            return task

    def cancel(self, request_id: int) -> AnalysisTask | None:
        with self._lock:
            task = self._tasks.get(request_id)
            if task is None:
                return None
            task.cancel_event.set()
            task.phase = TaskPhase.CANCELLING
            return task

    def finish(self, request_id: int, phase: TaskPhase = TaskPhase.LOCAL_READY) -> AnalysisTask | None:
        if phase not in {TaskPhase.LOCAL_READY, TaskPhase.ERROR, TaskPhase.CLOSED}:
            raise ValueError(f"invalid terminal phase: {phase}")
        with self._lock:
            task = self._tasks.pop(request_id, None)
            if task is not None:
                task.phase = phase
            return task

    def close_session(self, session_id: str) -> list[AnalysisTask]:
        with self._lock:
            closed = [task for task in self._tasks.values() if task.token.session_id == session_id]
            for task in closed:
                task.cancel_event.set()
                task.phase = TaskPhase.CLOSED
                self._tasks.pop(task.token.request_id, None)
            return closed

    def close_all(self) -> list[AnalysisTask]:
        with self._lock:
            tasks = list(self._tasks.values())
            for task in tasks:
                task.cancel_event.set()
                task.phase = TaskPhase.CLOSED
            self._tasks.clear()
            return tasks

    def searching(self) -> AnalysisTask | None:
        with self._lock:
            return next((task for task in self._tasks.values() if task.phase == TaskPhase.SEARCHING), None)

    def latest_ai(self, session_id: str | None = None) -> AnalysisTask | None:
        with self._lock:
            tasks = [
                task
                for task in self._tasks.values()
                if task.phase == TaskPhase.AI_RUNNING and (session_id is None or task.token.session_id == session_id)
            ]
            return max(tasks, key=lambda task: task.token.request_id, default=None)

    def for_turn(self, session_id: str, turn_id: str) -> AnalysisTask | None:
        with self._lock:
            return next(
                (
                    task
                    for task in self._tasks.values()
                    if task.token.session_id == session_id
                    and task.token.turn_id == turn_id
                    and task.phase in {TaskPhase.SEARCHING, TaskPhase.AI_RUNNING}
                ),
                None,
            )

    def capabilities(self, session_id: str | None) -> Capabilities:
        searching = self.searching()
        if searching is not None:
            return CAPABILITIES[TaskPhase.SEARCHING]
        if session_id and self.latest_ai(session_id) is not None:
            return CAPABILITIES[TaskPhase.AI_RUNNING]
        return CAPABILITIES[TaskPhase.IDLE]
