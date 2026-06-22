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
