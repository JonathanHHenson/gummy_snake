# 3D and Shaders

Create a WEBGL canvas:

```python
gs.create_canvas(640, 480, renderer=gs.WEBGL)
```

## Camera and Projection

- `create_camera(...)`
- `camera(...)`
- `perspective(...)`
- `ortho(...)`
- `orbit_control(...)`

## Lights and Materials

- `ambient_light(...)`
- `directional_light(...)`
- `point_light(...)`
- `normal_material()`
- `ambient_material(...)`
- `specular_material(...)`
- `shininess(value)`
- `texture(image)`

## Primitives and Models

- `plane(width, height=None)`
- `box(width, height=None, depth=None)`
- `sphere(radius, detail_x=24, detail_y=16)`
- `ellipsoid(...)`
- `cylinder(...)`
- `cone(...)`
- `torus(...)`
- `load_model(path)`
- `model(shape)`
- `save_obj(shape, path)`
- `save_stl(shape, path)`

## Shaders

- `load_shader(vertex_path, fragment_path)`
- `create_shader(vertex_source, fragment_source)`
- `shader(shader_program)`
- `reset_shader()`

Current `WEBGL` support is a Rust-backed 3D path presented through the canvas
runtime. It supports deterministic small-sketch rendering, primitive meshes,
loaded OBJ models, lights, materials, textures, and shader objects for API
compatibility. It does not imply user-programmable native shader execution;
backend capabilities distinguish `software_three_d`, `native_three_d`,
`shaders`, and `native_shaders`.

The current path keeps model and mesh data in Rust-owned handles. OBJ parsing,
primitive model generation, OBJ/STL export, built-in material lighting, texture
sampling, and fallback rasterization are handled by the canvas runtime. When GPU
drawing is available, unstroked primitive and loaded-model draws use retained
GPU vertex/index buffers with GPU transform/projection, depth testing, and
built-in material/texture shaders. Sketch coordinates remain logical, including
on HiDPI displays.

Unsupported shader or advanced 3D APIs raise explicit Gummy Snake exceptions.
Browser context APIs such as `webgl_version`, `set_attributes`,
`drawing_context`, WebGPU compute/storage APIs, offscreen browser canvas helpers,
and user-programmable native shader execution are not public API surfaces. See
[Feature scope decisions](../contribute/feature_scope_decisions.md) for the
native capability contract and deferred WebGPU/compute design.
