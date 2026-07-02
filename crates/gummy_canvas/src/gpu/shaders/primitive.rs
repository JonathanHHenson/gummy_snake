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

pub(in crate::gpu) const STROKE_PATH_SHADER: &str = r#"
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

struct StrokePath {
    records: array<vec4<f32>>,
};

@group(2) @binding(0)
var<storage, read> stroke_path: StrokePath;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) canvas_position: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 1.0),
    );
    let canvas_position = corners[vertex_index] * viewport.size;
    var output: VertexOutput;
    let ndc_x = canvas_position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - canvas_position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.canvas_position = canvas_position;
    return output;
}

fn transform_path_point(p: vec2<f32>) -> vec2<f32> {
    let column_x = stroke_path.records[0u].xy;
    let column_y = stroke_path.records[0u].zw;
    let translation = stroke_path.records[1u].xy;
    let pixel_density = stroke_path.records[1u].z;
    return vec2<f32>(
        column_x.x * p.x + column_y.x * p.y + translation.x,
        column_x.y * p.x + column_y.y * p.y + translation.y,
    ) * pixel_density;
}

fn path_point(index: u32) -> vec2<f32> {
    return transform_path_point(stroke_path.records[4u + index].xy);
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

fn quadratic_point(p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, t: f32) -> vec2<f32> {
    let u = 1.0 - t;
    return u * u * p0 + 2.0 * u * t * p1 + t * t * p2;
}

fn cubic_point(p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, p3: vec2<f32>, t: f32) -> vec2<f32> {
    let u = 1.0 - t;
    return u * u * u * p0 + 3.0 * u * u * t * p1 + 3.0 * u * t * t * p2 + t * t * t * p3;
}

fn sampled_quadratic_distance(point: vec2<f32>, p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>) -> f32 {
    var previous = p0;
    var min_distance = 10000000000.0;
    var sample = 1u;
    loop {
        if sample > 32u {
            break;
        }
        let t = f32(sample) / 32.0;
        let current = quadratic_point(p0, p1, p2, t);
        min_distance = min(min_distance, distance_to_segment(point, previous, current));
        previous = current;
        sample = sample + 1u;
    }
    return min_distance;
}

fn sampled_cubic_distance(point: vec2<f32>, p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, p3: vec2<f32>) -> f32 {
    var previous = p0;
    var min_distance = 10000000000.0;
    var sample = 1u;
    loop {
        if sample > 48u {
            break;
        }
        let t = f32(sample) / 48.0;
        let current = cubic_point(p0, p1, p2, p3, t);
        min_distance = min(min_distance, distance_to_segment(point, previous, current));
        previous = current;
        sample = sample + 1u;
    }
    return min_distance;
}

fn arc_point(center_radius: vec4<f32>, angle: f32) -> vec2<f32> {
    return transform_path_point(
        center_radius.xy + vec2<f32>(cos(angle) * center_radius.z, sin(angle) * center_radius.w)
    );
}

fn sampled_arc_distance(point: vec2<f32>, center_radius: vec4<f32>, start_stop: vec2<f32>, mode: u32) -> f32 {
    let center = transform_path_point(center_radius.xy);
    let start_point = arc_point(center_radius, start_stop.x);
    let end_point = arc_point(center_radius, start_stop.y);
    var previous = start_point;
    var min_distance = 10000000000.0;
    var sample = 1u;
    loop {
        if sample > 96u {
            break;
        }
        let t = f32(sample) / 96.0;
        let angle = mix(start_stop.x, start_stop.y, t);
        let current = arc_point(center_radius, angle);
        min_distance = min(min_distance, distance_to_segment(point, previous, current));
        previous = current;
        sample = sample + 1u;
    }
    if mode == 1u {
        min_distance = min(min_distance, distance_to_segment(point, end_point, start_point));
    } else if mode == 2u {
        min_distance = min(min_distance, distance_to_segment(point, center, start_point));
        min_distance = min(min_distance, distance_to_segment(point, end_point, center));
    }
    return min_distance;
}

fn command_distance(point: vec2<f32>, command_index: u32) -> f32 {
    let base = 4u + command_index * 3u;
    let kind = u32(stroke_path.records[base].x + 0.5);
    let p0 = transform_path_point(stroke_path.records[base].yz);
    if kind == 0u {
        let p1 = transform_path_point(stroke_path.records[base + 1u].xy);
        return distance_to_segment(point, p0, p1);
    }
    if kind == 1u {
        let p1 = transform_path_point(stroke_path.records[base + 1u].xy);
        let p2 = transform_path_point(stroke_path.records[base + 1u].zw);
        return sampled_quadratic_distance(point, p0, p1, p2);
    }
    if kind == 2u {
        let p1 = transform_path_point(stroke_path.records[base + 1u].xy);
        let p2 = transform_path_point(stroke_path.records[base + 1u].zw);
        let p3 = transform_path_point(stroke_path.records[base + 2u].xy);
        return sampled_cubic_distance(point, p0, p1, p2, p3);
    }
    let mode = u32(stroke_path.records[base].y + 0.5);
    return sampled_arc_distance(point, stroke_path.records[base + 1u], stroke_path.records[base + 2u].xy, mode);
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

    let record_count = u32(stroke_path.records[3u].x + 0.5);
    let record_mode = u32(stroke_path.records[3u].z + 0.5);
    let half_width = max(stroke_path.records[1u].w * 0.5, 0.5);
    var min_distance = 10000000000.0;

    if record_mode == 1u {
        if record_count < 1u {
            discard;
        }
        var command_index = 0u;
        loop {
            if command_index >= record_count {
                break;
            }
            min_distance = min(min_distance, command_distance(input.canvas_position, command_index));
            command_index = command_index + 1u;
        }
    } else {
        if record_count < 2u {
            discard;
        }
        let close_path = stroke_path.records[3u].y > 0.5;
        var index = 0u;
        loop {
            if index + 1u >= record_count {
                break;
            }
            min_distance = min(
                min_distance,
                distance_to_segment(input.canvas_position, path_point(index), path_point(index + 1u)),
            );
            index = index + 1u;
        }
        if close_path {
            min_distance = min(
                min_distance,
                distance_to_segment(input.canvas_position, path_point(record_count - 1u), path_point(0u)),
            );
        }
    }

    let coverage = alpha_coverage(min_distance - half_width);
    if coverage <= 0.0 {
        discard;
    }
    var color = stroke_path.records[2u];
    color.a *= coverage;
    return color;
}
"#;

pub(in crate::gpu) const PATH_FILL_SHADER: &str = r#"
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

struct PathFill {
    records: array<vec4<f32>>,
};

@group(2) @binding(0)
var<storage, read> path_fill: PathFill;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) canvas_position: vec2<f32>,
};

