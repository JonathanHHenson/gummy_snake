# Examples

The full reviewed catalog is [`examples/example_catalog.toml`](../../examples/example_catalog.toml),
with runnable command contracts, required assets/capabilities, output behavior,
and smoke classification. Start with these representative examples:

- `examples/01_getting_started/basic_shapes.py`
- `examples/01_getting_started/timing_and_animation.py`
- `examples/02_drawing/shapes_curves.py`
- `examples/02_drawing/transforms_and_modes.py`
- `examples/03_assets/images_and_sprites.py`
- `examples/04_text/typography_accessibility.py`
- `examples/05_interaction/lifecycle_controls.py`
- `examples/06_math/noise_vectors_random.py`
- `examples/08_3d/webgl_scene.py`
- `examples/10_ecs/firefly_constellation.py`
- `examples/games/asteroids.py`

The numbered directories form the learning sequence documented in
[`examples/README.md`](../../examples/README.md): drawing, assets, text,
interaction, math, plugins, 3D, performance, ECS, and synth. The performance
group is intentionally separate from the learning path; it demonstrates dense
rendering and ECS workloads. `examples/11_temporary_perf_tests/` contains retained
forwarding paths only, while `examples/support/` and `examples/assets/` are not
standalone lessons.

Run an example interactively:

```sh
uv run python examples/01_getting_started/basic_shapes.py --interactive
```

Run a bounded headless preview:

```sh
uv run python examples/01_getting_started/basic_shapes.py --headless --frames 1 --no-save
```

Normal bounded canvas runs save their catalogued result under `examples/output/`
when `--no-save` is omitted. That directory is ignored. Synth examples render WAV
files and play by default; use `--no-play` in non-interactive environments.

For contributor validation, run the catalog audit and cumulative bounded smoke
tiers. They cover 2D, image/text assets, lifecycle, ECS, WEBGL, and offline synth
rendering without requiring an audio device:

```sh
uv run python scripts/structure_audit.py
uv run python scripts/example_smoke.py --tier fast
uv run python scripts/example_smoke.py --tier extended
uv run python scripts/example_smoke.py --tier release
```

The canonical wobble synth path and callable are `wob_rhythm`; the historical
`examples/12_synth/wob_rythm.py` path/callable remains supported with its original
`wob_rythm.wav` default output.
