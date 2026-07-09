use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sdl3::audio::{AudioFormat, AudioSpec, AudioStreamOwner};
use std::fs;
use std::thread;
use std::time::{Duration, Instant};

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

#[pyclass(name = "CanvasAudioPlayback", unsendable)]
pub(crate) struct CanvasAudioPlayback {
    _sdl: sdl3::Sdl,
    stream: Option<AudioStreamOwner>,
    duration: f64,
    started_at: Instant,
    stopped: bool,
}

#[pymethods]
impl CanvasAudioPlayback {
    #[getter]
    fn duration(&self) -> f64 {
        self.duration
    }

    fn stop(&mut self) -> PyResult<()> {
        self.stop_inner().map_err(PyRuntimeError::new_err)
    }

    fn close(&mut self) -> PyResult<()> {
        self.stop()
    }

    fn is_playing(&self) -> bool {
        !self.stopped && self.started_at.elapsed().as_secs_f64() < self.duration
    }

    #[pyo3(signature = (timeout=None))]
    fn wait_until_stop(&mut self, timeout: Option<f64>) -> PyResult<bool> {
        let started = Instant::now();
        loop {
            if !self.is_playing() {
                self.stop()?;
                return Ok(true);
            }
            if let Some(timeout) = timeout {
                if started.elapsed().as_secs_f64() >= timeout.max(0.0) {
                    return Ok(false);
                }
            }
            thread::sleep(Duration::from_millis(5));
        }
    }
}

impl CanvasAudioPlayback {
    fn stop_inner(&mut self) -> Result<(), String> {
        self.stopped = true;
        let Some(stream) = self.stream.take() else {
            return Ok(());
        };
        let pause_result = stream.pause();
        let clear_result = stream.clear();
        drop(stream);
        pause_result.map_err(|err| format!("Failed to pause SDL3 synth playback: {err}"))?;
        clear_result.map_err(|err| format!("Failed to clear SDL3 synth playback: {err}"))?;
        Ok(())
    }
}

impl Drop for CanvasAudioPlayback {
    fn drop(&mut self) {
        let _ = self.stop_inner();
    }
}

#[pyfunction]
pub(crate) fn synth_play_wav_bytes(payload: &Bound<'_, PyBytes>) -> PyResult<CanvasAudioPlayback> {
    start_wav_playback(payload.as_bytes())
}

#[pyfunction]
pub(crate) fn synth_play_serialized_plan(
    payload: &Bound<'_, PyBytes>,
    sample_rate: u32,
) -> PyResult<CanvasAudioPlayback> {
    let wav_payload =
        gummy_synth::render_serialized_plan_wav_bytes(payload.as_bytes(), sample_rate)?;
    start_wav_playback(&wav_payload)
}

fn start_wav_playback(payload: &[u8]) -> PyResult<CanvasAudioPlayback> {
    let wav = parse_pcm_s16_wav(payload)?;
    let sdl = sdl3::init().map_err(|err| {
        PyRuntimeError::new_err(format!(
            "Failed to initialize SDL3 synth audio playback: {err}"
        ))
    })?;
    let audio = sdl.audio().map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to initialize SDL3 audio subsystem: {err}"))
    })?;
    let spec = AudioSpec {
        freq: Some(wav.sample_rate as i32),
        channels: Some(i32::from(wav.channels)),
        format: Some(AudioFormat::s16_sys()),
    };
    let device = audio.open_playback_device(&spec).map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to open SDL3 synth playback device: {err}"))
    })?;
    let stream = device.open_device_stream(Some(&spec)).map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to open SDL3 synth playback stream: {err}"))
    })?;
    stream.put_data_i16(&wav.samples).map_err(|err| {
        PyRuntimeError::new_err(format!(
            "Failed to queue SDL3 synth playback samples: {err}"
        ))
    })?;
    stream.flush().map_err(|err| {
        PyRuntimeError::new_err(format!(
            "Failed to flush SDL3 synth playback samples: {err}"
        ))
    })?;
    stream.resume().map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to start SDL3 synth playback: {err}"))
    })?;
    Ok(CanvasAudioPlayback {
        _sdl: sdl,
        stream: Some(stream),
        duration: wav.duration,
        started_at: Instant::now(),
        stopped: false,
    })
}

