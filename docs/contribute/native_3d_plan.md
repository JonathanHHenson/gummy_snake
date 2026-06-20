# Native 3D Renderer Plan

The current `WEBGL` renderer mode is a software-projected compatibility path.
Python owns camera, projection, material, light, shader-description state, mesh
generation, face sorting, shading, and rasterization. The Rust `p5_canvas`
runtime presents the resulting 2D canvas output, but it does not yet own a
native accelerated 3D pipeline.

## Capability Split

Backend capability reporting should keep these concepts separate:

- `three_d`: `create_canvas(..., WEBGL)` is accepted.
- `software_three_d`: 3D is implemented by the Python software renderer.
- `native_three_d`: 3D geometry is uploaded and drawn by the native runtime.
- `shaders`: shader objects and shader-style API calls are accepted.
- `native_shaders`: user shader programs are compiled or interpreted by the
  native renderer.

For the canvas backend today, `three_d` and `software_three_d` are true, while
`native_three_d` and `native_shaders` are false.

## Target Runtime Shape

Native 3D should move these responsibilities into `p5_canvas`:

1. Geometry upload: immutable mesh buffers keyed by model identity, primitive
   parameter keys, and model version.
2. Draw commands: per-frame command buffers for model transform, material,
   texture, camera, projection, and light state.
3. Depth handling: GPU depth buffer with explicit near/far clipping and culling
   policy.
4. Materials and textures: bind groups for base color, normal material,
   specular controls, and p5 image textures.
5. Shader scope: start with built-in material shaders; only set
   `native_shaders=True` after user shader source is validated, compiled, and
   mapped to supported attributes/uniforms.

## Migration Steps

1. Keep software 3D deterministic and covered by projection/culling tests.
2. Cache Python-generated primitive meshes so current sketches avoid repeated
   allocation while native upload work is developed.
3. Add Rust-side mesh resource APIs behind internal renderer methods.
4. Route built-in primitives through native mesh upload/draw when
   `native_three_d=True`, leaving software fallback available until parity is
   tested.
5. Add golden or integration tests for depth, culling, projection, materials,
   texture coordinates, and model loading before switching capability defaults.
