from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.core.types import JsonValue


@dataclass(slots=True)
class _OutputItem:
    first_index: int
    item_type: str
    completed: dict[str, JsonValue] | None = None


class ResponseOutputCollector:
    """Reconstruct missing terminal output without treating mutable indexes as identity."""

    def __init__(self) -> None:
        self._items: dict[str, _OutputItem] = {}
        self._invalid = False

    def add_event(self, payload: Mapping[str, JsonValue]) -> None:
        event_type = payload.get("type")
        if event_type not in ("response.output_item.added", "response.output_item.done"):
            return
        index = payload.get("output_index")
        item = payload.get("item")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or not isinstance(item, dict):
            self._invalid = True
            return
        item_id, item_type = item.get("id"), item.get("type")
        if not isinstance(item_id, str) or not item_id or not isinstance(item_type, str) or not item_type:
            self._invalid = True
            return
        state = self._items.setdefault(item_id, _OutputItem(index, item_type))
        if state.item_type != item_type:
            self._invalid = True
        if event_type == "response.output_item.done":
            if state.completed is not None and state.completed != item:
                self._invalid = True
            state.completed = dict(item)

    def merge(self, response: Mapping[str, JsonValue]) -> dict[str, JsonValue] | None:
        """Return None when fallback output cannot be reconstructed unambiguously."""
        merged = dict(response)
        output = response.get("output")
        if isinstance(output, list) and output:
            return merged
        if self._invalid:
            return None
        if not self._items:
            return merged
        completed: list[JsonValue] = []
        indexes: set[int] = set()
        call_ids: set[str] = set()
        for state in sorted(self._items.values(), key=lambda value: value.first_index):
            item = state.completed
            if item is None or state.first_index in indexes:
                return None
            indexes.add(state.first_index)
            if item.get("type") == "function_call":
                call_id = item.get("call_id")
                if not isinstance(call_id, str) or not call_id or call_id in call_ids:
                    return None
                call_ids.add(call_id)
            completed.append(item)
        merged["output"] = completed
        return merged
