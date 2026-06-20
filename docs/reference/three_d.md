# 3D and Shaders

Create a WEBGL canvas:

```python
gs.create_canvas(640, 480, renderer=gs.WEBGL)
```

## Camera and Projection

- `create_camera(...)`
- `camera(...)`
- `set_camera(camera)`
- `perspective(...)`
- `ortho(...)`
- `frustum(...)`
- `orbit_control(...)`

## Lights and Materials

- `ambient_light(...)`
- `directional_light(...)`
- `point_light(...)`
- `spot_light(...)`
- `lights()`
- `no_lights()`
- `normal_material()`
- `ambient_material(...)`
- `specular_material(...)`
- `emissive_material(...)`
- `shininess(value)`
- `metalness(value)`
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
- `normal_shader()`

3D support is evolving. Unsupported shader or advanced 3D APIs raise explicit
Gummy Snake exceptions.
