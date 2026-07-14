mod audio_manager;
mod wav;

use std::fs;
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use audio_manager::{start_playback, AudioAsset, PlaybackHandle, PlaybackSource, VoiceUpdate};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use wav::parse_pcm_s16_wav;

#[pyclass(name = "CanvasSound", unsendable)]
#[derive(Clone, Debug)]
pub(crate) struct CanvasSound {
    path: String,
    bytes: Arc<Vec<u8>>,
    asset: Arc<AudioAsset>,
}

#[pymethods]
impl CanvasSound {
    #[staticmethod]
    fn from_file(py: Python<'_>, path: String) -> PyResult<Self> {
        gummy_synth::record_gil_released_call(gummy_synth::GilReleasedOperation::Decode);
        let worker_path = path.clone();
        let (bytes, asset) = py.allow_threads(move || {
            let bytes = fs::read(&worker_path).map_err(|error| {
                PyValueError::new_err(format!("Could not load sound {worker_path}: {error}"))
            })?;
            let wav = parse_pcm_s16_wav(&bytes).map_err(|error| {
                PyValueError::new_err(format!(
                    "Could not load sound {worker_path}: {error}. Native Sound playback supports mono or stereo 16-bit PCM WAV assets."
                ))
            })?;
            Ok::<_, PyErr>((bytes, Arc::new(wav.into_audio_asset())))
        })?;
        Ok(Self {
            path,
            bytes: Arc::new(bytes),
            asset,
        })
    }

    #[staticmethod]
    fn from_bytes(py: Python<'_>, path: String, payload: &Bound<'_, PyBytes>) -> PyResult<Self> {
        let bytes = payload.as_bytes().to_vec();
        gummy_synth::record_gil_released_call(gummy_synth::GilReleasedOperation::Decode);
        let (bytes, asset) = py.allow_threads(move || {
            let wav = parse_pcm_s16_wav(&bytes).map_err(|error| {
                PyValueError::new_err(format!(
                    "Could not create native Sound asset: {error}. Expected mono or stereo 16-bit PCM WAV bytes."
                ))
            })?;
            Ok::<_, PyErr>((bytes, Arc::new(wav.into_audio_asset())))
        })?;
        Ok(Self {
            path,
            bytes: Arc::new(bytes),
            asset,
        })
    }

    #[getter]
    fn path(&self) -> &str {
        &self.path
    }

    #[getter]
    fn duration(&self) -> f64 {
        self.asset.duration
    }

    #[getter]
    fn byte_len(&self) -> usize {
        self.bytes.len()
    }

    #[getter]
    fn sample_rate(&self) -> u32 {
        self.asset.sample_rate
    }

    #[getter]
    fn frame_count(&self) -> usize {
        self.asset.frame_count()
    }

    fn to_bytes<'py>(&self, py: Python<'py>) -> Bound<'py, PyBytes> {
        PyBytes::new_bound(py, &self.bytes)
    }

    #[pyo3(signature = (volume=1.0, rate=1.0, pan=0.0, looping=false, position=0.0))]
    fn play(
        &self,
        volume: f64,
        rate: f64,
        pan: f64,
        looping: bool,
        position: f64,
    ) -> PyResult<CanvasAudioPlayback> {
        CanvasAudioPlayback::start(PlaybackSource::Asset {
            asset: Arc::clone(&self.asset),
            volume,
            rate,
            pan,
            looping,
            position_seconds: position,
        })
    }
}

impl CanvasSound {
    pub(crate) fn from_encoded_bytes(path: String, bytes: Vec<u8>) -> PyResult<Self> {
        let wav = parse_pcm_s16_wav(&bytes).map_err(|error| {
            PyValueError::new_err(format!(
                "Could not create rendered native Sound asset: {error}. Expected 16-bit PCM WAV output."
            ))
        })?;
        Ok(Self {
            path,
            bytes: Arc::new(bytes),
            asset: Arc::new(wav.into_audio_asset()),
        })
    }
}

