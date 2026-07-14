use crate::frame_commands::FrameCommandFamily;
use crate::prelude::*;

pub(super) const LINE_RECORD_BYTES: usize = 32;
pub(super) const PRIMITIVE_RECORD_BYTES: usize = 56;
pub(super) const MIXED_PRIMITIVE_RECORD_BYTES: usize = 64;
pub(super) const FILL_PRIMITIVE_RECORD_BYTES: usize = 60;

type PrimitiveTuple = (u8, f64, f64, f64, f64, f64, f64);
type FillPrimitiveTuple = (u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8);

fn invalid_record_size(family: &str, record_bytes: usize, actual_bytes: usize) -> PyErr {
    PyValueError::new_err(format!(
        "Packed {family} records must use {record_bytes}-byte records; got {actual_bytes} bytes."
    ))
}

fn ensure_record_size(bytes: &[u8], family: &str, record_bytes: usize) -> PyResult<()> {
    if bytes.len() % record_bytes == 0 {
        Ok(())
    } else {
        Err(invalid_record_size(family, record_bytes, bytes.len()))
    }
}

fn read_f64(record: &[u8], offset: usize) -> f64 {
    f64::from_le_bytes(
        record[offset..offset + 8]
            .try_into()
            .expect("packed record slices have a validated fixed width"),
    )
}

fn decode_values(record: &[u8]) -> [f64; 6] {
    std::array::from_fn(|index| read_f64(record, 8 + index * 8))
}

fn ensure_reserved_bytes(record: &[u8], family: &str) -> PyResult<()> {
    if record[1..8] == [0; 7] {
        Ok(())
    } else {
        Err(PyValueError::new_err(format!(
            "Packed {family} record reserved bytes must be zero."
        )))
    }
}

fn ensure_primitive_kind(kind: u8, allow_line: bool) -> PyResult<()> {
    if matches!(kind, 1..=3) || (allow_line && kind == 4) {
        Ok(())
    } else {
        Err(PyValueError::new_err(format!(
            "Unknown primitive batch record kind {kind}."
        )))
    }
}

fn decode_lines(bytes: &[u8]) -> PyResult<Vec<(f64, f64, f64, f64)>> {
    ensure_record_size(bytes, "line", LINE_RECORD_BYTES)?;
    Ok(bytes
        .chunks_exact(LINE_RECORD_BYTES)
        .map(|record| {
            (
                read_f64(record, 0),
                read_f64(record, 8),
                read_f64(record, 16),
                read_f64(record, 24),
            )
        })
        .collect())
}

fn decode_primitives(bytes: &[u8]) -> PyResult<Vec<PrimitiveTuple>> {
    ensure_record_size(bytes, "primitive", PRIMITIVE_RECORD_BYTES)?;
    bytes
        .chunks_exact(PRIMITIVE_RECORD_BYTES)
        .map(|record| {
            ensure_reserved_bytes(record, "primitive")?;
            ensure_primitive_kind(record[0], true)?;
            let values = decode_values(record);
            Ok((
                record[0], values[0], values[1], values[2], values[3], values[4], values[5],
            ))
        })
        .collect()
}

fn decode_fill_primitives(bytes: &[u8]) -> PyResult<Vec<FillPrimitiveTuple>> {
    ensure_record_size(bytes, "fill primitive", FILL_PRIMITIVE_RECORD_BYTES)?;
    bytes
        .chunks_exact(FILL_PRIMITIVE_RECORD_BYTES)
        .map(|record| {
            ensure_reserved_bytes(record, "fill primitive")?;
            ensure_primitive_kind(record[0], false)?;
            let values = decode_values(record);
            Ok((
                record[0], values[0], values[1], values[2], values[3], values[4], values[5],
                record[56], record[57], record[58], record[59],
            ))
        })
        .collect()
}

impl Canvas {
    pub(crate) fn ingest_packed_lines(
        &mut self,
        bytes: &[u8],
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let records = decode_lines(bytes)?;
        let record_count = records.len() as u64;
        self.batch_lines_impl(records, style, matrix)?;
        self.record_packed_primitive_ingress(record_count, &[bytes]);
        Ok(())
    }

    pub(crate) fn ingest_packed_current_lines(&mut self, bytes: &[u8]) -> PyResult<()> {
        let records = decode_lines(bytes)?;
        let record_count = records.len() as u64;
        self.batch_lines_current_impl(records)?;
        self.record_packed_primitive_ingress(record_count, &[bytes]);
        Ok(())
    }

    pub(crate) fn ingest_packed_primitives(
        &mut self,
        bytes: &[u8],
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<()> {
        let records = decode_primitives(bytes)?;
        let record_count = records.len() as u64;
        self.batch_primitives_impl(records, style, matrix)?;
        self.record_packed_primitive_ingress(record_count, &[bytes]);
        Ok(())
    }

    pub(crate) fn ingest_packed_current_primitives(&mut self, bytes: &[u8]) -> PyResult<()> {
        let records = decode_primitives(bytes)?;
        let record_count = records.len() as u64;
        self.batch_primitives_current_impl(records)?;
        self.record_packed_primitive_ingress(record_count, &[bytes]);
        Ok(())
    }

    pub(crate) fn ingest_packed_mixed_primitives(
        &mut self,
        bytes: &[u8],
        styles: &[u8],
        matrices: &[u8],
    ) -> PyResult<()> {
        ensure_record_size(bytes, "mixed primitive", MIXED_PRIMITIVE_RECORD_BYTES)?;
        self.batch_primitives_mixed_packed_impl(bytes, styles, matrices)?;
        self.record_packed_primitive_ingress(
            (bytes.len() / MIXED_PRIMITIVE_RECORD_BYTES) as u64,
            &[bytes, styles, matrices],
        );
        Ok(())
    }

    pub(crate) fn ingest_packed_fill_primitives(
        &mut self,
        bytes: &[u8],
        matrix: Matrix,
    ) -> PyResult<()> {
        let records = decode_fill_primitives(bytes)?;
        let record_count = records.len() as u64;
        self.batch_fill_primitives_impl(records, matrix)?;
        self.record_packed_primitive_ingress(record_count, &[bytes]);
        Ok(())
    }

    fn record_packed_primitive_ingress(&mut self, records: u64, payloads: &[&[u8]]) {
        let bytes = payloads.iter().map(|payload| payload.len()).sum::<usize>();
        self.performance_counters.packed_primitive_records += records;
        self.performance_counters.packed_primitive_bytes += bytes as u64;
        self.record_frame_command_ingress(
            FrameCommandFamily::Primitive,
            payloads,
            records as usize,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn packed_primitive_decoder_rejects_nonzero_reserved_bytes() {
        let mut bytes = vec![0; PRIMITIVE_RECORD_BYTES];
        bytes[1] = 1;
        assert!(decode_primitives(&bytes).is_err());
    }

    #[test]
    fn packed_fill_decoder_rejects_partial_records() {
        assert!(decode_fill_primitives(&[0; FILL_PRIMITIVE_RECORD_BYTES - 1]).is_err());
    }

    #[test]
    fn packed_line_decoder_preserves_values() {
        let mut bytes = Vec::new();
        for value in [1.0_f64, 2.0, 3.0, 4.0] {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        assert_eq!(decode_lines(&bytes).unwrap(), vec![(1.0, 2.0, 3.0, 4.0)]);
    }
}
