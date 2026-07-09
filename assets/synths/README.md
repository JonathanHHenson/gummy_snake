# Synth assets

`src/gummysnake/synth/builtins/` contains one Python source module per bundled non-FX Sonic Pi `SynthDef` from `etc/synthdefs/designs/`, plus public Sonic Pi synth aliases retained from the cheatsheet. Each module defines its source plan with `@sy.synth` using the `sy.synth_input(...).layer(...).output()` signal-builder DSL, which emits low-level Gummy Snake primitive synth events.

`src/gummysnake/synth/fx_builtins/` contains one Python source module per documented Sonic Pi FX. Each module defines its source plan with `@sy.fx` using `sy.fx_input().<operation>(...)` plus `sy.fx_output(signal, ...)`, which emits generic low-level FX chain operations.

`assets/synths/compiled/` contains binary synth `.gss` files, and `assets/synths/fx/compiled/` contains binary FX `.gsfx` files generated from those source definitions with:

```sh
uv run python scripts/compile_synth_assets.py
```

A `.gss` file is a versioned Gummy Snake Synth binary container holding an expanded `PhysicalPlan`. It can be loaded with `gummysnake.synth.load_physical_plan()` or, for bundled assets, `gummysnake.synth.load_builtin_synth_plan(name)` and `gummysnake.synth.load_builtin_fx_plan(name)`.
