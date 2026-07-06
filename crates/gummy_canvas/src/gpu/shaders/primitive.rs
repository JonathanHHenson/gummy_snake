mod path_fill;
mod procedural;
mod stroke;
mod triangle;

pub(in crate::gpu) use path_fill::PATH_FILL_SHADER;
pub(in crate::gpu) use procedural::PROCEDURAL_PRIMITIVE_SHADER;
pub(in crate::gpu) use stroke::STROKE_PATH_SHADER;
pub(in crate::gpu) use triangle::TRIANGLE_SHADER;