#[pyclass(name = "CanvasAudioPlayback", unsendable)]
pub(crate) struct CanvasAudioPlayback {
    handle: Option<PlaybackHandle>,
    last_ended_generation: u64,
}

#[pymethods]
impl CanvasAudioPlayback {
    #[getter]
    fn duration(&self) -> PyResult<f64> {
        self.with_snapshot(|state| state.duration)
    }

    fn play(&self) -> PyResult<()> {
        self.command(VoiceUpdate::Resume)
    }

    fn pause(&self) -> PyResult<()> {
        self.command(VoiceUpdate::Pause)
    }

    fn stop(&self) -> PyResult<()> {
        self.command(VoiceUpdate::Stop)
    }

    fn close(&mut self) -> PyResult<()> {
        let Some(handle) = self.handle.take() else {
            return Ok(());
        };
        handle.command(VoiceUpdate::Close).map_err(playback_error)
    }

    #[pyo3(signature = (value=None))]
    fn looping(&self, value: Option<bool>) -> PyResult<bool> {
        if let Some(value) = value {
            self.command(VoiceUpdate::SetLooping(value))?;
        }
        self.with_snapshot(|state| state.looping)
    }

    fn set_volume(&self, value: f64) -> PyResult<()> {
        self.command(VoiceUpdate::SetVolume(value))
    }

    fn set_rate(&self, value: f64) -> PyResult<()> {
        self.command(VoiceUpdate::SetRate(value))
    }

    fn set_pan(&self, value: f64) -> PyResult<()> {
        self.command(VoiceUpdate::SetPan(value))
    }

    fn seek(&self, seconds: f64) -> PyResult<()> {
        self.command(VoiceUpdate::Seek(seconds))
    }

    fn time(&self) -> PyResult<f64> {
        self.with_snapshot(|state| state.position)
    }

    fn is_playing(&self) -> PyResult<bool> {
        self.raise_error()?;
        self.with_snapshot(|state| state.playing)
    }

    fn is_paused(&self) -> PyResult<bool> {
        self.raise_error()?;
        self.with_snapshot(|state| state.paused)
    }

    #[getter]
    fn error(&self) -> PyResult<Option<String>> {
        self.with_snapshot(|state| state.error.clone())
    }

    fn take_ended(&mut self) -> PyResult<bool> {
        let generation = self.with_snapshot(|state| state.ended_generation)?;
        if generation == 0 || generation == self.last_ended_generation {
            return Ok(false);
        }
        self.last_ended_generation = generation;
        Ok(true)
    }

    fn diagnostics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let handle = self.handle.as_ref().ok_or_else(closed_playback_error)?;
        let state = handle.state.lock().map_err(|_| {
            PyRuntimeError::new_err("Native audio playback state lock was poisoned.")
        })?;
        let payload = PyDict::new_bound(py);
        payload.set_item("duration_seconds", state.duration)?;
        payload.set_item("position_seconds", state.position)?;
        payload.set_item("playing", state.playing)?;
        payload.set_item("paused", state.paused)?;
        payload.set_item("looping", state.looping)?;
        payload.set_item("blocks", state.blocks)?;
        payload.set_item("rendered_frames", state.rendered_frames)?;
        payload.set_item("ended_generation", state.ended_generation)?;
        payload.set_item("error", state.error.clone())?;
        Ok(payload)
    }

    #[pyo3(signature = (timeout=None))]
    fn wait_until_stop(&self, py: Python<'_>, timeout: Option<f64>) -> PyResult<bool> {
        let state = self
            .handle
            .as_ref()
            .ok_or_else(closed_playback_error)?
            .state
            .clone();
        let result = py.allow_threads(move || {
            let started = Instant::now();
            loop {
                let playing = state
                    .lock()
                    .map_err(|_| "Native audio playback state lock was poisoned.".to_owned())?
                    .playing;
                if !playing {
                    return Ok(true);
                }
                if timeout.is_some_and(|limit| started.elapsed().as_secs_f64() >= limit.max(0.0)) {
                    return Ok(false);
                }
                thread::sleep(Duration::from_millis(5));
            }
        });
        result.map_err(playback_error)
    }
}