struct FillAccumulator {
    min_distance: f32,
    crossings: u32,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var corners = array<vec2<f32>, 6>(
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 0.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(0.0, 1.0),
    );
    let canvas_position = corners[vertex_index] * viewport.size;
    var output: VertexOutput;
    let ndc_x = canvas_position.x / viewport.size.x * 2.0 - 1.0;
    let ndc_y = 1.0 - canvas_position.y / viewport.size.y * 2.0;
    output.position = vec4<f32>(ndc_x, ndc_y, 0.0, 1.0);
    output.canvas_position = canvas_position;
    return output;
}

fn transform_path_point(p: vec2<f32>) -> vec2<f32> {
    let column_x = path_fill.records[0u].xy;
    let column_y = path_fill.records[0u].zw;
    let translation = path_fill.records[1u].xy;
    let pixel_density = path_fill.records[1u].z;
    return vec2<f32>(
        column_x.x * p.x + column_y.x * p.y + translation.x,
        column_x.y * p.x + column_y.y * p.y + translation.y,
    ) * pixel_density;
}

fn path_point(index: u32) -> vec2<f32> {
    return transform_path_point(path_fill.records[4u + index].xy);
}

fn distance_to_segment(point: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let segment = b - a;
    let length_squared = max(dot(segment, segment), 0.000001);
    let t = clamp(dot(point - a, segment) / length_squared, 0.0, 1.0);
    let projection = a + segment * t;
    return length(point - projection);
}

