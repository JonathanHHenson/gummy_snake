"""Internal helpers for synchronous APIs that accept awaitable callbacks."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
from collections.abc import Awaitable, Callable
from typing import cast


def run_awaitable_blocking[T](awaitable: Awaitable[T]) -> T:
    """Run an awaitable to completion from gummysnake's synchronous runtime paths.

    Args:
        awaitable: The awaitable value. Expected type: `Awaitable[T]`.

    Returns:
        The return value. Type: `T`.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_value(awaitable))

    result: object = None
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
    return cast(T, result)


def resolve_maybe_awaitable[T](value: T | Awaitable[T]) -> T:
    """Return a value, awaiting it first when a callback returned an awaitable.

    Args:
        value: The value value. Expected type: `T | Awaitable[T]`.

    Returns:
        The return value. Type: `T`.
    """

    if inspect.isawaitable(value):
        return run_awaitable_blocking(cast(Awaitable[T], value))
    return cast(T, value)


async def _await_value[T](awaitable: Awaitable[T]) -> T:
    return await awaitable


def call_maybe_async[T, **P](
    callback: Callable[P, T | Awaitable[T]], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Call a Gummy Snake callback and await its result when needed."""

    return resolve_maybe_awaitable(callback(*args, **kwargs))


def call_maybe_async_with_optional_args[T](
    callback: Callable[..., T | Awaitable[T]], *args: object
) -> T:
    """Call callback with optional args without masking callback-internal TypeErrors."""

    accepts_args = _accepts_positional_args(callback, len(args)) if args else False
    if accepts_args is True:
        value = callback(*args)
    elif accepts_args is False:
        value = callback()
    else:
        try:
            value = callback(*args)
        except TypeError:
            value = callback()
    return resolve_maybe_awaitable(value)


def _accepts_positional_args(callback: Callable[..., object], count: int) -> bool | None:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return None
    positional_capacity = 0
    for parameter in signature.parameters.values():
        if parameter.kind is parameter.VAR_POSITIONAL:
            return True
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD):
            positional_capacity += 1
    return positional_capacity >= count
