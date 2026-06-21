"""Plugin registry and public registration helpers."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from types import MethodType
from typing import TYPE_CHECKING, Any
from weakref import WeakSet

from gummysnake._async import call_maybe_async
from gummysnake.api.current import require_context
from gummysnake.plugins.base import (
    EVENT_HOOKS,
    LIFECYCLE_HOOKS,
    PluginApi,
    PluginHookName,
    PluginProtocol,
)

if TYPE_CHECKING:
    from gummysnake.context import SketchContext
    from gummysnake.events.input_state import KeyboardEvent, MouseEvent, TouchEvent
    from gummysnake.sketch import Sketch


@dataclass(slots=True)
class PluginEntry:
    name: str
    plugin: PluginProtocol
    priority: int
    install_order: int


class PluginRegistry:
    """Registry for optional plugins and plugin-provided public APIs."""

    def __init__(self) -> None:
        self._entries: list[PluginEntry] = []
        self._apis: dict[str, PluginApi] = {}
        self._api_owners: dict[str, str] = {}
        self._bound_contexts: WeakSet[SketchContext] = WeakSet()
        self._bound_sketches: WeakSet[Sketch] = WeakSet()
        self._install_counter = 0
        self._installing_plugin_name: str | None = None

    def install(self, plugin: PluginProtocol) -> PluginProtocol:
        name = getattr(plugin, "name", plugin.__class__.__name__)
        if not name:
            raise ValueError("Plugin name cannot be empty.")
        if self.has(name):
            raise ValueError(f"Plugin {name!r} is already installed.")
        priority = int(getattr(plugin, "priority", 100))
        entry = PluginEntry(
            name=name,
            plugin=plugin,
            priority=priority,
            install_order=self._install_counter,
        )
        self._install_counter += 1
        self._entries.append(entry)
        self._entries.sort(key=lambda item: (item.priority, item.install_order, item.name))
        self._installing_plugin_name = name
        try:
            plugin.install(self)
        finally:
            self._installing_plugin_name = None
        return plugin

    def uninstall(self, plugin_or_name: PluginProtocol | str) -> None:
        name = plugin_or_name if isinstance(plugin_or_name, str) else plugin_or_name.name
        for index, entry in enumerate(self._entries):
            if entry.name == name:
                entry.plugin.uninstall(self)
                self._entries.pop(index)
                for api_name, owner_name in tuple(self._api_owners.items()):
                    if owner_name == name:
                        self.remove_api(api_name)
                return
        raise KeyError(f"Plugin {name!r} is not installed.")

    def clear(self) -> None:
        for name in list(self.names()):
            self.uninstall(name)

    def names(self) -> tuple[str, ...]:
        return tuple(entry.name for entry in self._entries)

    def has(self, name: str) -> bool:
        return any(entry.name == name for entry in self._entries)

    def bind_runtime(self, context: SketchContext, sketch: Sketch) -> None:
        self._bound_contexts.add(context)
        self._bound_sketches.add(sketch)
        for api_name, api in self._apis.items():
            self._bind_api_to_context(context, api_name, api)
            self._bind_api_to_sketch(sketch, api_name)

    def expose_api(self, name: str, api: PluginApi) -> None:
        if not name.isidentifier():
            raise ValueError(f"Plugin API name {name!r} must be a valid Python identifier.")
        if name in self._apis:
            raise ValueError(f"Plugin API {name!r} is already registered.")
        self._assert_public_name_available(name)
        self._apis[name] = api
        owner_name = self._installing_plugin_name
        if owner_name is not None:
            self._api_owners[name] = owner_name
        for context in tuple(self._bound_contexts):
            self._bind_api_to_context(context, name, api)
        for sketch in tuple(self._bound_sketches):
            self._bind_api_to_sketch(sketch, name)
        self._install_global_api(name)

    def remove_api(self, name: str) -> None:
        if name not in self._apis:
            raise KeyError(f"Plugin API {name!r} is not registered.")
        self._apis.pop(name)
        self._api_owners.pop(name, None)
        for context in tuple(self._bound_contexts):
            if hasattr(context, name):
                delattr(context, name)
        for sketch in tuple(self._bound_sketches):
            if hasattr(sketch, name):
                delattr(sketch, name)
        self._uninstall_global_api(name)

    def call_api(self, name: str, *args: Any, **kwargs: Any) -> Any:
        try:
            api = self._apis[name]
        except KeyError as exc:
            raise AttributeError(f"Plugin API {name!r} is not registered.") from exc
        context = require_context()
        return api(context, *args, **kwargs)

    def dispatch_lifecycle(self, hook_name: PluginHookName, context: SketchContext) -> None:
        if hook_name not in LIFECYCLE_HOOKS:
            raise ValueError(f"Unknown lifecycle hook {hook_name!r}.")
        for entry in self._entries:
            hook = getattr(entry.plugin, hook_name, None)
            if callable(hook):
                call_maybe_async(hook, context)

    def dispatch_event(
        self,
        hook_name: PluginHookName,
        context: SketchContext,
        event: MouseEvent | KeyboardEvent | TouchEvent,
    ) -> None:
        if hook_name not in EVENT_HOOKS:
            raise ValueError(f"Unknown event hook {hook_name!r}.")
        for entry in self._entries:
            general_hook = getattr(entry.plugin, "on_event", None)
            if hook_name != "on_event" and callable(general_hook):
                call_maybe_async(general_hook, context, event)
            hook = getattr(entry.plugin, hook_name, None)
            if callable(hook):
                call_maybe_async(hook, context, event)

    def _assert_public_name_available(self, name: str) -> None:
        for module_name in ("gummysnake", "gummysnake.api.global_mode"):
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, name):
                raise ValueError(
                    f"Cannot register plugin API {name!r}; {module_name} already defines it."
                )

    def _bind_api_to_context(self, context: SketchContext, name: str, api: PluginApi) -> None:
        def method(bound_context: SketchContext, *args: Any, **kwargs: Any) -> Any:
            return api(bound_context, *args, **kwargs)

        setattr(context, name, MethodType(method, context))

    def _bind_api_to_sketch(self, sketch: Sketch, name: str) -> None:
        def method(bound_sketch: Sketch, *args: Any, **kwargs: Any) -> Any:
            _ = bound_sketch
            return self.call_api(name, *args, **kwargs)

        setattr(sketch, name, MethodType(method, sketch))

    def _install_global_api(self, name: str) -> None:
        def global_api(*args: Any, **kwargs: Any) -> Any:
            return self.call_api(name, *args, **kwargs)

        global_api.__name__ = name
        global_api.__qualname__ = name
        global_api.__doc__ = f"Plugin API registered at runtime: {name}()."
        for module_name in ("gummysnake.api.global_mode", "gummysnake"):
            module = sys.modules.get(module_name)
            if module is not None:
                setattr(module, name, global_api)

    def _uninstall_global_api(self, name: str) -> None:
        for module_name in ("gummysnake.api.global_mode", "gummysnake"):
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, name):
                delattr(module, name)


GLOBAL_PLUGIN_REGISTRY = PluginRegistry()


def install_plugin(plugin: PluginProtocol) -> PluginProtocol:
    return GLOBAL_PLUGIN_REGISTRY.install(plugin)


def uninstall_plugin(plugin_or_name: PluginProtocol | str) -> None:
    GLOBAL_PLUGIN_REGISTRY.uninstall(plugin_or_name)


def clear_plugins() -> None:
    GLOBAL_PLUGIN_REGISTRY.clear()


def list_plugins() -> tuple[str, ...]:
    return GLOBAL_PLUGIN_REGISTRY.names()
