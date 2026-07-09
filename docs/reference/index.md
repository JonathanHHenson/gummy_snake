# API Reference

The public package is imported as `gummysnake` with the short `gs` alias:

```python
import gummysnake as gs
```

Reference topics:

- [Sketch lifecycle](lifecycle.md)
- [Canvas and drawing](drawing.md)
- [Color, style, and transforms](style_and_transforms.md)
- [Images, pixels, and assets](assets_and_pixels.md)
- [Input and events](input_and_events.md)
- [Entity component systems](ecs.md)
- [Synth tracks](synth.md)
- [Math, random, and vectors](math_random_vectors.md)
- [3D and shaders](three_d.md)
- [Constants and enums](constants_and_enums.md)

Function names use Python `snake_case`. p5.js-style camelCase names are not
public APIs.

Python-first conveniences are part of the public API:

- decorator callbacks with `@gs.setup`, `@gs.draw`, and `@gs.on(...)`
- property facades such as `gs.current`, `gs.mouse`, and `gs.keyboard`
- context managers such as `gs.style(...)` and `gs.transform(...)`
- async-compatible lifecycle callbacks and asset loaders
- dataclass-based ECS components/resources with Rust physical system execution
- logical synth tracks that render to audio files or `Sound` objects
- vector operators, event vector properties, and image indexing
