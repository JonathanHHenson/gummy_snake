use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::fs;

#[pyclass(name = "CanvasSound", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasSound {
    path: String,
    bytes: Vec<u8>,
    duration: Option<f64>,
}

#[pymethods]
impl CanvasSound {
    #[staticmethod]
    fn from_file(path: &str) -> PyResult<Self> {
        let bytes = fs::read(path)
            .map_err(|err| PyValueError::new_err(format!("Could not load sound {path}: {err}")))?;
        let duration = wav_duration_seconds(&bytes)?;
        Ok(Self {
            path: path.to_owned(),
            bytes,
            duration,
        })
    }

    #[getter]
    fn path(&self) -> &str {
        &self.path
    }

    #[getter]
    fn duration(&self) -> Option<f64> {
        self.duration
    }

    #[getter]
    fn byte_len(&self) -> usize {
        self.bytes.len()
    }

    fn to_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, &self.bytes)
    }
}

fn wav_duration_seconds(bytes: &[u8]) -> PyResult<Option<f64>> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Ok(None);
    }

    let mut offset = 12usize;
    let mut channels: Option<u16> = None;
    let mut sample_rate: Option<u32> = None;
    let mut bits_per_sample: Option<u16> = None;
    let mut data_len: Option<u32> = None;

    while offset.checked_add(8).is_some_and(|end| end <= bytes.len()) {
        let chunk_id = &bytes[offset..offset + 4];
        let chunk_len = u32::from_le_bytes([
            bytes[offset + 4],
            bytes[offset + 5],
            bytes[offset + 6],
            bytes[offset + 7],
        ]);
        offset += 8;
        let chunk_len_usize = chunk_len as usize;
        if offset
            .checked_add(chunk_len_usize)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(PyValueError::new_err(
                "Could not load WAV sound: malformed chunk length.",
            ));
        }
        let chunk = &bytes[offset..offset + chunk_len_usize];
        match chunk_id {
            b"fmt " => {
                if chunk.len() < 16 {
                    return Err(PyValueError::new_err(
                        "Could not load WAV sound: malformed fmt chunk.",
                    ));
                }
                channels = Some(u16::from_le_bytes([chunk[2], chunk[3]]));
                sample_rate = Some(u32::from_le_bytes([chunk[4], chunk[5], chunk[6], chunk[7]]));
                bits_per_sample = Some(u16::from_le_bytes([chunk[14], chunk[15]]));
            }
            b"data" => {
                data_len = Some(chunk_len);
            }
            _ => {}
        }
        offset += chunk_len_usize + (chunk_len_usize % 2);
    }

    let Some(channels) = channels else {
        return Ok(None);
    };
    let Some(sample_rate) = sample_rate else {
        return Ok(None);
    };
    let Some(bits_per_sample) = bits_per_sample else {
        return Ok(None);
    };
    let Some(data_len) = data_len else {
        return Ok(None);
    };
    let bytes_per_sample = u32::from(bits_per_sample).div_ceil(8);
    let frame_bytes = u32::from(channels).saturating_mul(bytes_per_sample);
    if sample_rate == 0 || frame_bytes == 0 {
        return Ok(None);
    }
    Ok(Some(
        data_len as f64 / frame_bytes as f64 / sample_rate as f64,
    ))
}
