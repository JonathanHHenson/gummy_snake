mod instances;
mod paths;
mod primitives;
mod records;

pub(in crate::canvas) use instances::{
    procedural_ellipse_instance, procedural_rect_instance, procedural_triangle_instance,
};

#[cfg(test)]
mod tests;
