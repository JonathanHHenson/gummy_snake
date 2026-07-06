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
    @location(7) params: vec4<f32>,
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
    let kind = u32(input.params.x + 0.5);
    var canvas_position = mix(input.bounds.xy, input.bounds.zw, corner);
    if kind == 4u {
        let start = transform_line_point(input.p0, input.p2, input.bounds);
        let end = transform_line_point(input.p1, input.p2, input.bounds);
        let half_width = max(input.params.y * 0.5, 0.5);
        canvas_position = mix(
            min(start, end) - vec2<f32>(half_width, half_width),
            max(start, end) + vec2<f32>(half_width, half_width),
            corner,
        );
    } else if kind == 5u || kind == 7u {
        let c0 = transform_line_point(input.p0, input.p2, input.bounds);
        let c1 = transform_line_point(vec2<f32>(input.p1.x, input.p0.y), input.p2, input.bounds);
        let c2 = transform_line_point(input.p1, input.p2, input.bounds);
        let c3 = transform_line_point(vec2<f32>(input.p0.x, input.p1.y), input.p2, input.bounds);
        let min_corner = min(min(c0, c1), min(c2, c3));
        let max_corner = max(max(c0, c1), max(c2, c3));
        var pad = 0.0;
        if kind == 7u {
            pad = 1.0;
            if input.params.y > 0.0 {
                pad = pad + max(input.params.y * 0.5, 0.5);
            }
        }
        canvas_position = mix(
            min_corner - vec2<f32>(pad, pad),
            max_corner + vec2<f32>(pad, pad),
            corner,
        );
    } else if kind == 6u {
        let c0 = transform_triangle_point(input.p0, input.bounds, input.params);
        let c1 = transform_triangle_point(input.p1, input.bounds, input.params);
        let c2 = transform_triangle_point(input.p2, input.bounds, input.params);
        canvas_position = mix(
            min(min(c0, c1), c2),
            max(max(c0, c1), c2),
            corner,
        );
    }
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
    output.kind = kind;
    output.params = input.params;
    return output;
}

fn triangle_sign(a: vec2<f32>, b: vec2<f32>, c: vec2<f32>) -> f32 {
    return (a.x - c.x) * (b.y - c.y) - (b.x - c.x) * (a.y - c.y);
}

fn transform_line_point(point: vec2<f32>, p2: vec2<f32>, bounds: vec4<f32>) -> vec2<f32> {
    let column_x = p2;
    let column_y = bounds.xy;
    let translation = bounds.zw;
    return vec2<f32>(
        column_x.x * point.x + column_y.x * point.y + translation.x,
        column_x.y * point.x + column_y.y * point.y + translation.y,
    );
}

fn transform_triangle_point(point: vec2<f32>, bounds: vec4<f32>, params: vec4<f32>) -> vec2<f32> {
    let column_x = bounds.xy;
    let column_y = bounds.zw;
    let translation = params.yz;
    return vec2<f32>(
        column_x.x * point.x + column_y.x * point.y + translation.x,
        column_x.y * point.x + column_y.y * point.y + translation.y,
    );
}

fn inverse_line_point(point: vec2<f32>, p2: vec2<f32>, bounds: vec4<f32>) -> vec2<f32> {
    let column_x = p2;
    let column_y = bounds.xy;
    let translation = bounds.zw;
    let determinant = column_x.x * column_y.y - column_x.y * column_y.x;
    if abs(determinant) <= 0.000001 {
        return vec2<f32>(10000000000.0, 10000000000.0);
    }
    let local = point - translation;
    return vec2<f32>(
        (column_y.y * local.x - column_y.x * local.y) / determinant,
        (-column_x.y * local.x + column_x.x * local.y) / determinant,
    );
}

fn distance_to_segment(point: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let segment = b - a;
    let length_squared = max(dot(segment, segment), 0.000001);
    let t = clamp(dot(point - a, segment) / length_squared, 0.0, 1.0);
    let projection = a + segment * t;
    return length(point - projection);
}

fn alpha_coverage(edge_distance: f32) -> f32 {
    let aa = max(length(vec2<f32>(dpdx(edge_distance), dpdy(edge_distance))), 0.75);
    return clamp(0.5 - edge_distance / aa, 0.0, 1.0);
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    var output_color = input.color;
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
    if input.kind == 4u {
        let start = transform_line_point(input.p0, input.p2, input.bounds);
        let end = transform_line_point(input.p1, input.p2, input.bounds);
        let half_width = max(input.params.y * 0.5, 0.5);
        let coverage = alpha_coverage(distance_to_segment(input.canvas_position, start, end) - half_width);
        if coverage <= 0.0 {
            discard;
        }
        output_color.a *= coverage;
    } else if input.kind == 5u {
        let local = inverse_line_point(input.canvas_position, input.p2, input.bounds);
        let min_point = min(input.p0, input.p1);
        let max_point = max(input.p0, input.p1);
        if local.x < min_point.x || local.y < min_point.y || local.x > max_point.x || local.y > max_point.y {
            discard;
        }
    } else if input.kind == 7u {
        let local = inverse_line_point(input.canvas_position, input.p2, input.bounds);
        let center = (input.p0 + input.p1) * 0.5;
        let radius = max(abs(input.p1 - input.p0) * 0.5, vec2<f32>(0.0001, 0.0001));
        let field = length((local - center) / radius) - 1.0;
        let field_per_pixel = max(length(vec2<f32>(dpdx(field), dpdy(field))), 0.000001);
        if input.params.y > 0.0 {
            let half_width = max(input.params.y * 0.5, 0.5);
            let coverage = alpha_coverage(abs(field) / field_per_pixel - half_width);
            if coverage <= 0.0 {
                discard;
            }
            output_color.a *= coverage;
        } else {
            let coverage = alpha_coverage(field / field_per_pixel);
            if coverage <= 0.0 {
                discard;
            }
            output_color.a *= coverage;
        }
    } else if input.kind == 6u {
        let p0 = transform_triangle_point(input.p0, input.bounds, input.params);
        let p1 = transform_triangle_point(input.p1, input.bounds, input.params);
        let p2 = transform_triangle_point(input.p2, input.bounds, input.params);
        let d1 = triangle_sign(input.canvas_position, p0, p1);
        let d2 = triangle_sign(input.canvas_position, p1, p2);
        let d3 = triangle_sign(input.canvas_position, p2, p0);
        let has_neg = d1 < 0.0 || d2 < 0.0 || d3 < 0.0;
        let has_pos = d1 > 0.0 || d2 > 0.0 || d3 > 0.0;
        if has_neg && has_pos {
            discard;
        }
    } else if input.kind == 3u {
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
    return output_color;
}
"#;
