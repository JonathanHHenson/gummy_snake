pub(super) const TRIANGLE_SHADER: &str = r#"
struct Viewport {
    size: vec2<f32>,
    _padding: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> viewport: Viewport;

@group(1) @binding(0)
var clip_texture: texture_2d<f32>;

@group(1) @binding(1)
var clip_sampler: sampler;

struct Clip {
    rect: vec4<f32>,
    flags: vec4<f32>,
};

@group(1) @binding(2)
var<uniform> clip: Clip;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) color: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) color: vec4<f32>,
    @location(1) canvas_position: vec2<f32>,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;
    let ndc_x = input.position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - input.position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.color = input.color;
    output.canvas_position = input.position;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    if clip.flags.x > 0.5 {
        let clip_position = input.canvas_position - clip.rect.xy;
        if clip_position.x < 0.0 || clip_position.y < 0.0 || clip_position.x >= clip.rect.z || clip_position.y >= clip.rect.w {
            discard;
        }
        let clip_uv = (clip_position + vec2<f32>(0.5, 0.5)) / clip.rect.zw;
        if textureSample(clip_texture, clip_sampler, clip_uv).a < 0.5 {
            discard;
        }
    }
    return input.color;
}
"#;

pub(super) const PROCEDURAL_PRIMITIVE_SHADER: &str = r#"
struct Viewport {
    size: vec2<f32>,
    _padding: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> viewport: Viewport;

@group(1) @binding(0)
var clip_texture: texture_2d<f32>;

@group(1) @binding(1)
var clip_sampler: sampler;

struct Clip {
    rect: vec4<f32>,
    flags: vec4<f32>,
};

@group(1) @binding(2)
var<uniform> clip: Clip;

struct InstanceInput {
    @location(0) p0: vec2<f32>,
    @location(1) p1: vec2<f32>,
    @location(2) p2: vec2<f32>,
    @location(3) bounds: vec4<f32>,
    @location(4) color: vec4<f32>,
    @location(5) params: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) canvas_position: vec2<f32>,
    @location(1) color: vec4<f32>,
    @location(2) p0: vec2<f32>,
    @location(3) p1: vec2<f32>,
    @location(4) p2: vec2<f32>,
    @location(5) bounds: vec4<f32>,
    @location(6) @interpolate(flat) kind: u32,
};

@vertex
fn vs_main(input: InstanceInput, @builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 1.0),
    );
    let corner = corners[vertex_index];
    let canvas_position = mix(input.bounds.xy, input.bounds.zw, corner);
    var output: VertexOutput;
    let ndc_x = canvas_position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - canvas_position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.canvas_position = canvas_position;
    output.color = input.color;
    output.p0 = input.p0;
    output.p1 = input.p1;
    output.p2 = input.p2;
    output.bounds = input.bounds;
    output.kind = u32(input.params.x + 0.5);
    return output;
}

fn triangle_sign(a: vec2<f32>, b: vec2<f32>, c: vec2<f32>) -> f32 {
    return (a.x - c.x) * (b.y - c.y) - (b.x - c.x) * (a.y - c.y);
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    if clip.flags.x > 0.5 {
        let clip_position = input.canvas_position - clip.rect.xy;
        if clip_position.x < 0.0 || clip_position.y < 0.0 || clip_position.x >= clip.rect.z || clip_position.y >= clip.rect.w {
            discard;
        }
        let clip_uv = (clip_position + vec2<f32>(0.5, 0.5)) / clip.rect.zw;
        if textureSample(clip_texture, clip_sampler, clip_uv).a < 0.5 {
            discard;
        }
    }
    if input.kind == 3u {
        let center = (input.bounds.xy + input.bounds.zw) * 0.5;
        let radius = max((input.bounds.zw - input.bounds.xy) * 0.5, vec2<f32>(0.0001, 0.0001));
        let normalized = (input.canvas_position - center) / radius;
        if dot(normalized, normalized) > 1.0 {
            discard;
        }
    } else if input.kind == 2u {
        let d1 = triangle_sign(input.canvas_position, input.p0, input.p1);
        let d2 = triangle_sign(input.canvas_position, input.p1, input.p2);
        let d3 = triangle_sign(input.canvas_position, input.p2, input.p0);
        let has_neg = d1 < 0.0 || d2 < 0.0 || d3 < 0.0;
        let has_pos = d1 > 0.0 || d2 > 0.0 || d3 > 0.0;
        if has_neg && has_pos {
            discard;
        }
    }
    return input.color;
}
"#;

