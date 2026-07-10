"""Implementation chunks for :mod:`gummysnake.ecs.action_tools.building`."""

from __future__ import annotations

from .scopes import (
    ForEachSource,
    _BranchContext,
    _ForEachContext,
    _OtherwiseBranchBuilder,
    _WhenBranchBuilder,
    conditional,
    do,
    do_in_order,
    do_in_parallel,
    for_each,
    otherwise,
    when,
)
from .session import (
    _BlockContext,
    _BuildBlock,
    _BuildSession,
    _BuildSessionContext,
    _ConditionalContext,
    _ConditionalScope,
    _DoFactory,
    active_build_session,
    append_action,
    build_session,
)

__all__ = [
    "ForEachSource",
    "_BlockContext",
    "_BranchContext",
    "_BuildBlock",
    "_BuildSession",
    "_BuildSessionContext",
    "_ConditionalContext",
    "_ConditionalScope",
    "_DoFactory",
    "_ForEachContext",
    "_OtherwiseBranchBuilder",
    "_WhenBranchBuilder",
    "active_build_session",
    "append_action",
    "build_session",
    "conditional",
    "do",
    "do_in_order",
    "do_in_parallel",
    "for_each",
    "otherwise",
    "when",
]
