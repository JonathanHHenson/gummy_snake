pub(in crate::gpu) const IMAGE_SHADER: &str = r#"
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
