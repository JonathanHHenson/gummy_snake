pub(in crate::gpu) const MODEL_SHADER: &str = r#"
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

pub(in crate::gpu) const TEXTURED_MODEL_SHADER: &str = r#"
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
