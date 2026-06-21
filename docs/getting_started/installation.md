# Installation

Install the package from PyPI:

```sh
pip install gummy-snake
```

Then import it as `gummysnake` and use the short `gs` alias:

```python
import gummysnake as gs
```

Optional media helpers are available through the `media` extra:

```sh
pip install "gummy-snake[media]"
```

## Check Your Install

Save this as `hello_gummy.py`:

```python
import gummysnake as gs


def setup() -> None:
    gs.create_canvas(200, 200)


def draw() -> None:
    gs.background(240)
    gs.fill(30, 120, 220)
    gs.circle(100, 100, 80)


gs.run(setup=setup, draw=draw)
```

Run it:

```sh
python hello_gummy.py
```

If your environment does not support a native window, run a bounded headless
render:

```sh
python hello_gummy.py --headless --frames 1
```

## Local Repository Setup

If you are working from this repository, use `uv`:

```sh
uv sync --dev
uvx maturin develop --manifest-path crates/gummy_canvas/Cargo.toml --features extension-module
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1
```
