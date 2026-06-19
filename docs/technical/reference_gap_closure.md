# p5.js beta reference gap closure

This note summarizes a compatibility review against the beta p5.js reference at <https://beta.p5js.org/reference/>. It is intentionally scoped to `p5-py` and the native Python runtime. The sibling `p5.js` repository was not analyzed here because this project should not depend on JavaScript, HTML, DOM APIs, or browser runtime details.

Epic 140 in `backlog/140_reference_gap_closure/` tracks the follow-up work. The durable machine-readable inventory now lives in `docs/technical/reference_compatibility_inventory.toml` and is validated by `tests/unit/test_reference_gap_closure.py`.

## Compatibility policy

Every p5.js reference item should be classified as one of:

- `supported`: implemented and exported by p5-py.
- `partial`: implemented for a meaningful subset, with documented limitations.
- `pythonic_equivalent`: available through a Python-native API rather than a direct p5.js name.
- `deferred`: in scope someday, but blocked by renderer, media, platform, or design work.
- `excluded`: intentionally not part of p5-py.
- `not_applicable`: reference/tutorial/foundation material rather than a library API.

Canonical p5-py APIs are `snake_case` only. p5.js-style camelCase aliases should not be exported; sketch portability work should document the snake_case replacement instead.

## Current strong coverage

The current public API already covers substantial non-browser sketching:

- Sketch lifecycle and global mode: `run`, `setup`/`draw` discovery, `loop`, `no_loop`, `redraw`, `is_looping`, frame count, delta time, frame rate, and `millis`.
- Canvas/runtime basics: `create_canvas`, `resize_canvas`, width/height accessors, display/pixel density, headless/offscreen behavior through the canvas runtime.
- 2D primitives: `point`, `line`, `rect`, `square`, `ellipse`, `circle`, `triangle`, `quad`, `arc`.
- Core style and transform: fill/stroke state, stroke weight/cap/join, rect/ellipse/image modes, smoothing, push/pop, translate/rotate/scale/shear/apply/reset matrix, angle modes.
- Basic custom shapes and curves: `begin_shape`, `vertex`, `bezier_vertex`, `quadratic_vertex`, `end_shape`, `bezier`, `bezier_point`, and `bezier_tangent`.
- Color creation and interpolation: `color`, `color_mode`, `lerp_color`, plus RGB/HSB/HSL model support.
- Math/random/noise/vector basics: trigonometry, mapping/constrain/norm/lerp/dist/mag, seedable random/Gaussian/noise, and mutable vectors.
- Images/text/pixels: image loading/drawing/mode, font loading, text drawing and basic metrics, `load_pixels`, `update_pixels`, pixel array access, `blend`, `blend_mode`, `erase`, and `save_canvas`.
- Input basics: mouse position/movement/buttons, keyboard state, key lookup, and touch list support.
- Partial advanced media/3D: software/native canvas 3D slice for cameras, projection, orbit control, selected lights/materials, `plane`, `box`, `sphere`, model loading/drawing, shaders on supported native paths, file-backed sound, video, and capture.

## Major missing or partial feature groups

### Core 2D reference gaps

The high-value non-browser 2D gaps are mostly additive APIs on top of existing renderer/state foundations:

- Remaining custom shape gaps after the Pythonic spline slice: `begin_contour`, `end_contour`, `bezier_order`, `normal`, and `vertex_property`. Catmull-Rom `spline`, `spline_point`, `spline_tangent`, `spline_vertex`, `spline_properties`, and `spline_property` are implemented.
- Color readers/mutators: `red`, `green`, `blue`, `alpha`, `hue`, `saturation`, `brightness`, `lightness`, `palette_lerp`, plus `Color` methods such as contrast, channel setters, alpha setter, and string formatting.
- Clipping/tinting: `begin_clip`, `clip`, `end_clip`, `tint`, and `no_tint` need native canvas semantics.
- Remaining image/canvas gaps: clipping/tinting, `save_frames`, `save_gif`, and animated GIF controls where feasible. Canvas-level `get`, `set`, `copy`, and `filter` are implemented over the physical RGBA backing buffer.
- Remaining typography gaps: font outline/path helpers and richer shaping semantics. Font ascent/descent/width/bounds helpers, `text_bounds`, `text_direction`, `text_wrap`, `text_weight`, `text_properties`, and `text_property` are implemented over the current native metric contract.
- Offscreen rendering: `create_graphics`, framebuffer-like equivalents, `no_canvas`, and any `drawing_context` substitute need explicit canvas-runtime design before implementation.

### Math, data, and environment gaps

Many missing APIs are small compatibility utilities. They should be added only where they reduce porting friction without confusing Python users. The first Python-native parity slice adds trailing-underscore names for helpers that would otherwise shadow important Python built-ins, including `abs_`, `pow_`, `round_`, `float_`, `hex_`, `int_`, and `str_`:

