use crate::prelude::*;

pub(crate) const FRAME_COMMAND_ABI_VERSION: u32 = 1;
pub(crate) const PRIMITIVE_STYLE_RECORD_BYTES: usize = 24;
pub(crate) const MATRIX_RECORD_BYTES: usize = 48;
pub(crate) const PATH_POINT_RECORD_BYTES: usize = 16;
pub(crate) const PATH_CONTOUR_RECORD_BYTES: usize = 4;
pub(crate) const IMAGE_RECORD_BYTES: usize = 104;
pub(crate) const TEXT_RECORD_BYTES: usize = 24;
pub(crate) const MODEL_TRANSFORM_RECORD_BYTES: usize = 128;
pub(crate) const EFFECT_RECORD_BYTES: usize = 40;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum FrameCommandFamily {
    Primitive,
    Path,
    Image,
    Text,
    Model,
    Effect,
    Barrier,
}

impl FrameCommandFamily {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Primitive => "primitive",
            Self::Path => "path",
            Self::Image => "image",
            Self::Text => "text",
            Self::Model => "model",
            Self::Effect => "effect",
            Self::Barrier => "barrier",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct FrameCommandSegment {
    pub(crate) family: FrameCommandFamily,
    pub(crate) offset: usize,
    pub(crate) byte_len: usize,
    pub(crate) record_count: usize,
}

#[derive(Debug, Default)]
pub(crate) struct FrameCommandRecorder {
    generation: u64,
    storage: Vec<u8>,
    segments: Vec<FrameCommandSegment>,
}

impl FrameCommandRecorder {
    pub(crate) fn begin_frame(&mut self) {
        self.generation = self.generation.wrapping_add(1).max(1);
        self.storage.clear();
        self.segments.clear();
    }

    pub(crate) fn record(
        &mut self,
        family: FrameCommandFamily,
        payloads: &[&[u8]],
        record_count: usize,
    ) -> bool {
        let offset = self.storage.len();
        let byte_len = payloads.iter().map(|payload| payload.len()).sum::<usize>();
        let previous_capacity = self.storage.capacity();
        self.storage.reserve(byte_len);
        for payload in payloads {
            self.storage.extend_from_slice(payload);
        }
        self.segments.push(FrameCommandSegment {
            family,
            offset,
            byte_len,
            record_count,
        });
        self.storage.capacity() > previous_capacity
    }

    pub(crate) fn generation(&self) -> u64 {
        self.generation
    }

    pub(crate) fn storage_len(&self) -> usize {
        self.storage.len()
    }

    pub(crate) fn storage_capacity(&self) -> usize {
        self.storage.capacity()
    }

