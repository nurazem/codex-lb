"""Upstream ``session_id`` derived from a client ``prompt_cache_key``.

Upstream only reuses its prompt cache for requests that carry a Codex
``session_id``. A client that sends one stable ``prompt_cache_key`` per
conversation and no Codex session header must therefore get a session id the
proxy derives from that key, without changing routing and without touching
requests that already name a session or that sent no key at all.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest

from app.core.openai.requests import ResponsesRequest
from app.core.types import JsonValue
from app.db.models import StickySessionKind
from app.modules.api_keys.service import ApiKeyData
from app.modules.proxy.affinity import (
    PROMPT_CACHE_UPSTREAM_SESSION_HEADER,
    _headers_with_upstream_session_id,
    _prompt_cache_upstream_session_id,
    _sticky_key_for_responses_request,
)
from app.modules.proxy.thread_anchors import reset_thread_anchor_index

pytestmark = pytest.mark.unit

_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_anchor_index():
    reset_thread_anchor_index()
    yield
    reset_thread_anchor_index()


def _api_key(key_id: str) -> ApiKeyData:
    return ApiKeyData(
        id=key_id,
        name="test-key",
        key_prefix="sk-test",
        allowed_models=None,
        enforced_model=None,
        enforced_reasoning_effort=None,
        enforced_service_tier=None,
        expires_at=None,
        is_active=True,
        created_at=_NOW,
        last_used_at=None,
    )


def _request(prompt_cache_key: str | None = None) -> ResponsesRequest:
    return ResponsesRequest(
        model="gpt-5.4",
        instructions="You are helpful.",
        input=cast(
            JsonValue,
            [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
                {"role": "assistant", "content": "four"},
                {"role": "user", "content": "five"},
            ],
        ),
        prompt_cache_key=prompt_cache_key,
    )


def _policy(
    payload: ResponsesRequest,
    headers: dict[str, str],
    api_key: ApiKeyData | None,
    *,
    codex_session_affinity: bool = False,
):
    return _sticky_key_for_responses_request(
        payload,
        headers,
        codex_session_affinity=codex_session_affinity,
        openai_cache_affinity=True,
        openai_cache_affinity_max_age_seconds=1800,
        sticky_threads_enabled=False,
        api_key=api_key,
    )


def test_same_key_and_api_key_derive_one_stable_uuid() -> None:
    api_key = _api_key("ak_one")

    first = _prompt_cache_upstream_session_id("conv-123", {}, api_key)
    second = _prompt_cache_upstream_session_id("  conv-123  ", {"user-agent": "sdk"}, api_key)

    assert first is not None
    assert first == second
    assert str(UUID(first)) == first


def test_different_keys_or_api_keys_never_share_a_session_id() -> None:
    ids = {
        _prompt_cache_upstream_session_id("conv-a", {}, _api_key("ak_one")),
        _prompt_cache_upstream_session_id("conv-b", {}, _api_key("ak_one")),
        _prompt_cache_upstream_session_id("conv-a", {}, _api_key("ak_two")),
        _prompt_cache_upstream_session_id("conv-a", {}, None),
        # Length framing: these two would collide under naive concatenation.
        _prompt_cache_upstream_session_id("b:c", {}, _api_key("a")),
        _prompt_cache_upstream_session_id("c", {}, _api_key("a:b")),
    }

    assert None not in ids
    assert len(ids) == 6


@pytest.mark.parametrize(
    "header",
    ["session_id", "session-id", "x-codex-session-id", "x-codex-conversation-id", "thread-id", "Session_Id"],
)
def test_explicit_session_or_thread_header_wins(header: str) -> None:
    headers = {header: "client-session"}

    assert _prompt_cache_upstream_session_id("conv-123", headers, _api_key("ak_one")) is None
    assert _headers_with_upstream_session_id(headers, "derived") == headers


@pytest.mark.parametrize("key", [None, "", "   ", "v2t-std-ak_one-0123456789abcdef"])
def test_missing_blank_or_proxy_derived_key_mints_nothing(key: str | None) -> None:
    assert _prompt_cache_upstream_session_id(key, {}, _api_key("ak_one")) is None


def test_turn_state_alone_does_not_block_the_derived_session() -> None:
    headers = {"x-codex-turn-state": "http_turn_0123"}

    session_id = _prompt_cache_upstream_session_id("conv-123", headers, None)

    assert session_id is not None
    assert _headers_with_upstream_session_id(headers, session_id) == {
        "x-codex-turn-state": "http_turn_0123",
        PROMPT_CACHE_UPSTREAM_SESSION_HEADER: session_id,
    }


def test_client_key_policy_carries_session_id_and_keeps_prompt_cache_routing() -> None:
    api_key = _api_key("ak_one")
    payload = _request("conv-123")

    policy = _policy(payload, {}, api_key)

    assert policy.kind == StickySessionKind.PROMPT_CACHE
    assert policy.key == "conv-123"
    assert policy.max_age_seconds == 1800
    assert policy.prompt_cache_key_source == "payload"
    assert policy.upstream_session_id == _prompt_cache_upstream_session_id("conv-123", {}, api_key)
    # The selection boundary never sees the session id.
    assert "conv-123" == policy.selection_kwargs()["sticky_key"]


@pytest.mark.parametrize("codex_session_affinity", [False, True])
def test_client_session_header_policy_has_no_derived_session(codex_session_affinity: bool) -> None:
    policy = _policy(
        _request("conv-123"),
        {"session_id": "client-session"},
        _api_key("ak_one"),
        codex_session_affinity=codex_session_affinity,
    )

    assert policy.upstream_session_id is None


def test_keyless_request_keeps_anchor_derivation_and_mints_no_session() -> None:
    api_key = _api_key("ak_one")
    payload = _request(None)

    first = _policy(payload, {}, api_key)
    # The bridge -> HTTP fallback resolves the same object again; the derived
    # key written back onto it must not be mistaken for a client key.
    second = _policy(payload, {}, api_key)

    assert first.prompt_cache_key_source == "derived"
    assert isinstance(payload.prompt_cache_key, str) and payload.prompt_cache_key.startswith("v2t-")
    assert first.upstream_session_id is None
    assert second.upstream_session_id is None