- Calculation helpers: `abs_`, `ceil`, `exp`, `floor`, `log`, `pow_`, `round_`, `sqrt`, plus existing `min_value`, `max_value`, and `map_value` / `map`.
- Vector parity: indexed accessors, modulo/remainder, equality helpers, clamp-to-zero, heading and angle-between helpers, component get/set helpers, string formatting, spherical interpolation, random 2D/3D constructors, angle constructors, and reflection.
- Quaternion helpers: still deferred until a concrete native 3D camera/model workflow requires them. The current public 3D APIs do not need a standalone quaternion object, so adding one now would create API surface without a runtime-backed use case.
- Data conversion/formatting: `boolean`, `byte`, `char`, `float_`, `hex_`, `int_`, `str_`, `unchar`, `unhex`, `nf`, `nfc`, `nfp`, `nfs`, `shuffle`, and `split_tokens`.
- Time/date/environment: `day`, `month`, `year`, `hour`, `minute`, `second`, `get_target_frame_rate`, `window_width`, `window_height`, display dimensions, focus state, and `cursor` / `no_cursor` no-ops until native cursor control exists.
- Browser URL, localStorage, and Blob/client-side-save helpers are explicit package-specific stubs (`get_url`, `get_url_path`, `get_url_params`, `local_storage`, `create_blob`, `save_blob`, `load_blob`) and do not silently emulate browser state.

### Events, accessibility, and IO gaps

Current mouse/keyboard/touch support is partial. The beta reference includes browser/device APIs that need careful classification:

- Pointer/keyboard callbacks and variables: `mouse_clicked`, `double_clicked`, `mouse_dragged`, `mouse_moved`, `mouse_released`, `mouse_wheel`, `key_pressed`, `key_released`, `key_typed`, `win_mouse_x/y`, previous window mouse values, and `code` semantics.
- Pointer lock is browser-specific and remains excluded through `request_pointer_lock` and `exit_pointer_lock` stubs unless the native window runtime offers an explicit equivalent.
- Device acceleration/orientation APIs remain deferred through explicit current/previous value and device callback stubs until a native sensor provider is selected.
- Accessibility helpers such as `describe`, `describe_element`, `grid_output`, and `text_output` are implemented as native metadata/test hooks rather than browser DOM output.
- IO helpers focus on local file workflows such as text, bytes, JSON, and writer-style output. Browser Blob/client-side save behavior is not a native Python concept.

### Advanced 3D, shaders, and WebGPU gaps

The 3D/media work is intentionally partial. Missing beta-reference areas should be separated into practical native milestones:

- Remaining 3D geometry gaps: `build_geometry`, `free_geometry`, and rich p5.Geometry-style mutation helpers. `cone`, `cylinder`, `ellipsoid`, `torus`, `create_model`, `save_obj`, and `save_stl` are implemented.
- Camera/projection/interaction: `frustum`, `set_camera`, `roll`, debug grid/axes helpers, line perspective, and screen/world coordinate conversion.
- Lights/materials: `lights`, `no_lights`, `spot_light`, `image_light`, `panorama`, `light_falloff`, `specular_color`, `emissive_material`, `metalness`, `texture_mode`, and `texture_wrap`.
- Shader object parity: `Shader3D` now exposes Pythonic uniform, version, context-copy, hook-inspection, and source-modification helpers. Shader variant helpers are explicit deferred stubs.
- WebGPU, p5.strands, storage buffers, and compute shaders remain deferred or excluded through explicit public stubs unless the Rust canvas runtime grows a native GPU abstraction that can support them safely.

## Explicit exclusions and non-goals

These remain intentionally out of scope unless the project policy changes:

- JavaScript, HTML, DOM APIs, and browser elements.
- `p5.XML`.
- `p5.Table` and `p5.TableRow`.
- Browser-only URL, localStorage, pointer-lock, and client-side-save semantics unless a native design is explicitly accepted.
- Foundation reference pages such as JavaScript `class`, `for`, `function`, `if`, `let`, and JavaScript primitive types. These are educational reference material, not p5-py API targets.

## Follow-on implementation epics

Epic 140 created the compatibility inventory and first Pythonic parity slice. Remaining `partial` and `deferred` features are now tracked by implementation epics:

- `141_math_vector_quaternion_completion`: remaining Vector and quaternion parity.
- `142_core_2d_canvas_image_completion`: splines, contours, clipping, tinting, canvas pixels, image parity, and frame/GIF export.
- `143_typography_font_completion`: rich text metrics, text properties, and feasible font outline/path helpers.
- `144_offscreen_framebuffer_rendering`: `create_graphics`, framebuffer-like APIs, drawing-context alternatives, and `no_canvas` decisions.
- `145_events_accessibility_io_completion`: native event callbacks, touch, sensors, accessibility metadata, pointer-lock decisions, and local IO helpers.
- `146_advanced_3d_geometry_camera_lighting`: 3D primitives, geometry objects/export, cameras, debug helpers, lights, materials, and texture modes.
- `147_shader_webgpu_strands_storage_buffers`: shader object parity, shader variants, WebGPU/strands/storage-buffer/compute decisions.
- `148_sound_media_completion`: sound/media partial and deferred categories from `COMPATIBILITY_MATRIX` that sit outside the core beta reference page.

## Epic 140 breakdown

Epic 140 is split into focused PBIs:

- `reference_gap_audit.toml`: create the durable compatibility inventory and validation checks, including snake_case-only export checks.
- `core_2d_reference_parity.toml`: close high-value 2D/color/text/image/transform gaps.
- `math_data_environment_parity.toml`: add small math, data, time/date, and environment helpers.
- `events_accessibility_io_parity.toml`: clarify native event, accessibility, and IO behavior.
- `advanced_3d_webgpu_reference_gaps.toml`: classify advanced 3D, shader, geometry, WebGPU, and compute gaps.
