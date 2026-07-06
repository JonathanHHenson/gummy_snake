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