pub(super) const TEXTURE_SHADER: &str = r#"
struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(1.0, 1.0),
    );
    var uvs = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(1.0, 0.0),
    );
    var output: VertexOutput;
    output.position = vec4<f32>(positions[vertex_index], 0.0, 1.0);
    output.uv = uvs[vertex_index];
    return output;
}

@group(0) @binding(0)
var offscreen_texture: texture_2d<f32>;

@group(0) @binding(1)
var offscreen_sampler: sampler;

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    return textureSample(offscreen_texture, offscreen_sampler, input.uv);
}
"#;

pub(super) const IMAGE_SHADER: &str = r#"
struct Viewport {
    size: vec2<f32>,
    _padding: vec2<f32>,
};

@group(0) @binding(0)
var<uniform> viewport: Viewport;

@group(2) @binding(0)
var clip_texture: texture_2d<f32>;

@group(2) @binding(1)
var clip_sampler: sampler;

struct Clip {
    rect: vec4<f32>,
    flags: vec4<f32>,
};

@group(2) @binding(2)
var<uniform> clip: Clip;

struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) uv: vec2<f32>,
    @location(2) tint: vec4<f32>,
};

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) tint: vec4<f32>,
    @location(2) canvas_position: vec2<f32>,
};

@vertex
fn vs_main(input: VertexInput) -> VertexOutput {
    var output: VertexOutput;
    let ndc_x = input.position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - input.position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.uv = input.uv;
    output.tint = input.tint;
    output.canvas_position = input.position;
    return output;
}

@group(1) @binding(0)
var image_texture: texture_2d<f32>;

@group(1) @binding(1)
var image_sampler: sampler;

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    if clip.flags.x > 0.5 {
        let clip_position = input.canvas_position - clip.rect.xy;
        if clip_position.x < 0.0 || clip_position.y < 0.0 || clip_position.x >= clip.rect.z || clip_position.y >= clip.rect.w {
            discard;
        }
        let clip_uv = (clip_position + vec2<f32>(0.5, 0.5)) / clip.rect.zw;
        if textureSample(clip_texture, clip_sampler, clip_uv).a < 0.5 {
            discard;
        }
    }
    return textureSample(image_texture, image_sampler, input.uv) * input.tint;
}
"#;

pub(super) const MODEL_SHADER: &str = r#"
struct ModelUniform {
    model: mat4x4<f32>,
    view_projection: mat4x4<f32>,
    base_color: vec4<f32>,
    emissive_color: vec4<f32>,
    specular_shininess: vec4<f32>,
    ambient_color: vec4<f32>,
    directional_color: vec4<f32>,
    directional_direction: vec4<f32>,
    point_color: vec4<f32>,
    point_position: vec4<f32>,
    flags: vec4<f32>,
};

@group(0) @binding(0)
var<storage, read> models: array<ModelUniform>;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) world_position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) @interpolate(flat) model_index: u32,
};

