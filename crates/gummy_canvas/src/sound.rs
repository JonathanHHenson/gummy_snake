use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sdl3::audio::{AudioFormat, AudioSpec, AudioStreamOwner};
use std::fs;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
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

pub(crate) struct LivePlanWorker {
    stop: Arc<AtomicBool>,
    state: Arc<(Mutex<LivePlanWorkerState>, Condvar)>,
    thread: Option<JoinHandle<()>>,
}

#[derive(Debug, Default)]
pub(crate) struct LivePlanWorkerState {
    started: bool,
    finished: bool,
    error: Option<String>,
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
    let plan = gummy_synth::SynthPlaybackPlan::from_serialized_plan(payload)?;
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

fn open_sdl_audio_stream(
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

impl LivePlanWorker {
    fn start(
        plan: gummy_synth::SynthPlaybackPlan,
        sample_rate: u32,
        duration: f64,
    ) -> PyResult<Self> {
        let stop = Arc::new(AtomicBool::new(false));
        let state = Arc::new((Mutex::new(LivePlanWorkerState::default()), Condvar::new()));
        let worker_stop = Arc::clone(&stop);
        let worker_state = Arc::clone(&state);
        let thread = thread::spawn(move || {
            run_live_plan_worker(plan, sample_rate, duration, worker_stop, worker_state);
        });

        {
            let (lock, cvar) = &*state;
            let mut guard = lock.lock().map_err(|_| {
                PyRuntimeError::new_err("Rust synth live playback state lock was poisoned.")
            })?;
            while !guard.started && guard.error.is_none() {
                guard = cvar.wait(guard).map_err(|_| {
                    PyRuntimeError::new_err("Rust synth live playback state lock was poisoned.")
                })?;
            }
            if let Some(error) = guard.error.clone() {
                drop(guard);
                stop.store(true, Ordering::SeqCst);
                thread.join().map_err(|_| {
                    PyRuntimeError::new_err(
                        "Rust synth live playback worker panicked after startup failure.",
                    )
                })?;
                return Err(PyRuntimeError::new_err(error));
            }
        }

        Ok(Self {
            stop,
            state,
            thread: Some(thread),
        })
    }

    fn stop(&mut self) -> Result<(), String> {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(thread) = self.thread.take() {
            thread
                .join()
                .map_err(|_| "Rust synth live playback worker panicked.".to_owned())?;
        }
        Ok(())
    }

    fn error_message(&mut self) -> Result<Option<String>, String> {
        let (lock, _) = &*self.state;
        let guard = lock
            .lock()
            .map_err(|_| "Rust synth live playback state lock was poisoned.".to_owned())?;
        Ok(guard.error.clone())
    }
}

impl Drop for LivePlanWorker {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

fn run_live_plan_worker(
    plan: gummy_synth::SynthPlaybackPlan,
    sample_rate: u32,
    duration: f64,
    stop: Arc<AtomicBool>,
    state: Arc<(Mutex<LivePlanWorkerState>, Condvar)>,
) {
    let result = run_live_plan_worker_inner(plan, sample_rate, duration, &stop, &state);
    if let Err(error) = result {
        set_live_worker_error(&state, error);
    }
    set_live_worker_finished(&state);
}

fn run_live_plan_worker_inner(
    plan: gummy_synth::SynthPlaybackPlan,
    sample_rate: u32,
    duration: f64,
    stop: &AtomicBool,
    state: &Arc<(Mutex<LivePlanWorkerState>, Condvar)>,
) -> Result<(), String> {
    let (_sdl, stream) = open_sdl_audio_stream(sample_rate, 2)
        .map_err(|err| format!("Failed to open SDL3 synth live playback stream: {err}"))?;
    let duration_frames = (duration * sample_rate as f64).ceil().max(0.0) as u64;
    let mut position_frames = 0_u64;

    queue_live_plan_until_ahead(
        &plan,
        &stream,
        sample_rate,
        duration_frames,
        &mut position_frames,
        live_stream_initial_ahead_frames(sample_rate),
    )?;
    stream
        .resume()
        .map_err(|err| format!("Failed to start SDL3 synth live playback: {err}"))?;
    set_live_worker_started(state);

    while !stop.load(Ordering::SeqCst) && position_frames < duration_frames {
        queue_live_plan_until_ahead(
            &plan,
            &stream,
            sample_rate,
            duration_frames,
            &mut position_frames,
            live_stream_queue_ahead_frames(sample_rate),
        )?;
        thread::sleep(Duration::from_millis(2));
    }

    if stop.load(Ordering::SeqCst) {
        let pause_result = stream.pause();
        let clear_result = stream.clear();
        pause_result.map_err(|err| format!("Failed to pause SDL3 synth live playback: {err}"))?;
        clear_result.map_err(|err| format!("Failed to clear SDL3 synth live playback: {err}"))?;
        return Ok(());
    }

    stream
        .flush()
        .map_err(|err| format!("Failed to flush SDL3 synth live playback stream: {err}"))?;
    while !stop.load(Ordering::SeqCst) {
        let queued = stream
            .queued_bytes()
            .map_err(|err| format!("Failed to query SDL3 synth live playback queue: {err}"))?;
        if queued <= 0 {
            break;
        }
        thread::sleep(Duration::from_millis(5));
    }
    Ok(())
}

fn queue_live_plan_until_ahead(
    plan: &gummy_synth::SynthPlaybackPlan,
    stream: &AudioStreamOwner,
    sample_rate: u32,
    duration_frames: u64,
    position_frames: &mut u64,
    target_queued_frames: u64,
) -> Result<(), String> {
    while *position_frames < duration_frames {
        let queued_bytes = stream
            .queued_bytes()
            .map_err(|err| format!("Failed to query SDL3 synth live playback queue: {err}"))?;
        let queued_samples = usize::try_from(queued_bytes.max(0))
            .map_err(|_| "SDL3 synth live playback queue size was invalid.".to_owned())?
            / std::mem::size_of::<i16>();
        let queued_frames = (queued_samples / 2) as u64;
        if queued_frames >= target_queued_frames {
            break;
        }
        queue_live_plan_window(plan, stream, sample_rate, duration_frames, position_frames)?;
    }
    Ok(())
}

fn queue_live_plan_window(
    plan: &gummy_synth::SynthPlaybackPlan,
    stream: &AudioStreamOwner,
    sample_rate: u32,
    duration_frames: u64,
    position_frames: &mut u64,
) -> Result<(), String> {
    let remaining_frames = duration_frames.saturating_sub(*position_frames);
    if remaining_frames == 0 {
        return Ok(());
    }
    let chunk_frames = live_stream_chunk_frames(sample_rate).min(remaining_frames);
    let start_seconds = *position_frames as f64 / sample_rate as f64;
    let chunk_seconds = chunk_frames as f64 / sample_rate as f64;
    let mut samples = plan
        .render_window_i16(start_seconds, chunk_seconds, sample_rate)
        .map_err(|err| format!("Rust synth live playback window render failed: {err}"))?;
    let max_samples = (remaining_frames as usize).saturating_mul(2);
    if samples.len() > max_samples {
        samples.truncate(max_samples);
    }
    if samples.is_empty() {
        return Err(format!(
            "Rust synth live playback rendered no samples for the window starting at {start_seconds:.6}s before the planned end."
        ));
    }
    if samples.len() % 2 != 0 {
        return Err(format!(
            "Rust synth live playback rendered {} samples, which is not aligned to stereo frames.",
            samples.len()
        ));
    }
    stream
        .put_data_i16(&samples)
        .map_err(|err| format!("Failed to queue SDL3 synth live playback samples: {err}"))?;
    *position_frames = position_frames
        .saturating_add((samples.len() / 2) as u64)
        .min(duration_frames);
    Ok(())
}

fn set_live_worker_started(state: &Arc<(Mutex<LivePlanWorkerState>, Condvar)>) {
    let (lock, cvar) = &**state;
    if let Ok(mut guard) = lock.lock() {
        guard.started = true;
        cvar.notify_all();
    }
}

fn set_live_worker_error(state: &Arc<(Mutex<LivePlanWorkerState>, Condvar)>, error: String) {
    let (lock, cvar) = &**state;
    if let Ok(mut guard) = lock.lock() {
        if guard.error.is_none() {
            guard.error = Some(error);
        }
        cvar.notify_all();
    }
}

fn set_live_worker_finished(state: &Arc<(Mutex<LivePlanWorkerState>, Condvar)>) {
    let (lock, cvar) = &**state;
    if let Ok(mut guard) = lock.lock() {
        guard.finished = true;
        cvar.notify_all();
    }
}

fn live_stream_chunk_frames(sample_rate: u32) -> u64 {
    (live_stream_chunk_seconds() * sample_rate as f64)
        .ceil()
        .max(1.0) as u64
}

fn live_stream_initial_ahead_frames(sample_rate: u32) -> u64 {
    (0.75 * sample_rate as f64).ceil().max(1.0) as u64
}

fn live_stream_queue_ahead_frames(sample_rate: u32) -> u64 {
    (3.0 * sample_rate as f64).ceil().max(1.0) as u64
}

fn live_stream_chunk_seconds() -> f64 {
    0.5
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
