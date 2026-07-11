# Gummy Snake examples

The reviewed machine-readable inventory is
[`example_catalog.toml`](example_catalog.toml). It classifies every Python file
under `examples/` as a runnable entry point, a support module, a historical
compatibility entry point, or an intentionally excluded generated file. For each
runnable example it records requirements, assets, CLI flags, output behavior,
headless suitability, smoke tier, and whether it is performance-only.

Examples use the mandatory canvas-first runtime. ECS examples additionally use
the Rust-owned ECS runtime; synth examples use the Rust synth renderer. Missing
runtime capabilities or assets are errors—examples do not create replacement
assets or use fallback renderers.

Run an interactive example:

```sh
uv run python examples/01_getting_started/basic_shapes.py --interactive
```

Run a bounded headless preview without writing output:

```sh
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1 --no-save
```

Generated images, data, and WAV files belong under ignored `examples/output/`.
For a normal bounded run, omit `--no-save`; canvas examples then save their
catalogued output when `--frames` is positive. Synth examples save and play by
default, so use `--no-play` for non-interactive/offline use.

## Learning groups

The numbered groups are a learning sequence, from basic drawing to specialized
runtime features:

- `01_getting_started`: first sketches, timing, and drawing basics.
- `02_drawing`: primitives, curves, transforms, color, compositing, pixels, and export.
- `03_assets`: images, data, sound metadata/analysis, and offscreen graphics.
- `04_text`: text rendering, measurement, and accessibility descriptions.
- `05_interaction`: mouse, keyboard, touch/sensor state, environment, and lifecycle controls.
- `06_math`: vectors, random numbers, noise, mapping, and interpolation.
- `07_plugins`: plugin hook ordering and plugin-provided APIs.
- `08_3d`: WEBGL primitives, cameras, lights, materials, geometry, models, and textures.
- `09_performance`: dense drawing, particle forces, retained WEBGL models, ECS boids,
  ant colony, and maintained ECS scenarios in `ecs_scenarios/`. These are
  performance-focused demonstrations rather than introductory lessons.
- `10_ecs`: Rust ECS components, resources, ordered systems, typed views, and spatial joins.
- `12_synth`: offline-capable synth tracks, samples, FX, controls, scales, and rings.
  `wob_rhythm.py` is canonical; `wob_rythm.py` remains a supported historical adapter
  with its original callable and default WAV output.

`11_temporary_perf_tests` is deliberately **not** a learning group. It contains
supported historical forwarding paths to the maintained `09_performance/ecs_scenarios/`
commands. `games/` contains complete sprite-based sketches rather than numbered
lessons. `assets/` is input data only, `support/` contains shared example/benchmark
logic, and `output/` is generated and ignored.

## Bounded smoke tiers

The catalog drives cumulative headless tiers; no tier deletes files, writes its
normal output, starts audio playback, or creates placeholder assets.

| Tier | Includes | Coverage |
| --- | --- | --- |
| `fast` | 7 focused examples | 2D drawing, packaged image assets, text, input-independent lifecycle, ECS, WEBGL model assets, and offline synth rendering. |
| `extended` | `fast` plus 5 examples | Offscreen graphics, sound metadata without playback, advanced 3D geometry, a second ECS sketch, and a packaged-asset game. |
| `release` | `extended` plus 4 examples | Export ordering, the 6,000-agent ECS/WebGL boids path, a compiled ECS scenario, and a second offline synth track. |

```sh
uv run python scripts/structure_audit.py
uv run python scripts/example_smoke.py --tier fast
uv run python scripts/example_smoke.py --tier extended
uv run python scripts/example_smoke.py --tier release
```

The synth smoke commands always pass `--no-play` and render only `0.1` seconds;
they require no audio device. Tiers require the actual selected canvas/ECS/synth
capability and declared assets. A missing capability or asset fails clearly instead
of being skipped or substituted.
