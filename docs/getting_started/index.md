# Getting Started

Gummy Snake is a Python creative-coding package. You write normal Python functions,
call drawing commands such as `circle()` and `background()`, and let Gummy Snake run the
sketch lifecycle.

Start here:

1. [Installation](installation.md)
2. [Your first sketch](first_sketch.md)
3. [Core concepts](core_concepts.md)
4. [Examples and next steps](examples.md)

## Tiny Example

```python
import gummysnake as gs


def setup() -> None:
    gs.create_canvas(320, 240)


def draw() -> None:
    gs.background(250)
    gs.circle(160, 120, 80)


gs.run(setup=setup, draw=draw)
```

