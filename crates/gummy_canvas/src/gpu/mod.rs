mod pipeline;
mod render;
mod setup;
mod shaders;
mod surface;
mod textures;
mod types;

#[cfg(test)]
mod tests;

#[allow(unused_imports)]
pub(crate) use types::ImageVertex;
#[allow(unused_imports)]
pub use types::{
    DrawCommand, GpuColor, GpuRenderer, ModelUniform, ModelVertex, PrimitiveInstance,
    RetainedPrimitiveInstances, RetainedTriangleVertices,
};
