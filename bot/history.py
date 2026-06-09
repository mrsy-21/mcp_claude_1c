"""In-memory conversation history per user_id.

Stores only user text and final assistant text — no tool_use/tool_result blocks.
This keeps the history compact and prevents token blowup from large OData payloads.
"""

from llm.base import Message

MAX_PAIRS = 10  # 10 user + 10 assistant = 20 messages max


class History:
    def __init__(self) -> None:
        self._store: dict[int, list[Message]] = {}

    def get(self, user_id: int) -> list[Message]:
        return list(self._store.get(user_id, []))

    def append(self, user_id: int, role: str, content: str) -> None:
        msgs = self._store.setdefault(user_id, [])
        msgs.append(Message(role=role, content=content))
        # Keep only the last MAX_PAIRS pairs (2 messages per pair)
        if len(msgs) > MAX_PAIRS * 2:
            self._store[user_id] = msgs[-(MAX_PAIRS * 2):]

    def clear(self, user_id: int) -> None:
        self._store.pop(user_id, None)
