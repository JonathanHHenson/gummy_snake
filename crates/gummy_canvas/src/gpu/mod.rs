//! GPU resource setup, ordered command encoding, and presentation internals.
//!
//! `renderer_state` owns the non-POD resource graph. `types` owns the POD draw,
//! uniform, and vertex records consumed by pipelines and encoders.

mod context;
mod pipeline;
mod render;
mod renderer_state;
mod setup;
mod shaders;
mod surface;
mod textures;
mod types;

#[cfg(test)]
mod tests;

#[allow(unused_imports)]
pub use renderer_state::GpuRenderer;
#[allow(unused_imports)]
pub(crate) use types::ImageVertex;
#[allow(unused_imports)]
pub use types::{
    DrawCommand, GpuColor, ModelUniform, ModelVertex, PrimitiveInstance,
    RetainedPrimitiveInstances, RetainedTriangleVertices, StrokePathRecord,
};
