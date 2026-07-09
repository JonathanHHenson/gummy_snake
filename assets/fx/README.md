# FX assets

`assets/fx/src/` contains one Python source module per documented Sonic Pi FX.

Each module defines its source plan with `@sy.fx` using `sy.fx_input().<operation>(...)` plus `sy.fx_output(signal, ...)`, which emits generic low-level FX chain operations.

`assets/fx/compiled/` contains binary FX `.gsfx` files generated from those source definitions with:

```sh
uv run python scripts/compile_synth_assets.py
```

A `.gsfx` file is a versioned Gummy Snake Synth binary container holding an expanded FX `PhysicalPlan`. It can be loaded with `gummysnake.synth.load_physical_plan()` or, for bundled FX assets, `gummysnake.synth.load_builtin_fx_plan(name)`.

Runtime `gummysnake` code loads built-in FX from `assets/fx/compiled/`; source modules are only used by the compile script.