    pub(crate) fn segments(&self) -> &[FrameCommandSegment] {
        &self.segments
    }
}

pub(crate) fn invalid_record_size(family: &str, record_bytes: usize, actual: usize) -> PyErr {
    PyValueError::new_err(format!(
        "Typed frame-command {family} records must use {record_bytes}-byte records; got {actual} bytes. Rebuild gummy_canvas if the producer uses a different frame-command ABI."
    ))
}

pub(crate) fn ensure_record_size(bytes: &[u8], family: &str, record_bytes: usize) -> PyResult<()> {
    if bytes.len() % record_bytes == 0 {
        Ok(())
    } else {
        Err(invalid_record_size(family, record_bytes, bytes.len()))
    }
}

pub(crate) fn ensure_reserved_zero(
    record: &[u8],
    range: std::ops::Range<usize>,
    family: &str,
) -> PyResult<()> {
    if record[range].iter().all(|value| *value == 0) {
        Ok(())
    } else {
        Err(PyValueError::new_err(format!(
            "Typed frame-command {family} reserved bytes must be zero. Rebuild gummy_canvas if the producer uses a different frame-command ABI."
        )))
    }
}

pub(crate) fn read_u32(record: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(
        record[offset..offset + 4]
            .try_into()
            .expect("validated record width"),
    )
}

pub(crate) fn read_u64(record: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(
        record[offset..offset + 8]
            .try_into()
            .expect("validated record width"),
    )
}

pub(crate) fn read_i32(record: &[u8], offset: usize) -> i32 {
    i32::from_le_bytes(
        record[offset..offset + 4]
            .try_into()
            .expect("validated record width"),
    )
}

pub(crate) fn read_f64(record: &[u8], offset: usize) -> f64 {
    f64::from_le_bytes(
        record[offset..offset + 8]
            .try_into()
            .expect("validated record width"),
    )
}

fn decode_blend_mode(code: u8) -> PyResult<(BlendMode, String)> {
    let value = match code {
        0 => (BlendMode::Blend, "blend"),
        1 => (BlendMode::Add, "add"),
        2 => (BlendMode::Darkest, "darkest"),
        3 => (BlendMode::Lightest, "lightest"),
        4 => (BlendMode::Difference, "difference"),
        5 => (BlendMode::Exclusion, "exclusion"),
        6 => (BlendMode::Multiply, "multiply"),
        7 => (BlendMode::Replace, "replace"),
        8 => (BlendMode::Screen, "screen"),
        _ => {
            return Err(PyValueError::new_err(format!(
                "Unknown typed frame-command blend mode {code}."
            )))
        }
    };
    Ok((value.0, value.1.to_string()))
}

pub(crate) fn decode_primitive_styles(bytes: &[u8]) -> PyResult<Vec<Style>> {
    ensure_record_size(bytes, "primitive style", PRIMITIVE_STYLE_RECORD_BYTES)?;
    bytes
        .chunks_exact(PRIMITIVE_STYLE_RECORD_BYTES)
        .map(|record| {
            ensure_reserved_zero(record, 2..8, "primitive style")?;
            let flags = record[0];
            if flags & !0b111 != 0 {
                return Err(PyValueError::new_err(format!(
                    "Unknown typed frame-command primitive style flags {flags:#x}."
                )));
            }
            let (blend_mode_kind, blend_mode) = decode_blend_mode(record[1])?;
            let fill = (flags & 0b001 != 0).then(|| Rgba {
                r: record[8],
                g: record[9],
                b: record[10],
                a: record[11],
            });
            let stroke = (flags & 0b010 != 0).then(|| Rgba {
                r: record[12],
                g: record[13],
                b: record[14],
                a: record[15],
            });
            let mut style = Style::default();
            style.fill = fill;
            style.stroke = stroke;
            style.stroke_weight = read_f64(record, 16);
            style.blend_mode = blend_mode;
            style.blend_mode_kind = blend_mode_kind;
            style.erasing = flags & 0b100 != 0;
            crate::runtime::style::ensure_supported_style(&style)?;
            Ok(style)
        })
        .collect()
}

pub(crate) fn decode_matrices(bytes: &[u8]) -> PyResult<Vec<Matrix>> {
    ensure_record_size(bytes, "matrix", MATRIX_RECORD_BYTES)?;
    Ok(bytes
        .chunks_exact(MATRIX_RECORD_BYTES)
        .map(|record| {
            (
                read_f64(record, 0),
                read_f64(record, 8),
                read_f64(record, 16),
                read_f64(record, 24),
                read_f64(record, 32),
                read_f64(record, 40),
            )
        })
        .collect())
}

pub(crate) fn decode_path(
    points: &[u8],
    contour_ends: &[u8],
) -> PyResult<(Vec<(f64, f64)>, Vec<Vec<(f64, f64)>>)> {
    ensure_record_size(points, "path point", PATH_POINT_RECORD_BYTES)?;
    ensure_record_size(contour_ends, "path contour", PATH_CONTOUR_RECORD_BYTES)?;
    let points = points
        .chunks_exact(PATH_POINT_RECORD_BYTES)
        .map(|record| (read_f64(record, 0), read_f64(record, 8)))
        .collect::<Vec<_>>();
    let ends = contour_ends
        .chunks_exact(PATH_CONTOUR_RECORD_BYTES)
        .map(|record| read_u32(record, 0) as usize)
        .collect::<Vec<_>>();
    if ends.is_empty() {
        return Err(PyValueError::new_err(
            "Typed frame-command paths require at least one contour-end record.",
        ));
    }
    let mut start = 0;
    let mut groups = Vec::with_capacity(ends.len());
    for end in ends {
        if end < start || end > points.len() {
            return Err(PyValueError::new_err(
                "Typed frame-command path contour offsets must be monotonic and within the point buffer.",
            ));
        }
        groups.push(points[start..end].to_vec());
        start = end;
    }
    if start != points.len() {
        return Err(PyValueError::new_err(
            "Typed frame-command path contour offsets must consume the complete point buffer.",
        ));
    }
    let mut groups = groups.into_iter();
    let outer = groups.next().expect("at least one contour was validated");
    Ok((outer, groups.collect()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recorder_reuses_storage_and_preserves_family_order() {
        let mut recorder = FrameCommandRecorder::default();
        recorder.begin_frame();
        recorder.record(FrameCommandFamily::Primitive, &[&[1, 2]], 1);
        recorder.record(FrameCommandFamily::Text, &[&[3], &[4, 5]], 2);
        assert_eq!(recorder.storage_len(), 5);
        assert_eq!(recorder.segments().len(), 2);
        assert_eq!(recorder.segments()[0].family, FrameCommandFamily::Primitive);
        assert_eq!(recorder.segments()[1].family, FrameCommandFamily::Text);
        let capacity = recorder.storage_capacity();
        recorder.begin_frame();
        assert_eq!(recorder.storage_len(), 0);
        assert_eq!(recorder.storage_capacity(), capacity);
        assert_eq!(recorder.generation(), 2);
    }

    #[test]
    fn path_decoder_rejects_incomplete_contour_coverage() {
        let mut points = Vec::new();
        points.extend_from_slice(&1.0_f64.to_le_bytes());
        points.extend_from_slice(&2.0_f64.to_le_bytes());
        assert!(decode_path(&points, &0_u32.to_le_bytes()).is_err());
    }
}