fn segment_crosses_ray(point: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> bool {
    if (a.y > point.y) == (b.y > point.y) {
        return false;
    }
    let t = (point.y - a.y) / (b.y - a.y);
    let x = mix(a.x, b.x, t);
    return x > point.x;
}

fn add_line(acc: FillAccumulator, point: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> FillAccumulator {
    var result = acc;
    result.min_distance = min(result.min_distance, distance_to_segment(point, a, b));
    if segment_crosses_ray(point, a, b) {
        result.crossings = result.crossings + 1u;
    }
    return result;
}

fn alpha_coverage(edge_distance: f32) -> f32 {
    let aa = max(length(vec2<f32>(dpdx(edge_distance), dpdy(edge_distance))), 0.75);
    return clamp(0.5 - edge_distance / aa, 0.0, 1.0);
}

fn quadratic_point(p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, t: f32) -> vec2<f32> {
    let u = 1.0 - t;
    return u * u * p0 + 2.0 * u * t * p1 + t * t * p2;
}

fn cubic_point(p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, p3: vec2<f32>, t: f32) -> vec2<f32> {
    let u = 1.0 - t;
    return u * u * u * p0 + 3.0 * u * u * t * p1 + 3.0 * u * t * t * p2 + t * t * t * p3;
}

fn sampled_quadratic_fill(acc: FillAccumulator, point: vec2<f32>, p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>) -> FillAccumulator {
    var result = acc;
    var previous = p0;
    var sample = 1u;
    loop {
        if sample > 32u {
            break;
        }
        let t = f32(sample) / 32.0;
        let current = quadratic_point(p0, p1, p2, t);
        result = add_line(result, point, previous, current);
        previous = current;
        sample = sample + 1u;
    }
    return result;
}

fn sampled_cubic_fill(acc: FillAccumulator, point: vec2<f32>, p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>, p3: vec2<f32>) -> FillAccumulator {
    var result = acc;
    var previous = p0;
    var sample = 1u;
    loop {
        if sample > 48u {
            break;
        }
        let t = f32(sample) / 48.0;
        let current = cubic_point(p0, p1, p2, p3, t);
        result = add_line(result, point, previous, current);
        previous = current;
        sample = sample + 1u;
    }
    return result;
}

fn arc_point(center_radius: vec4<f32>, angle: f32) -> vec2<f32> {
    return transform_path_point(
        center_radius.xy + vec2<f32>(cos(angle) * center_radius.z, sin(angle) * center_radius.w)
    );
}

fn sampled_arc_fill(acc: FillAccumulator, point: vec2<f32>, center_radius: vec4<f32>, start_stop: vec2<f32>, mode: u32) -> FillAccumulator {
    var result = acc;
    let center = transform_path_point(center_radius.xy);
    let start_point = arc_point(center_radius, start_stop.x);
    let end_point = arc_point(center_radius, start_stop.y);
    var previous = start_point;
    var sample = 1u;
    loop {
        if sample > 96u {
            break;
        }
        let t = f32(sample) / 96.0;
        let angle = mix(start_stop.x, start_stop.y, t);
        let current = arc_point(center_radius, angle);
        result = add_line(result, point, previous, current);
        previous = current;
        sample = sample + 1u;
    }
    if mode == 2u {
        result = add_line(result, point, end_point, center);
        result = add_line(result, point, center, start_point);
    } else {
        result = add_line(result, point, end_point, start_point);
    }
    return result;
}

fn command_fill(acc: FillAccumulator, point: vec2<f32>, command_index: u32) -> FillAccumulator {
    let base = 4u + command_index * 3u;
    let kind = u32(path_fill.records[base].x + 0.5);
    let p0 = transform_path_point(path_fill.records[base].yz);
    if kind == 0u {
        let p1 = transform_path_point(path_fill.records[base + 1u].xy);
        return add_line(acc, point, p0, p1);
    }
    if kind == 1u {
        let p1 = transform_path_point(path_fill.records[base + 1u].xy);
        let p2 = transform_path_point(path_fill.records[base + 1u].zw);
        return sampled_quadratic_fill(acc, point, p0, p1, p2);
    }
    if kind == 2u {
        let p1 = transform_path_point(path_fill.records[base + 1u].xy);
        let p2 = transform_path_point(path_fill.records[base + 1u].zw);
        let p3 = transform_path_point(path_fill.records[base + 2u].xy);
        return sampled_cubic_fill(acc, point, p0, p1, p2, p3);
    }
    let mode = u32(path_fill.records[base].y + 0.5);
    return sampled_arc_fill(acc, point, path_fill.records[base + 1u], path_fill.records[base + 2u].xy, mode);
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

    let record_count = u32(path_fill.records[3u].x + 0.5);
    let record_mode = u32(path_fill.records[3u].z + 0.5);
    var acc: FillAccumulator;
    acc.min_distance = 10000000000.0;
    acc.crossings = 0u;

    if record_mode == 1u {
        if record_count < 1u {
            discard;
        }
        var command_index = 0u;
        loop {
            if command_index >= record_count {
                break;
            }
            acc = command_fill(acc, input.canvas_position, command_index);
            command_index = command_index + 1u;
        }
    } else {
        if record_count < 3u {
            discard;
        }
        let close_path = path_fill.records[3u].y > 0.5;
        var index = 0u;
        loop {
            if index + 1u >= record_count {
                break;
            }
            acc = add_line(acc, input.canvas_position, path_point(index), path_point(index + 1u));
            index = index + 1u;
        }
        if close_path {
            acc = add_line(acc, input.canvas_position, path_point(record_count - 1u), path_point(0u));
        }
    }

    let inside = (acc.crossings % 2u) == 1u;
    var signed_distance = acc.min_distance;
    if inside {
        signed_distance = -acc.min_distance;
    }
    let coverage = alpha_coverage(signed_distance);
    if coverage <= 0.0 {
        discard;
    }
    var color = path_fill.records[2u];
    color.a *= coverage;
    return color;
}
"#;
