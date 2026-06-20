# Compatibility and Unsupported APIs

Gummy Snake follows a sketch model, but it is a Python package, not a browser
runtime.

## Naming

Use Python `snake_case`:

```python
gs.create_canvas(400, 300)
gs.frame_rate(30)
gs.no_loop()
```

Do not use p5.js camelCase names such as `createCanvas()`, `frameRate()`, or
`noLoop()`.

## Excluded Browser Features

The package does not implement:

- DOM element helpers
- browser storage and URL helpers
- `gs.XML`
- `gs.Table`
- `gs.TableRow`
- browser-only Web APIs

Unsupported compatibility stubs raise package-specific exceptions instead of
failing indirectly.

## Runtime Requirements

The Rust `gummy_canvas` extension is required. Bounded/headless rendering,
interactive rendering, image loading, pixels, text, and export all route through
the canvas runtime.
