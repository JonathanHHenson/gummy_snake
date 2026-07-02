mod blend;

mod gpu;
mod queries;

mod transform;
mod types;

pub(crate) use blend::rgba_to_present_pixel;

pub(crate) use gpu::gpu_color;
pub(crate) use queries::polygon_is_convex;

pub(crate) use transform::{
    clipped_source_rect, image_to_canvas_matrix, matrix_determinant, matrix_transform_point,
    point_to_f32, stroke_width,
};
pub(crate) use types::{Matrix, Point};
