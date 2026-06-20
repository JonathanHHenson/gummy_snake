"""Internal helpers for synchronous APIs that accept awaitable callbacks."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any


def run_awaitable_blocking(awaitable: Awaitable[Any]) -> Any:
    """Run an awaitable to completion from gummysnake's synchronous runtime paths."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_value(awaitable))

    result: Any = None
    error: BaseException | None = None
    context = contextvars.copy_context()

    def target() -> None:
        nonlocal result, error
        try:
            result = context.run(lambda: asyncio.run(_await_value(awaitable)))
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            error = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error
    return result


def resolve_maybe_awaitable(value: Any) -> Any:
    """Return a value, awaiting it first when a callback returned an awaitable."""

    if inspect.isawaitable(value):
        return run_awaitable_blocking(value)
    return value


async def _await_value(awaitable: Awaitable[Any]) -> Any:
    return await awaitable


def call_maybe_async(callback: Callable[..., Any], *args: Any) -> Any:
    """Call a Gummy Snake callback and await its result when needed."""

    return resolve_maybe_awaitable(callback(*args))


def call_maybe_async_with_optional_args(callback: Callable[..., Any], *args: Any) -> Any:
    """Call callback with args, falling back to no args before awaiting."""

    try:
        value = callback(*args)
    except TypeError:
        value = callback()
    return resolve_maybe_awaitable(value)


async def run_blocking_io(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run blocking IO without copying active Gummy Snake contextvars to the worker thread."""

    loop = asyncio.get_running_loop()
    call = partial(callback, *args, **kwargs)
    from gummysnake.api.current import _ACTIVE_CONTEXT

    token = _ACTIVE_CONTEXT.set(None)
    try:
        future = loop.run_in_executor(None, call)
    finally:
        _ACTIVE_CONTEXT.reset(token)
    return await future
