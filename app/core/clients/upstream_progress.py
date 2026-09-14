"""Bounded HTTP attempt diagnostics independent of payload archive retention."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from app.core.conversation_archive import archive_enabled
from app.core.utils.request_id import get_request_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HttpUpstreamProgress:
    body_format: Literal["sse", "json"]
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: float = field(default_factory=time.monotonic)
    headers_ms: int | None = None
    first_byte_ms: int | None = None
    first_event_ms: int | None = None
    last_byte_ms: int | None = None
    last_event_ms: int | None = None
    status_code: int | None = None
    received_bytes: int = 0
    body_bytes_visible: bool = True
    received_events: int = 0
    terminal_observed: bool = False

    def elapsed_ms(self) -> int:
        return max(0, int((time.monotonic() - self.started_at) * 1000))

    def emit(self, phase: str, *, exit_kind: str | None = None) -> None:
        # Fixed scalar fields only. No event text, upstream URL, headers,
        # account identity, or exception messages enter this channel.
        record = {
            "schema_version": 1,
            "request_id": get_request_id(),
            "attempt_id": self.attempt_id,
            "phase": phase,
            "elapsed_ms": self.elapsed_ms(),
            "body_format": self.body_format,
            "status_code": self.status_code,
            "headers_ms": self.headers_ms,
            "first_byte_ms": self.first_byte_ms,
            "first_event_ms": self.first_event_ms,
            "last_byte_ms": self.last_byte_ms,
            "last_event_ms": self.last_event_ms,
            "received_bytes": (self.received_bytes if self.body_format == "sse" and self.body_bytes_visible else None),
            "received_events": self.received_events,
            "terminal_observed": self.terminal_observed,
            "exit_kind": exit_kind,
            "archive_enabled": archive_enabled(),
            "archive_capture_complete": None,
        }
        logger.info("http_upstream_progress %s", json.dumps(record, separators=(",", ":")))

    def headers(self, status: int) -> None:
        self.status_code = status
        self.headers_ms = self.elapsed_ms()
        self.emit("headers")

    def body_chunk(self, size: int) -> None:
        self.received_bytes += size
        self.last_byte_ms = self.elapsed_ms()
        if self.first_byte_ms is None:
            self.first_byte_ms = self.last_byte_ms
            self.emit("first_byte")

    def event(self, *, terminal: bool) -> None:
        self.received_events += 1
        self.last_event_ms = self.elapsed_ms()
        self.terminal_observed |= terminal
        if self.first_event_ms is None:
            self.first_event_ms = self.last_event_ms
            self.emit("first_event")
