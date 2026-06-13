"""Plugin registration APIs for optional p5-py extensions."""

from p5_py.plugins.base import EVENT_HOOKS, LIFECYCLE_HOOKS, PLUGIN_HOOKS, Plugin, PluginProtocol
from p5_py.plugins.registry import (
    GLOBAL_PLUGIN_REGISTRY,
    PluginRegistry,
    clear_plugins,
    install_plugin,
    list_plugins,
    uninstall_plugin,
)

__all__ = [
    "EVENT_HOOKS",
    "GLOBAL_PLUGIN_REGISTRY",
    "LIFECYCLE_HOOKS",
    "PLUGIN_HOOKS",
    "Plugin",
    "PluginProtocol",
    "PluginRegistry",
    "clear_plugins",
    "install_plugin",
    "list_plugins",
    "uninstall_plugin",
]
