pub(in crate::gpu) const TRIANGLE_SHADER: &str = r#"
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

pub(in crate::gpu) const PROCEDURAL_PRIMITIVE_SHADER: &str = r#"
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
