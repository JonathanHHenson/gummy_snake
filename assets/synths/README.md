# Synth assets

`assets/synths/src/` contains one Python source module per bundled non-FX Sonic Pi `SynthDef` from `etc/synthdefs/designs/`, plus public Sonic Pi synth aliases retained from the cheatsheet.

Each module defines its source plan with `@sy.synth` using the `sy.synth_input(...).layer(...).output()` signal-builder DSL, which emits low-level Gummy Snake primitive synth events.

`assets/synths/compiled/` contains binary synth `.gss` files generated from those source definitions with:

```sh
uv run python scripts/compile_synth_assets.py
```

A `.gss` file is a versioned Gummy Snake Synth binary container holding an expanded `PhysicalPlan`. It can be loaded with `gummysnake.synth.load_physical_plan()` or, for bundled synth assets, `gummysnake.synth.load_builtin_synth_plan(name)`.

Runtime `gummysnake` code loads built-in synths from `assets/synths/compiled/`; source modules are only used by the compile script.
