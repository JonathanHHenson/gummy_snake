# 3D and Shaders

Create a WEBGL canvas:

```python
gs.create_canvas(640, 480, renderer=gs.WEBGL)
```

## Camera and Projection

- `create_camera(...)`
- `camera(...)`
- `set_camera(camera)`
- `roll(angle)`
- `world_to_screen(x, y, z)`
- `screen_to_world(x, y, depth=0.0)`
- `perspective(...)`
- `frustum(left, right, bottom, top, near=0.1, far=10000.0)`
- `ortho(...)`
- `orbit_control(...)`

## Lights and Materials

- `ambient_light(...)`
- `directional_light(...)`
- `point_light(...)`
- `spot_light(...)`
- `image_light(image, intensity=1.0)`
- `panorama(image=None)`
- `lights()`
- `no_lights()`
- `light_falloff(constant, linear, quadratic)`
- `specular_color(...)`
- `normal_material()`
- `ambient_material(...)`
- `specular_material(...)`
- `shininess(value)`
- `emissive_material(...)`
- `metalness(value)`
- `texture_mode(mode=None)`
- `texture_wrap(wrap_x=None, wrap_y=None)`
- `texture(image)`

## Primitives and Models

- `plane(width, height=None)`
- `box(width, height=None, depth=None)`
- `sphere(radius, detail_x=24, detail_y=16)`
- `ellipsoid(...)`
- `cylinder(...)`
- `cone(...)`
- `torus(...)`
- `create_model(mesh_or_model)`
- `normal(x, y, z)`
- `vertex_property(name, value)`
- `build_geometry(callback)`
- `free_geometry(model)`
- `flip_u(mesh_or_model)`
- `flip_v(mesh_or_model)`
- `load_model(path)`
- `load_model_async(path)`
- `model(shape)`
- `save_obj(shape, path)`
- `save_stl(shape, path)`

## Shaders

- `load_shader(vertex_path, fragment_path)`
- `load_shader_async(vertex_path, fragment_path)`
- `create_shader(vertex_source, fragment_source)`
- `shader(shader_program)`
- `set_shader_uniform(name, value)`
- `reset_shader()`

Current `WEBGL` and `WEBGPU` support is a Rust-backed 3D path presented through
the canvas runtime. It supports deterministic small-sketch rendering, primitive
meshes, loaded OBJ/STL models, camera/projection helpers, lights, materials,
textures, geometry capture helpers, and shader objects for API compatibility.
Light, material, texture, and transform state compose with `push()`/`pop()` for
scoped drawing. `WEBGL`/`WEBGPU` do not imply user-programmable native shader
execution; backend capabilities distinguish `software_three_d`,
`native_three_d`, `shaders`, and `native_shaders`.

The current path keeps model and mesh data in Rust-owned handles. OBJ and STL
loading, primitive model generation, OBJ/STL export, built-in material lighting,
texture sampling, and fallback rasterization are handled by the canvas runtime
or Rust-compatible Python wrappers. When GPU drawing is available, unstroked
primitive and loaded-model draws use retained GPU vertex/index buffers with GPU
transform/projection, depth testing, and built-in material/texture shaders.
Sketch coordinates remain logical, including on HiDPI displays.

Browser context escape hatches such as `webgl_version`, `set_attributes`, and
`drawing_context` remain intentionally absent. Use Gummy Snake's Pythonic APIs
for camera/projection, materials, textures, shaders, compute/storage, and
offscreen render targets. See
[Feature scope decisions](../contribute/feature_scope_decisions.md) for the
native capability contract.