struct PcmS16Wav {
    samples: Vec<i16>,
    sample_rate: u32,
    channels: u16,
    duration: f64,
}

fn parse_pcm_s16_wav(bytes: &[u8]) -> PyResult<PcmS16Wav> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err(PyValueError::new_err(
            "SDL3 synth playback requires PCM WAV bytes produced by the Rust synth renderer.",
        ));
    }

    let mut offset = 12usize;
    let mut audio_format: Option<u16> = None;
    let mut channels: Option<u16> = None;
    let mut sample_rate: Option<u32> = None;
    let mut bits_per_sample: Option<u16> = None;
    let mut data: Option<&[u8]> = None;

    while offset.checked_add(8).is_some_and(|end| end <= bytes.len()) {
        let chunk_id = &bytes[offset..offset + 4];
        let chunk_len = u32::from_le_bytes([
            bytes[offset + 4],
            bytes[offset + 5],
            bytes[offset + 6],
            bytes[offset + 7],
        ]) as usize;
        offset += 8;
        if offset
            .checked_add(chunk_len)
            .is_none_or(|end| end > bytes.len())
        {
            return Err(PyValueError::new_err(
                "Could not play synth WAV bytes: malformed chunk length.",
            ));
        }
        let chunk = &bytes[offset..offset + chunk_len];
        match chunk_id {
            b"fmt " => {
                if chunk.len() < 16 {
                    return Err(PyValueError::new_err(
                        "Could not play synth WAV bytes: malformed fmt chunk.",
                    ));
                }
                audio_format = Some(u16::from_le_bytes([chunk[0], chunk[1]]));
                channels = Some(u16::from_le_bytes([chunk[2], chunk[3]]));
                sample_rate = Some(u32::from_le_bytes([chunk[4], chunk[5], chunk[6], chunk[7]]));
                bits_per_sample = Some(u16::from_le_bytes([chunk[14], chunk[15]]));
            }
            b"data" => {
                data = Some(chunk);
            }
            _ => {}
        }
        offset += chunk_len + (chunk_len % 2);
    }

    let audio_format = audio_format.ok_or_else(|| {
        PyValueError::new_err("Could not play synth WAV bytes: missing fmt chunk.")
    })?;
    if audio_format != 1 {
        return Err(PyValueError::new_err(
            "SDL3 synth playback requires uncompressed PCM WAV bytes.",
        ));
    }
    let channels = channels.ok_or_else(|| {
        PyValueError::new_err("Could not play synth WAV bytes: missing channel count.")
    })?;
    if channels == 0 {
        return Err(PyValueError::new_err(
            "Could not play synth WAV bytes: channel count must be greater than zero.",
        ));
    }
    let sample_rate = sample_rate.ok_or_else(|| {
        PyValueError::new_err("Could not play synth WAV bytes: missing sample rate.")
    })?;
    if sample_rate == 0 {
        return Err(PyValueError::new_err(
            "Could not play synth WAV bytes: sample rate must be greater than zero.",
        ));
    }
    let bits_per_sample = bits_per_sample.ok_or_else(|| {
        PyValueError::new_err("Could not play synth WAV bytes: missing bit depth.")
    })?;
    if bits_per_sample != 16 {
        return Err(PyValueError::new_err(
            "SDL3 synth playback requires 16-bit PCM WAV bytes.",
        ));
    }
    let data = data.ok_or_else(|| {
        PyValueError::new_err("Could not play synth WAV bytes: missing data chunk.")
    })?;
    if data.len() % 2 != 0 {
        return Err(PyValueError::new_err(
            "Could not play synth WAV bytes: sample data length is not aligned to 16-bit samples.",
        ));
    }
    let samples: Vec<i16> = data
        .chunks_exact(2)
        .map(|chunk| i16::from_le_bytes([chunk[0], chunk[1]]))
        .collect();
    let duration = samples.len() as f64 / f64::from(channels) / sample_rate as f64;
    Ok(PcmS16Wav {
        samples,
        sample_rate,
        channels,
        duration,
    })
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
