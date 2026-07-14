use crate::canvas_state::Canvas;
use crate::raster::Matrix;
use pyo3::prelude::*;
use pyo3::types::PyAny;

mod atlas;
mod batch;
mod cached;
mod canvas_image;
mod helpers;
mod records;

pub(crate) use batch::{
    BatchCanvasImage, BatchUniqueImage, ImageBatchBuilder, IMAGE_ATLAS_MAX_UNIQUE_IMAGES,
};

impl Canvas {
    pub(crate) fn draw_image_impl(
        &mut self,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        self.draw_image_pixels(
            &image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            style,
            matrix,
            source,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn draw_image_current_impl(
        &mut self,
        image_pixels: Vec<u8>,
        image_width: usize,
        image_height: usize,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        let matrix = self.current_matrix;
        self.draw_image_pixels_with_style(
            &image_pixels,
            image_width,
            image_height,
            dx,
            dy,
            dw,
            dh,
            &style,
            matrix,
            source,
        )
    }
}
