from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal['user', 'assistant']
    content: str


class LLMProvider(Protocol):
    async def generate(self, *, instructions: str, messages: list[Message], schema: dict | None = None) -> str:
        """Return text, or JSON text when schema is supplied. Callers validate app schemas."""
        ...
