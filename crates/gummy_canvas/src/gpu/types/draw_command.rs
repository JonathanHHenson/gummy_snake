use super::{
    GpuColor, ImageVertex, ModelUniform, PrimitiveInstance, RetainedPrimitiveInstances,
    RetainedTriangleVertices, StrokePathRecord,
};
use crate::types::BlendMode;

#[derive(Debug, PartialEq)]
pub enum DrawCommand {
    Clear(GpuColor),
    Triangles {
        vertices: Vec<([f32; 2], GpuColor)>,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    RetainedTriangles {
        retained: RetainedTriangleVertices,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    PrimitiveInstances {
        instances: Vec<PrimitiveInstance>,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    RetainedPrimitiveInstances {
        retained: RetainedPrimitiveInstances,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    StrokePath {
        records: Vec<StrokePathRecord>,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    FillPath {
        records: Vec<StrokePathRecord>,
        blend_mode: BlendMode,
        clip_id: usize,
    },

    BlendEllipse {
        cx: f32,
        cy: f32,
        rx: f32,
        ry: f32,
        color: GpuColor,
        blend_mode: BlendMode,
    },
    PixelPrefix {
        byte_limit: u32,
        stride: u32,
        red_delta: i32,
        green_delta: i32,
    },
    PixelFilter {
        mode: u32,
        value: f32,
    },

    ErasePrimitiveInstances {
        instances: Vec<PrimitiveInstance>,
        clip_id: usize,
    },
    EraseStrokePath {
        records: Vec<StrokePathRecord>,
        clip_id: usize,
    },
    EraseFillPath {
        records: Vec<StrokePathRecord>,
        clip_id: usize,
    },
    Image {
        key: u64,
        vertices: [([f32; 2], [f32; 2], GpuColor); 6],
        linear: bool,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    ImageBatch {
        key: u64,
        vertices: Vec<ImageVertex>,
        linear: bool,
        blend_mode: BlendMode,
        clip_id: usize,
    },
    Model {
        key: u64,
        index_count: u32,
        uniform: ModelUniform,
    },
    ModelWireframe {
        key: u64,
        index_count: u32,
        uniform: ModelUniform,
    },
    ModelInstances {
        key: u64,
        index_count: u32,
        uniforms: Vec<ModelUniform>,
    },
    TexturedModel {
        model_key: u64,
        texture_key: u64,
        index_count: u32,
        uniform: ModelUniform,
        linear: bool,
    },

    Text {
        text: String,
        x: f32,
        y: f32,
        width: f32,
        height: f32,
        font_size: f32,
        line_height: f32,
        color: GpuColor,
    },
}
