mod blend;
mod blit;
mod gpu;
mod queries;
mod shapes;
mod transform;
mod types;

pub(crate) use blend::{fill_rgba_buffer, rgba_to_present_pixel};
pub(crate) use blit::{blit_affine_region, blit_scaled_region};
pub(crate) use gpu::{gpu_color, push_triangle};
pub(crate) use queries::{clipped_bounds, ellipse_bounds, point_in_polygon, polygon_is_convex};
pub(crate) use shapes::{
    draw_axis_aligned_ellipse, draw_polygon_overlay, draw_polyline_stroke, fill_disc,
    fill_even_odd_polygon, for_even_odd_spans, rasterize_even_odd_mask, stroke_segment,
};
pub(crate) use transform::{
    affine_bounds, axis_aligned_image_destination, clipped_dest_rect, clipped_source_rect,
    image_to_canvas_matrix, matrix_determinant, matrix_inverse, matrix_transform_point,
    point_to_f32, scale_rect, stroke_width,
};
pub(crate) use types::{Matrix, OverlayRegion, Point};
