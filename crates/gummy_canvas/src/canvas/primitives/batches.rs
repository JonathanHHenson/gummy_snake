mod fill;
mod helpers;

use super::{
    PRIMITIVE_BATCH_ELLIPSE, PRIMITIVE_BATCH_LINE, PRIMITIVE_BATCH_RECT, PRIMITIVE_BATCH_TRIANGLE,
};
use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn batch_primitives_impl(
        &mut self,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.batch_primitives_with_style(records, &style, matrix)
    }

    pub(crate) fn batch_primitives_current_impl(
        &mut self,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.batch_primitives_with_style(records, &style, self.current_matrix)
    }

    pub(crate) fn batch_primitives_with_style(
        &mut self,
        records: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        if records.is_empty() {
            return Ok(());
        }
        ensure_supported_style(style)?;
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records += records.len() as u64;
        for (kind, a, b, c, d, e, f) in records {
            match kind {
                PRIMITIVE_BATCH_RECT => self.rect_with_style(a, b, c, d, style, matrix)?,
                PRIMITIVE_BATCH_TRIANGLE => {
                    self.triangle_with_style(a, b, c, d, e, f, style, matrix)?
                }
                PRIMITIVE_BATCH_ELLIPSE => self.ellipse_with_style(a, b, c, d, style, matrix)?,
                PRIMITIVE_BATCH_LINE => self.line_with_style(a, b, c, d, style, matrix)?,
                _ => {
                    return Err(PyValueError::new_err(format!(
                        "Unknown primitive batch record kind {kind}."
                    )));
                }
            }
        }
        Ok(())
    }

    pub(crate) fn batch_primitives_mixed_impl(
        &mut self,
        records: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let sequence = records.downcast::<PyList>()?;
        if sequence.is_empty() {
            return Ok(());
        }
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records += sequence.len() as u64;
        for item in sequence.iter() {
            let record = item.downcast::<PyTuple>()?;
            if record.len() != 9 {
                return Err(PyValueError::new_err(
                    "Mixed primitive records must contain kind, six coordinates, style, and matrix.",
                ));
            }
            let kind = record.get_item(0)?.extract::<u8>()?;
            let a = record.get_item(1)?.extract::<f64>()?;
            let b = record.get_item(2)?.extract::<f64>()?;
            let c = record.get_item(3)?.extract::<f64>()?;
            let d = record.get_item(4)?.extract::<f64>()?;
            let e = record.get_item(5)?.extract::<f64>()?;
            let f = record.get_item(6)?.extract::<f64>()?;
            let style_obj = record.get_item(7)?;
            let style = self.cached_style(&style_obj)?;
            ensure_supported_style(&style)?;
            let matrix = record.get_item(8)?.extract::<Matrix>()?;
            match kind {
                PRIMITIVE_BATCH_RECT => self.rect_with_style(a, b, c, d, &style, matrix)?,
                PRIMITIVE_BATCH_TRIANGLE => {
                    self.triangle_with_style(a, b, c, d, e, f, &style, matrix)?
                }
                PRIMITIVE_BATCH_ELLIPSE => self.ellipse_with_style(a, b, c, d, &style, matrix)?,
                PRIMITIVE_BATCH_LINE => self.line_with_style(a, b, c, d, &style, matrix)?,
                _ => {
                    return Err(PyValueError::new_err(format!(
                        "Unknown primitive batch record kind {kind}."
                    )));
                }
            }
        }
        Ok(())
    }
}
