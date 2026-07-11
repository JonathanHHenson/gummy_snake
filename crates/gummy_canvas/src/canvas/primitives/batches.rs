use crate::prelude::*;
mod fill;
mod helpers;

use crate::runtime::style::*;
use helpers::{
    unknown_primitive_batch_kind_message, PrimitiveBatchKind, PrimitiveBatchRecord,
    PrimitiveBatchTuple,
};

impl Canvas {
    pub(crate) fn batch_primitives_impl(
        &mut self,
        records: Vec<PrimitiveBatchTuple>,
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let style = self.cached_style(style)?;
        self.batch_primitives_with_style(
            records
                .into_iter()
                .map(PrimitiveBatchRecord::from)
                .collect(),
            &style,
            matrix,
        )
    }

    pub(crate) fn batch_primitives_current_impl(
        &mut self,
        records: Vec<PrimitiveBatchTuple>,
    ) -> PyResult<()> {
        let style = self.current_style.clone();
        self.batch_primitives_with_style(
            records
                .into_iter()
                .map(PrimitiveBatchRecord::from)
                .collect(),
            &style,
            self.current_matrix,
        )
    }

    fn batch_primitives_with_style(
        &mut self,
        records: Vec<PrimitiveBatchRecord>,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        if records.is_empty() {
            return Ok(());
        }
        let ingest_start = std::time::Instant::now();
        ensure_supported_style(style)?;
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records += records.len() as u64;
        for record in records {
            self.draw_primitive_batch_record(record, style, matrix)?;
        }
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        Ok(())
    }

    fn draw_primitive_batch_record(
        &mut self,
        record: PrimitiveBatchRecord,
        style: &Style,
        matrix: Matrix,
    ) -> PyResult<()> {
        match PrimitiveBatchKind::try_from(record.kind) {
            Ok(PrimitiveBatchKind::Rect) => {
                self.rect_with_style(record.a, record.b, record.c, record.d, style, matrix)
            }
            Ok(PrimitiveBatchKind::Triangle) => self.triangle_with_style(
                record.a, record.b, record.c, record.d, record.e, record.f, style, matrix,
            ),
            Ok(PrimitiveBatchKind::Ellipse) => {
                self.ellipse_with_style(record.a, record.b, record.c, record.d, style, matrix)
            }
            Ok(PrimitiveBatchKind::Line) => {
                self.line_with_style(record.a, record.b, record.c, record.d, style, matrix)
            }
            Err(kind) => Err(PyValueError::new_err(unknown_primitive_batch_kind_message(
                kind,
            ))),
        }
    }

    pub(crate) fn batch_primitives_mixed_impl(
        &mut self,
        records: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let sequence = records.downcast::<PyList>()?;
        if sequence.is_empty() {
            return Ok(());
        }
        let ingest_start = std::time::Instant::now();
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records += sequence.len() as u64;
        for item in sequence.iter() {
            let record = item.downcast::<PyTuple>()?;
            if record.len() != 9 {
                return Err(PyValueError::new_err(
                    "Mixed primitive records must contain kind, six coordinates, style, and matrix.",
                ));
            }
            let primitive = PrimitiveBatchRecord {
                kind: record.get_item(0)?.extract::<u8>()?,
                a: record.get_item(1)?.extract::<f64>()?,
                b: record.get_item(2)?.extract::<f64>()?,
                c: record.get_item(3)?.extract::<f64>()?,
                d: record.get_item(4)?.extract::<f64>()?,
                e: record.get_item(5)?.extract::<f64>()?,
                f: record.get_item(6)?.extract::<f64>()?,
            };
            let style_obj = record.get_item(7)?;
            let style = self.cached_style(&style_obj)?;
            ensure_supported_style(&style)?;
            let matrix = record.get_item(8)?.extract::<Matrix>()?;
            self.draw_primitive_batch_record(primitive, &style, matrix)?;
        }
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        Ok(())
    }
}