impl CanvasAudioPlayback {
    fn start(source: PlaybackSource) -> PyResult<Self> {
        let handle = start_playback(source).map_err(playback_error)?;
        Ok(Self {
            handle: Some(handle),
            last_ended_generation: 0,
        })
    }

    fn command(&self, update: VoiceUpdate) -> PyResult<()> {
        self.handle
            .as_ref()
            .ok_or_else(closed_playback_error)?
            .command(update)
            .map_err(playback_error)
    }

    fn with_snapshot<T>(
        &self,
        get: impl FnOnce(&audio_manager::PlaybackSnapshot) -> T,
    ) -> PyResult<T> {
        let handle = self.handle.as_ref().ok_or_else(closed_playback_error)?;
        let state = handle.state.lock().map_err(|_| {
            PyRuntimeError::new_err("Native audio playback state lock was poisoned.")
        })?;
        Ok(get(&state))
    }

    fn raise_error(&self) -> PyResult<()> {
        if let Some(error) = self.with_snapshot(|state| state.error.clone())? {
            return Err(playback_error(error));
        }
        Ok(())
    }
}

impl Drop for CanvasAudioPlayback {
    fn drop(&mut self) {
        if let Some(handle) = self.handle.take() {
            let _ = handle.command(VoiceUpdate::Close);
        }
    }
}

#[pyfunction]
pub(crate) fn synth_play_wav_bytes(
    py: Python<'_>,
    payload: &Bound<'_, PyBytes>,
) -> PyResult<CanvasAudioPlayback> {
    let payload = payload.as_bytes().to_vec();
    gummy_synth::record_gil_released_call(gummy_synth::GilReleasedOperation::Decode);
    let asset = py.allow_threads(move || {
        parse_pcm_s16_wav(&payload)
            .map(|wav| Arc::new(wav.into_audio_asset()))
            .map_err(|error| error.to_string())
    });
    CanvasAudioPlayback::start(PlaybackSource::Asset {
        asset: asset.map_err(playback_error)?,
        volume: 1.0,
        rate: 1.0,
        pan: 0.0,
        looping: false,
        position_seconds: 0.0,
    })
}

#[pyfunction]
#[pyo3(signature = (program, looping=false))]
pub(crate) fn synth_play_compiled_program(
    program: PyRef<'_, crate::bindings::synth::CanvasSynthProgram>,
    looping: bool,
) -> PyResult<CanvasAudioPlayback> {
    CanvasAudioPlayback::start(PlaybackSource::Synth {
        program: program.cloned_program(),
        looping,
    })
}

#[pyfunction]
#[pyo3(signature = (payload, sample_rate, looping=false))]
pub(crate) fn synth_play_serialized_plan(
    py: Python<'_>,
    payload: &Bound<'_, PyBytes>,
    sample_rate: u32,
    looping: bool,
) -> PyResult<CanvasAudioPlayback> {
    if sample_rate == 0 {
        return Err(PyValueError::new_err(
            "synth live playback sample rate must be greater than zero.",
        ));
    }
    let payload = payload.as_bytes().to_vec();
    gummy_synth::record_gil_released_call(gummy_synth::GilReleasedOperation::Compile);
    let program = py
        .allow_threads(move || {
            gummy_synth::CompiledSynthProgram::from_serialized_plan(&payload, sample_rate)
        })
        .map_err(|error| PyValueError::new_err(error.message().to_owned()))?;
    CanvasAudioPlayback::start(PlaybackSource::Synth { program, looping })
}

pub(crate) fn audio_diagnostics() -> audio_manager::AudioManagerDiagnostics {
    audio_manager::diagnostics()
}

pub(crate) fn reset_audio_diagnostics() {
    audio_manager::reset_diagnostics();
}

fn playback_error(error: String) -> PyErr {
    PyRuntimeError::new_err(error)
}

fn closed_playback_error() -> PyErr {
    PyRuntimeError::new_err("This native audio playback handle is closed.")
}
