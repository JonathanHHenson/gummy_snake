use crate::frame_commands::{
    ensure_record_size, read_f64, read_u32, FrameCommandFamily, TEXT_RECORD_BYTES,
};
use crate::prelude::*;

fn decode_text_records(records: &[u8], utf8: &[u8]) -> PyResult<Vec<(String, f64, f64)>> {
    ensure_record_size(records, "text", TEXT_RECORD_BYTES)?;
    records
        .chunks_exact(TEXT_RECORD_BYTES)
        .map(|record| {
            let offset = read_u32(record, 0) as usize;
            let length = read_u32(record, 4) as usize;
            let end = offset.checked_add(length).ok_or_else(|| {
                PyValueError::new_err("Typed frame-command text range overflowed.")
            })?;
            let bytes = utf8.get(offset..end).ok_or_else(|| {
                PyValueError::new_err(
                    "Typed frame-command text range is outside the UTF-8 payload.",
                )
            })?;
            let value = std::str::from_utf8(bytes).map_err(|_| {
                PyValueError::new_err("Typed frame-command text payload is not valid UTF-8.")
            })?;
            Ok((value.to_string(), read_f64(record, 8), read_f64(record, 16)))
        })
        .collect()
}

impl Canvas {
    pub(crate) fn text_batch_packed_impl(
        &mut self,
        records: &[u8],
        utf8: &[u8],
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        final_batch: bool,
    ) -> PyResult<bool> {
        let items = decode_text_records(records, utf8)?;
        let record_count = items.len();
        let reused = if final_batch {
            self.text_batch_frame_impl(items, style, matrix)?
        } else {
            self.text_batch_impl(items, style, matrix)?;
            false
        };
        self.record_frame_command_ingress(FrameCommandFamily::Text, &[records, utf8], record_count);
        Ok(reused)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decoder_rejects_invalid_utf8_transactionally() {
        let mut record = Vec::new();
        record.extend_from_slice(&0_u32.to_le_bytes());
        record.extend_from_slice(&1_u32.to_le_bytes());
        record.extend_from_slice(&1.0_f64.to_le_bytes());
        record.extend_from_slice(&2.0_f64.to_le_bytes());
        assert!(decode_text_records(&record, &[0xff]).is_err());
    }
}
