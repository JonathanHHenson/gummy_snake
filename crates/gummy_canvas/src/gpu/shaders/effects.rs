pub(in crate::gpu) const PIXEL_PREFIX_SHADER: &str = r#"
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

pub(in crate::gpu) const PIXEL_FILTER_SHADER: &str = r#"
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

struct PixelFilter {
    mode: u32,
    value: f32,
    _padding: vec2<u32>,
};

@group(0) @binding(0)
var source_texture: texture_2d<f32>;

@group(0) @binding(1)
var source_sampler: sampler;

@group(0) @binding(2)
var<uniform> pixel_filter: PixelFilter;

fn clamp_coord(coord: vec2<i32>, dims: vec2<i32>) -> vec2<i32> {
    return clamp(coord, vec2<i32>(0, 0), dims - vec2<i32>(1, 1));
}

fn load_pixel(coord: vec2<i32>, dims: vec2<i32>) -> vec4<f32> {
    return textureLoad(source_texture, clamp_coord(coord, dims), 0);
}

fn luma(color: vec3<f32>) -> f32 {
    return dot(color, vec3<f32>(0.299, 0.587, 0.114));
}

fn blur3(coord: vec2<i32>, dims: vec2<i32>) -> vec4<f32> {
    var sum = vec4<f32>(0.0);
    for (var dy = -1; dy <= 1; dy = dy + 1) {
        for (var dx = -1; dx <= 1; dx = dx + 1) {
            sum = sum + load_pixel(coord + vec2<i32>(dx, dy), dims);
        }
    }
    return sum / 9.0;
}

fn erode3(coord: vec2<i32>, dims: vec2<i32>) -> vec4<f32> {
    var result = vec4<f32>(1.0);
    for (var dy = -1; dy <= 1; dy = dy + 1) {
        for (var dx = -1; dx <= 1; dx = dx + 1) {
            result = min(result, load_pixel(coord + vec2<i32>(dx, dy), dims));
        }
    }
    return vec4<f32>(result.rgb, load_pixel(coord, dims).a);
}

fn dilate3(coord: vec2<i32>, dims: vec2<i32>) -> vec4<f32> {
    var result = vec4<f32>(0.0);
    for (var dy = -1; dy <= 1; dy = dy + 1) {
        for (var dx = -1; dx <= 1; dx = dx + 1) {
            result = max(result, load_pixel(coord + vec2<i32>(dx, dy), dims));
        }
    }
    return vec4<f32>(result.rgb, load_pixel(coord, dims).a);
}

@fragment
fn fs_main(input: VertexOutput) -> @location(0) vec4<f32> {
    let dims_u = vec2<u32>(textureDimensions(source_texture));
    let dims = vec2<i32>(dims_u);
    let coord = vec2<i32>(min(input.uv * vec2<f32>(dims_u), vec2<f32>(dims_u - vec2<u32>(1u, 1u))));
    let color = textureLoad(source_texture, coord, 0);
    if pixel_filter.mode == 1u {
        let gray = luma(color.rgb);
        return vec4<f32>(gray, gray, gray, color.a);
    }
    if pixel_filter.mode == 2u {
        return vec4<f32>(1.0 - color.rgb, color.a);
    }
    if pixel_filter.mode == 3u {
        let threshold = clamp(pixel_filter.value, 0.0, 1.0);
        let bw = select(0.0, 1.0, luma(color.rgb) >= threshold);
        return vec4<f32>(bw, bw, bw, color.a);
    }
    if pixel_filter.mode == 4u {
        return blur3(coord, dims);
    }
    if pixel_filter.mode == 5u {
        let levels = max(2.0, floor(pixel_filter.value));
        let scale = levels - 1.0;
        return vec4<f32>(floor(color.rgb * scale + vec3<f32>(0.5)) / scale, color.a);
    }
    if pixel_filter.mode == 6u {
        return erode3(coord, dims);
    }
    if pixel_filter.mode == 7u {
        return dilate3(coord, dims);
    }
    return color;
}
"#;

pub(in crate::gpu) const DESTINATION_BLEND_SHADER: &str = r#"
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

struct DestinationBlend {
    center_extent: vec4<f32>,
    color: vec4<f32>,
    mode: u32,
    shape: u32,
    _padding: vec2<u32>,
};

@group(0) @binding(0)
var source_texture: texture_2d<f32>;

@group(0) @binding(1)
var source_sampler: sampler;

@group(0) @binding(2)
var<uniform> destination_blend: DestinationBlend;

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
    let delta = pixel - destination_blend.center_extent.xy;
    if destination_blend.shape == 0u {
        let normalized = delta / destination_blend.center_extent.zw;
        if dot(normalized, normalized) > 1.0 {
            return dst;
        }
    } else if any(abs(delta) > destination_blend.center_extent.zw) {
        return dst;
    }
    let src = destination_blend.color;
    let blended = vec3<f32>(
        blend_channel(dst.r, src.r, destination_blend.mode),
        blend_channel(dst.g, src.g, destination_blend.mode),
        blend_channel(dst.b, src.b, destination_blend.mode),
    );
    let alpha = src.a;
    return vec4<f32>(mix(dst.rgb, blended, alpha), dst.a);
}
"#;
