use crate::canvas_state::Canvas;
use crate::frame_commands::{
    ensure_record_size, ensure_reserved_zero, read_f64, read_i32, read_u64, FrameCommandFamily,
    EFFECT_RECORD_BYTES,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[derive(Clone, Copy)]
enum TypedEffect {
    AdjustPrefix {
        byte_limit: usize,
        stride: usize,
        red_delta: i16,
        green_delta: i16,
    },
    Filter {
        mode: &'static str,
        value: Option<f64>,
    },
}

fn filter_name(code: u8) -> PyResult<&'static str> {
    match code {
        1 => Ok("gray"),
        2 => Ok("invert"),
        3 => Ok("threshold"),
        4 => Ok("blur"),
        5 => Ok("posterize"),
        6 => Ok("erode"),
        7 => Ok("dilate"),
        _ => Err(PyValueError::new_err(format!(
            "Unknown typed frame-command image filter {code}."
        ))),
    }
}

fn decode_effects(records: &[u8]) -> PyResult<Vec<TypedEffect>> {
    ensure_record_size(records, "effect", EFFECT_RECORD_BYTES)?;
    records
        .chunks_exact(EFFECT_RECORD_BYTES)
        .map(|record| {
            ensure_reserved_zero(record, 2..8, "effect")?;
            match record[0] {
                1 => {
                    if record[1] != 0 || read_f64(record, 32) != 0.0 {
                        return Err(PyValueError::new_err(
                            "Typed frame-command prefix effects require zero mode/value fields.",
                        ));
                    }
                    let byte_limit = usize::try_from(read_u64(record, 8)).map_err(|_| {
                        PyValueError::new_err(
                            "Typed frame-command prefix byte limit exceeds this platform.",
                        )
                    })?;
                    let stride = usize::try_from(read_u64(record, 16)).map_err(|_| {
                        PyValueError::new_err(
                            "Typed frame-command prefix stride exceeds this platform.",
                        )
                    })?;
                    let red_delta = i16::try_from(read_i32(record, 24)).map_err(|_| {
                        PyValueError::new_err(
                            "Typed frame-command red delta is outside the supported i16 range.",
                        )
                    })?;
                    let green_delta = i16::try_from(read_i32(record, 28)).map_err(|_| {
                        PyValueError::new_err(
                            "Typed frame-command green delta is outside the supported i16 range.",
                        )
                    })?;
                    Ok(TypedEffect::AdjustPrefix {
                        byte_limit,
                        stride,
                        red_delta,
                        green_delta,
                    })
                }
                2 => {
                    let mode_byte = record[1];
                    let has_value = mode_byte & 0x80 != 0;
                    let mode = filter_name(mode_byte & 0x7f)?;
                    if read_u64(record, 8) != 0
                        || read_u64(record, 16) != 0
                        || read_i32(record, 24) != 0
                        || read_i32(record, 28) != 0
                    {
                        return Err(PyValueError::new_err(
                            "Typed frame-command filter integer fields must be zero.",
                        ));
                    }
                    Ok(TypedEffect::Filter {
                        mode,
                        value: has_value.then(|| read_f64(record, 32)),
                    })
                }
                kind => Err(PyValueError::new_err(format!(
                    "Unknown typed frame-command effect kind {kind}."
                ))),
            }
        })
        .collect()
}

impl Canvas {
    pub(crate) fn apply_effects_packed_impl(&mut self, records: &[u8]) -> PyResult<()> {
        let effects = decode_effects(records)?;
        let record_count = effects.len();
        for effect in effects {
            match effect {
                TypedEffect::AdjustPrefix {
                    byte_limit,
                    stride,
                    red_delta,
                    green_delta,
                } => self.adjust_pixel_prefix_impl(byte_limit, stride, red_delta, green_delta)?,
                TypedEffect::Filter { mode, value } => self.filter_pixels_impl(mode, value)?,
            }
        }
        self.record_frame_command_ingress(FrameCommandFamily::Effect, &[records], record_count);
        self.record_frame_command_ingress(FrameCommandFamily::Barrier, &[], 1);
        Ok(())
    }
}
