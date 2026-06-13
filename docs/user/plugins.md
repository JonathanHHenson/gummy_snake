# Plugins and extension hooks

Epic 110 adds an optional plugin registry so extensions can integrate without modifying core runtime internals.

## Public APIs

```python
from p5_py.plugins import Plugin, install_plugin, uninstall_plugin, clear_plugins, list_plugins
```

## Hook ordering

Plugin execution order is deterministic:

1. lower `priority` values run first
2. ties keep installation order
3. duplicate plugin names are rejected

## Supported hooks

Lifecycle hooks:

- `before_preload(context)`
- `before_setup(context)`
- `after_setup(context)`
- `before_draw(context)`
- `after_draw(context)`

Event hooks:

- `on_event(context, event)`
- `on_mouse_event(context, event)`
- `on_keyboard_event(context, event)`
- `on_touch_event(context, event)`

## Adding a plugin API

Plugins can publish new sketch APIs at install time:

```python
from p5_py.plugins import Plugin, install_plugin


class GridPlugin(Plugin):
    name = "grid"

    def install(self, registry) -> None:
        registry.expose_api("draw_grid", self.draw_grid)

    def draw_grid(self, context, step: int = 20) -> None:
        context.stroke(220)
        for x in range(0, context.width, step):
            context.line(x, 0, x, context.height)
        for y in range(0, context.height, step):
            context.line(0, y, context.width, y)


install_plugin(GridPlugin())
```

After installation the API is available from:

- global mode through `p5_py.draw_grid(...)`
- class-based sketches through `self.draw_grid(...)`
- the underlying context through `context.draw_grid(...)`

## Cleanup

Uninstalling a plugin removes any APIs that plugin exposed through the registry.

## Example

See `examples/plugin_hooks.py` for a complete runnable example.
