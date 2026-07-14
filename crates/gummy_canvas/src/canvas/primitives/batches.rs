use crate::canvas_state::Canvas;
use crate::raster::Matrix;
use crate::types::Style;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;
mod fill;
mod helpers;

use crate::frame_commands::{decode_matrices, decode_primitive_styles};
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

    pub(crate) fn batch_primitives_mixed_packed_impl(
        &mut self,
        bytes: &[u8],
        styles: &[u8],
        matrices: &[u8],
    ) -> PyResult<()> {
        const RECORD_BYTES: usize = 64;
        if bytes.len() % RECORD_BYTES != 0 {
            return Err(PyValueError::new_err(format!(
                "Packed mixed primitive records must use {RECORD_BYTES}-byte records; got {} bytes.",
                bytes.len()
            )));
        }
        if bytes.is_empty() {
            return Ok(());
        }
        let parsed_styles = decode_primitive_styles(styles)?;
        let parsed_matrices = decode_matrices(matrices)?;
        let parsed_records = bytes
            .chunks_exact(RECORD_BYTES)
            .map(|record| {
                if record[1..8] != [0; 7] {
                    return Err(PyValueError::new_err(
                        "Packed mixed primitive record reserved bytes must be zero.",
                    ));
                }
                let value = |index: usize| {
                    let offset = 8 + index * 8;
                    f64::from_le_bytes(
                        record[offset..offset + 8]
                            .try_into()
                            .expect("mixed primitive records have a validated fixed width"),
                    )
                };
                let style_index = u32::from_le_bytes(
                    record[56..60]
                        .try_into()
                        .expect("mixed primitive records have a validated fixed width"),
                ) as usize;
                let matrix_index = u32::from_le_bytes(
                    record[60..64]
                        .try_into()
                        .expect("mixed primitive records have a validated fixed width"),
                ) as usize;
                if style_index >= parsed_styles.len() {
                    return Err(PyValueError::new_err(format!(
                        "Packed primitive style index {style_index} is invalid."
                    )));
                }
                if matrix_index >= parsed_matrices.len() {
                    return Err(PyValueError::new_err(format!(
                        "Packed primitive matrix index {matrix_index} is invalid."
                    )));
                }
                let record = PrimitiveBatchRecord {
                    kind: record[0],
                    a: value(0),
                    b: value(1),
                    c: value(2),
                    d: value(3),
                    e: value(4),
                    f: value(5),
                };
                PrimitiveBatchKind::try_from(record.kind).map_err(|kind| {
                    PyValueError::new_err(unknown_primitive_batch_kind_message(kind))
                })?;
                Ok((record, style_index, matrix_index))
            })
            .collect::<PyResult<Vec<_>>>()?;
        let ingest_start = std::time::Instant::now();
        self.performance_counters.native_primitive_batches += 1;
        self.performance_counters.native_primitive_records += parsed_records.len() as u64;
        for (record, style_index, matrix_index) in parsed_records {
            self.draw_primitive_batch_record(
                record,
                &parsed_styles[style_index],
                parsed_matrices[matrix_index],
            )?;
        }
        self.performance_counters.native_command_ingest_time_ms +=
            ingest_start.elapsed().as_secs_f64() * 1000.0;
        Ok(())
    }
}
