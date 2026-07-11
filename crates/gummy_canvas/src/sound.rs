mod live;
mod wav;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sdl3::audio::{AudioFormat, AudioSpec, AudioStreamOwner};
use std::fs;
use std::thread;
use std::time::{Duration, Instant};

use live::LivePlanWorker;
use wav::{parse_pcm_s16_wav, wav_duration_seconds};

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
    _sdl: Option<sdl3::Sdl>,
    stream: Option<PlaybackStream>,
    duration: f64,
    started_at: Instant,
    stopped: bool,
}

pub(crate) enum PlaybackStream {
    Queued(AudioStreamOwner),
    LiveWorker(LivePlanWorker),
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

    fn is_playing(&mut self) -> PyResult<bool> {
        if let Some(error) = self
            .callback_error_message()
            .map_err(PyRuntimeError::new_err)?
        {
            return Err(PyRuntimeError::new_err(error));
        }
        Ok(!self.stopped && self.started_at.elapsed().as_secs_f64() < self.duration)
    }

    #[getter]
    fn error(&mut self) -> PyResult<Option<String>> {
        self.callback_error_message()
            .map_err(PyRuntimeError::new_err)
    }

    #[pyo3(signature = (timeout=None))]
    fn wait_until_stop(&mut self, timeout: Option<f64>) -> PyResult<bool> {
        let started = Instant::now();
        loop {
            if !self.is_playing()? {
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
        match stream {
            PlaybackStream::Queued(stream) => {
                let pause_result = stream.pause();
                let clear_result = stream.clear();
                pause_result
                    .map_err(|err| format!("Failed to pause SDL3 synth playback: {err}"))?;
                clear_result
                    .map_err(|err| format!("Failed to clear SDL3 synth playback: {err}"))?;
            }
            PlaybackStream::LiveWorker(mut worker) => {
                worker.stop()?;
            }
        }
        Ok(())
    }

    fn callback_error_message(&mut self) -> Result<Option<String>, String> {
        let Some(PlaybackStream::LiveWorker(worker)) = self.stream.as_mut() else {
            return Ok(None);
        };
        worker.error_message()
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
    start_serialized_plan_streaming_playback(payload.as_bytes(), sample_rate)
}

fn start_wav_playback(payload: &[u8]) -> PyResult<CanvasAudioPlayback> {
    let wav = parse_pcm_s16_wav(payload)?;
    let (sdl, stream) = open_sdl_audio_stream(wav.sample_rate, wav.channels)?;
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
        _sdl: Some(sdl),
        stream: Some(PlaybackStream::Queued(stream)),
        duration: wav.duration,
        started_at: Instant::now(),
        stopped: false,
    })
}

fn start_serialized_plan_streaming_playback(
    payload: &[u8],
    sample_rate: u32,
) -> PyResult<CanvasAudioPlayback> {
    if sample_rate == 0 {
        return Err(PyValueError::new_err(
            "synth live playback sample rate must be greater than zero.",
        ));
    }
    let plan = gummy_synth::SynthPlaybackPlan::from_serialized_plan(payload)
        .map_err(|error| PyValueError::new_err(error.message().to_owned()))?;
    let duration = plan.duration_seconds();
    if !duration.is_finite() || duration < 0.0 {
        return Err(PyValueError::new_err(
            "synth live playback duration must be finite and non-negative.",
        ));
    }
    let worker = LivePlanWorker::start(plan, sample_rate, duration)?;
    Ok(CanvasAudioPlayback {
        _sdl: None,
        stream: Some(PlaybackStream::LiveWorker(worker)),
        duration,
        started_at: Instant::now(),
        stopped: false,
    })
}

pub(super) fn open_sdl_audio_stream(
    sample_rate: u32,
    channels: u16,
) -> PyResult<(sdl3::Sdl, AudioStreamOwner)> {
    let sdl = sdl3::init().map_err(|err| {
        PyRuntimeError::new_err(format!(
            "Failed to initialize SDL3 synth audio playback: {err}"
        ))
    })?;
    let audio = sdl.audio().map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to initialize SDL3 audio subsystem: {err}"))
    })?;
    let spec = AudioSpec {
        freq: Some(sample_rate as i32),
        channels: Some(i32::from(channels)),
        format: Some(AudioFormat::s16_sys()),
    };
    let device = audio.open_playback_device(&spec).map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to open SDL3 synth playback device: {err}"))
    })?;
    let stream = device.open_device_stream(Some(&spec)).map_err(|err| {
        PyRuntimeError::new_err(format!("Failed to open SDL3 synth playback stream: {err}"))
    })?;
    Ok((sdl, stream))
}
