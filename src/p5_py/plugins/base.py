"""Plugin protocols and default hook implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from p5_py.context import SketchContext
    from p5_py.events.input_state import KeyboardEvent, MouseEvent, TouchEvent
    from p5_py.plugins.registry import PluginRegistry

LifecycleHookName = Literal[
    "before_preload",
    "before_setup",
    "after_setup",
    "before_draw",
    "after_draw",
]
EventHookName = Literal[
    "on_event",
    "on_mouse_event",
    "on_keyboard_event",
    "on_touch_event",
]
PluginHookName = LifecycleHookName | EventHookName
PluginApi = Callable[..., Any]

LIFECYCLE_HOOKS: tuple[LifecycleHookName, ...] = (
    "before_preload",
    "before_setup",
    "after_setup",
    "before_draw",
    "after_draw",
)
EVENT_HOOKS: tuple[EventHookName, ...] = (
    "on_event",
    "on_mouse_event",
    "on_keyboard_event",
    "on_touch_event",
)
PLUGIN_HOOKS: tuple[PluginHookName, ...] = (*LIFECYCLE_HOOKS, *EVENT_HOOKS)


@runtime_checkable
class PluginProtocol(Protocol):
    """Structural protocol for p5-py plugins.

    Plugins may implement any subset of the hook methods named in
    :data:`PLUGIN_HOOKS`. Hooks are discovered dynamically with ``getattr()`` so
    lightweight objects do not need to inherit from a framework base class.
    """

    name: str
    priority: int

    def install(self, registry: PluginRegistry) -> None: ...

    def uninstall(self, registry: PluginRegistry) -> None: ...


class Plugin:
    """Convenience base class providing no-op hook implementations.

    Registration ordering is deterministic:

    1. lower ``priority`` values run first
    2. ties preserve plugin installation order
    3. duplicate ``name`` values are rejected by the registry
    """

    name = "plugin"
    priority = 100

    def install(self, registry: PluginRegistry) -> None:
        del registry

    def uninstall(self, registry: PluginRegistry) -> None:
        del registry

    def before_preload(self, context: SketchContext) -> None:
        del context

    def before_setup(self, context: SketchContext) -> None:
        del context

    def after_setup(self, context: SketchContext) -> None:
        del context

    def before_draw(self, context: SketchContext) -> None:
        del context

    def after_draw(self, context: SketchContext) -> None:
        del context

    def on_event(
        self, context: SketchContext, event: MouseEvent | KeyboardEvent | TouchEvent
    ) -> None:
        del context, event

    def on_mouse_event(self, context: SketchContext, event: MouseEvent) -> None:
        del context, event

    def on_keyboard_event(self, context: SketchContext, event: KeyboardEvent) -> None:
        del context, event

    def on_touch_event(self, context: SketchContext, event: TouchEvent) -> None:
        del context, event
