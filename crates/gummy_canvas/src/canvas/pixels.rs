use crate::canvas_state::Canvas;
use crate::runtime::style::*;
use pyo3::prelude::*;

mod effects;
mod export;
mod load;
mod update;

impl Canvas {
    pub(crate) fn blend_region_impl(
        &mut self,
        _source_pixels: Option<Vec<u8>>,
        _source_width: Option<usize>,
        _source_height: Option<usize>,
        _source: (i64, i64, i64, i64),
        _destination: (i64, i64, i64, i64),
        mode: &str,
    ) -> PyResult<()> {
        ensure_supported_blend_mode(mode)?;
        self.prepare_cpu_composite()
    }
}
