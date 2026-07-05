from __future__ import annotations

import asyncio

import pytest

from gummysnake._async import call_maybe_async_with_optional_args
from gummysnake.api.current import activate_context, get_active_context


def test_activate_context_restores_nested_contexts() -> None:
    outer = object()
    inner = object()

    assert get_active_context() is None
    with activate_context(outer):
        assert get_active_context() is outer
        with activate_context(inner):
            assert get_active_context() is inner
        assert get_active_context() is outer
    assert get_active_context() is None


def test_optional_arg_callback_preserves_no_arg_compatibility() -> None:
    calls: list[str] = []

    def callback() -> str:
        calls.append("called")
        return "ok"

    assert call_maybe_async_with_optional_args(callback, object()) == "ok"
    assert calls == ["called"]


def test_optional_arg_callback_does_not_mask_internal_type_error() -> None:
    def callback(_event: object) -> None:
        raise TypeError("internal callback failure")

    with pytest.raises(TypeError, match="internal callback failure"):
        call_maybe_async_with_optional_args(callback, object())


def test_optional_arg_callback_awaits_async_result() -> None:
    event = object()

    async def callback(value: object) -> object:
        await asyncio.sleep(0)
        return value

    assert call_maybe_async_with_optional_args(callback, event) is event
