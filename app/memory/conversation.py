import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator
from uuid import UUID, uuid4

from app.errors import TutorError
from app.llm.base import Message


@dataclass
class Conversation:
    messages: list[Message] = field(default_factory=list)
    touched_at: float = 0
    busy: bool = False
    learner_id: UUID | None = None


class ConversationStore:
    """Single-process, event-loop-owned temporary sessions; no disk persistence."""

    def __init__(self, *, max_sessions: int, max_turns: int, ttl: int, clock: Callable[[], float] = time.monotonic):
        self.sessions: dict[UUID, Conversation] = {}
        self.max_sessions, self.max_turns, self.ttl = max_sessions, max_turns, ttl
        self.clock = clock

    def _prune(self) -> None:
        now = self.clock()
        expired = [key for key, session in self.sessions.items()
                   if not session.busy and now - session.touched_at >= self.ttl]
        for key in expired:
            del self.sessions[key]

    def create(self) -> UUID:
        self._prune()
        if len(self.sessions) >= self.max_sessions:
            raise TutorError('session_capacity', 'The server has too many active sessions. Please try later.', 503)
        key = uuid4()
        self.sessions[key] = Conversation(touched_at=self.clock())
        return key

    def _get(self, key: UUID) -> Conversation:
        self._prune()
        if key not in self.sessions:
            raise TutorError('session_expired', 'This session expired or the server restarted. Start a new session.', 404)
        return self.sessions[key]

    @contextmanager
    def use(self, key: UUID) -> Iterator[Conversation]:
        session = self._get(key)
        if session.busy:
            raise TutorError('session_busy', 'Wait for the current reply before sending another message.', 409)
        session.busy = True
        try:
            yield session
        finally:
            session.busy = False
            session.touched_at = self.clock()

    def append_turn(self, session: Conversation, user: Message, assistant: Message) -> None:
        session.messages.extend([user, assistant])
        session.messages[:] = session.messages[-self.max_turns * 2:]

    def delete(self, key: UUID) -> None:
        with self.use(key):
            del self.sessions[key]