@vertex
fn vs_main(input: VertexInput, @builtin(instance_index) model_index: u32) -> VertexOutput {
    let model = models[model_index];
    let world = model.model * vec4<f32>(input.position, 1.0);
    var output: VertexOutput;
    output.clip_position = model.view_projection * world;
    output.world_position = world.xyz;
    output.normal = normalize((model.model * vec4<f32>(input.normal, 0.0)).xyz);
    output.model_index = model_index;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let model = models[input.model_index];
    let normal = normalize(input.normal);
    if model.flags.z > 0.5 {
        return vec4<f32>(normal * 0.5 + vec3<f32>(0.5), model.base_color.a);
    }
    var color = model.emissive_color + model.base_color * model.ambient_color;

    let directional_enabled = model.flags.x;
    if directional_enabled > 0.5 {
        let light_dir = normalize(-model.directional_direction.xyz);
        let diffuse = max(dot(normal, light_dir), 0.0);
        color = color + model.base_color * model.directional_color * diffuse;

        let view_dir = normalize(vec3<f32>(0.0, 0.0, 1.0));
        let half_dir = normalize(light_dir + view_dir);
        let specular = pow(max(dot(normal, half_dir), 0.0), max(model.specular_shininess.w, 1.0));
        color = color + vec4<f32>(model.specular_shininess.xyz, model.base_color.a) * model.directional_color * specular;
    }

    let point_enabled = model.flags.y;
    if point_enabled > 0.5 {
        let light_vector = model.point_position.xyz - input.world_position;
        let distance2 = max(dot(light_vector, light_vector), 1.0);
        let light_dir = normalize(light_vector);
        let diffuse = max(dot(normal, light_dir), 0.0) / (1.0 + distance2 * 0.00002);
        color = color + model.base_color * model.point_color * diffuse;
    }

    color.a = model.base_color.a;
    return clamp(color, vec4<f32>(0.0), vec4<f32>(1.0));
}
"#;

pub(super) const TEXTURED_MODEL_SHADER: &str = r#"
struct ModelUniform {
    model: mat4x4<f32>,
    view_projection: mat4x4<f32>,
    base_color: vec4<f32>,
    emissive_color: vec4<f32>,
    specular_shininess: vec4<f32>,
    ambient_color: vec4<f32>,
    directional_color: vec4<f32>,
    directional_direction: vec4<f32>,
    point_color: vec4<f32>,
    point_position: vec4<f32>,
    flags: vec4<f32>,
};

@group(0) @binding(0)
var<storage, read> models: array<ModelUniform>;

@group(1) @binding(0)
var image_texture: texture_2d<f32>;

@group(1) @binding(1)
var image_sampler: sampler;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) world_position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) uv: vec2<f32>,
    @location(3) @interpolate(flat) model_index: u32,
};

@vertex
fn vs_main(input: VertexInput, @builtin(instance_index) model_index: u32) -> VertexOutput {
    let model = models[model_index];
    let world = model.model * vec4<f32>(input.position, 1.0);
    var output: VertexOutput;
    output.clip_position = model.view_projection * world;
    output.world_position = world.xyz;
    output.normal = normalize((model.model * vec4<f32>(input.normal, 0.0)).xyz);
    output.uv = input.uv;
    output.model_index = model_index;
    return output;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let model = models[input.model_index];
    let normal = normalize(input.normal);
    let sampled = textureSample(image_texture, image_sampler, input.uv) * model.base_color;
    var color = model.emissive_color + sampled * model.ambient_color;

    if model.flags.x > 0.5 {
        let light_dir = normalize(-model.directional_direction.xyz);
        let diffuse = max(dot(normal, light_dir), 0.0);
        color = color + sampled * model.directional_color * diffuse;
    }

    if model.flags.y > 0.5 {
        let light_vector = model.point_position.xyz - input.world_position;
        let distance2 = max(dot(light_vector, light_vector), 1.0);
        let light_dir = normalize(light_vector);
        let diffuse = max(dot(normal, light_dir), 0.0) / (1.0 + distance2 * 0.00002);
        color = color + sampled * model.point_color * diffuse;
    }

    color.a = sampled.a;
    return clamp(color, vec4<f32>(0.0), vec4<f32>(1.0));
}
"#;

