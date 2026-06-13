# Compatibility and Pythonic differences

`p5-py` tries to feel familiar to p5.js users without pretending to be a browser runtime.

## Naming

Canonical Python APIs use `snake_case`:

- `create_canvas()`
- `frame_rate()`
- `no_loop()`
- `pixel_density()`

Compatibility aliases delegate to the same implementation:

- `createCanvas()`
- `frameRate()`
- `noLoop()`
- `pixelDensity()`

Aliases are for familiarity and migration. The snake_case APIs are the canonical surface.

## Same ideas, different runtime

Expected differences from browser p5.js include:

- no DOM helpers
- no HTML elements
- no browser event loop
- no browser fetch/storage assumptions
- Python exceptions instead of loose browser-style failures

## Unsupported and excluded APIs

The package intentionally excludes browser-only areas such as:

- DOM element helpers like `createDiv()` and `createButton()`
- `p5.XML`
- `p5.Table` and `p5.TableRow`
- browser-only APIs with no native Python equivalent

These compatibility stubs raise explicit `p5_py` exceptions so unsupported features fail clearly.

## Migration guidance

When porting small p5.js sketches:

1. keep the `setup()`/`draw()` structure
2. switch imports to `import p5_py as p5`
3. prefer snake_case as you touch code
4. replace browser/DOM code with native Python alternatives or remove it
5. use `headless` for deterministic tests while porting

See `tests/unit/test_compatibility.py` for representative compatibility expectations.
