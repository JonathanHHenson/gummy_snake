# Native 3D Renderer Plan

The current `WEBGL` renderer mode has a Rust-owned built-in GPU model path for
unstroked primitive/model drawing when GPU acceleration is available. Rust packs
model triangles, retains GPU vertex/index buffers, and runs transform,
projection, depth testing, texture sampling, and built-in material lighting in
GPU pipelines. Fallback software projection/rasterization still exists for
unsupported or CPU-only paths.

This plan now tracks the remaining gap between those built-in pipelines and a
broader native 3D renderer with full capability flags and user-programmable
native shaders.

## Capability Split

Backend capability reporting should keep these concepts separate:

- `three_d`: `create_canvas(..., WEBGL)` is accepted.
- `software_three_d`: WEBGL compatibility and fallback software 3D paths are
  available.
- `native_three_d`: the native runtime owns a broader native 3D feature set
  beyond the current built-in model pipelines.
- `shaders`: shader objects and shader-style API calls are accepted.
- `native_shaders`: user shader programs are compiled or interpreted by the
  native renderer.

For the canvas backend today, `three_d` and `software_three_d` are true, while
`native_three_d` and `native_shaders` are false. Built-in GPU model pipelines
do not by themselves imply full native 3D capability or native user shader
execution.

## Target Runtime Shape

The built-in GPU model path already moved part of this work into
`gummy_canvas`: retained model buffers, built-in model draw commands, GPU depth
testing, and built-in material/texture shaders. Remaining native 3D work should
complete or broaden:

1. Geometry upload: broaden immutable mesh buffers to cover all mesh/material
   combinations, stroked/outlined variants, versioning, and eviction.
2. Draw commands: broaden per-frame command buffers for model transform,
   material, texture, camera, projection, and light state across all 3D paths.
3. Depth handling: extend GPU depth behavior with explicit near/far clipping,
   culling policy, transparent ordering, and tests.
4. Materials and textures: broaden bind groups for base color, normal material,
   specular controls, Gummy Snake image textures, and future material features.
5. Shader scope: keep built-in material shaders stable; only set
   `native_shaders=True` after user shader source is validated, compiled, and
   mapped to supported attributes/uniforms.

## Migration Steps

1. Keep fallback software 3D deterministic and covered by projection/culling
   tests.
2. Add integration/golden tests for retained-buffer model draws, depth, culling,
   projection, materials, texture coordinates, and model loading.
3. Broaden Rust-side mesh resource APIs behind internal renderer methods for
   dynamic mesh mutation, stroked meshes, and transparent materials.
4. Route any remaining built-in primitive/model paths through retained
   mesh upload/draw where supported, leaving explicit fallbacks.
5. Switch capability defaults only after the broader native 3D feature set and
   native shader behavior are tested.