pub(super) const PIXEL_PREFIX_SHADER: &str = r#"
struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(1.0, 1.0),
    );
    var uvs = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(1.0, 0.0),
    );
    var output: VertexOutput;
    output.position = vec4<f32>(positions[vertex_index], 0.0, 1.0);
    output.uv = uvs[vertex_index];
    return output;
}

struct PixelPrefix {
    byte_limit: u32,
    stride: u32,
    red_delta: i32,
    green_delta: i32,
};

@group(0) @binding(0)
var source_texture: texture_2d<f32>;

@group(0) @binding(1)
var source_sampler: sampler;

@group(0) @binding(2)
var<uniform> prefix: PixelPrefix;

fn wrap_byte(value: i32) -> f32 {
    return f32(((value % 256) + 256) % 256) / 255.0;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let dims = vec2<u32>(textureDimensions(source_texture));
    let coord = vec2<u32>(min(input.uv * vec2<f32>(dims), vec2<f32>(dims - vec2<u32>(1u, 1u))));
    let pixel_index = coord.y * dims.x + coord.x;
    let base_offset = pixel_index * 4u;
    var color = textureSample(source_texture, source_sampler, input.uv);
    if prefix.stride > 0u {
        if base_offset < prefix.byte_limit && (base_offset % prefix.stride) == 0u {
            color.r = wrap_byte(i32(round(color.r * 255.0)) + prefix.red_delta);
        }
        let green_offset = base_offset + 1u;
        if green_offset < prefix.byte_limit && (green_offset % prefix.stride) == 0u {
            color.g = wrap_byte(i32(round(color.g * 255.0)) + prefix.green_delta);
        }
    }
    return color;
}
"#;

pub(super) const BLEND_ELLIPSE_SHADER: &str = r#"
struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(-1.0, 1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(1.0, 1.0),
    );
    var uvs = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(1.0, 0.0),
    );
    var output: VertexOutput;
    output.position = vec4<f32>(positions[vertex_index], 0.0, 1.0);
    output.uv = uvs[vertex_index];
    return output;
}

struct BlendEllipse {
    center_radius: vec4<f32>,
    color: vec4<f32>,
    mode: u32,
    _padding: vec3<u32>,
};

@group(0) @binding(0)
var source_texture: texture_2d<f32>;

@group(0) @binding(1)
var source_sampler: sampler;

@group(0) @binding(2)
var<uniform> ellipse: BlendEllipse;

fn blend_channel(dst: f32, src: f32, mode: u32) -> f32 {
    if mode == 1u {
        return min(dst + src, 1.0);
    }
    if mode == 2u {
        return min(dst, src);
    }
    if mode == 3u {
        return max(dst, src);
    }
    if mode == 4u {
        return abs(dst - src);
    }
    if mode == 5u {
        return clamp(dst + src - 2.0 * dst * src, 0.0, 1.0);
    }
    if mode == 6u {
        return dst * src;
    }
    if mode == 7u {
        return 1.0 - (1.0 - dst) * (1.0 - src);
    }
    return src;
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let dims = vec2<u32>(textureDimensions(source_texture));
    let coord = vec2<i32>(min(input.uv * vec2<f32>(dims), vec2<f32>(dims - vec2<u32>(1u, 1u))));
    let pixel = vec2<f32>(coord) + vec2<f32>(0.5, 0.5);
    let dst = textureLoad(source_texture, coord, 0);
    let delta = (pixel - ellipse.center_radius.xy) / ellipse.center_radius.zw;
    if dot(delta, delta) > 1.0 {
        return dst;
    }
    let src = ellipse.color;
    let blended = vec3<f32>(
        blend_channel(dst.r, src.r, ellipse.mode),
        blend_channel(dst.g, src.g, ellipse.mode),
        blend_channel(dst.b, src.b, ellipse.mode),
    );
    let alpha = src.a;
    return vec4<f32>(mix(dst.rgb, blended, alpha), dst.a);
}
"#;
