use sdl3::audio::AudioStreamOwner;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use super::open_sdl_audio_stream;

pub(crate) struct LivePlanWorker {
    stop: Arc<AtomicBool>,
    state: Arc<(Mutex<LivePlanWorkerState>, Condvar)>,
    thread: Option<JoinHandle<()>>,
}

#[derive(Debug, Default)]
struct LivePlanWorkerState {
    started: bool,
    finished: bool,
    error: Option<String>,
}

impl LivePlanWorker {
    pub(crate) fn start(
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

    pub(crate) fn stop(&mut self) -> Result<(), String> {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(thread) = self.thread.take() {
            thread
                .join()
                .map_err(|_| "Rust synth live playback worker panicked.".to_owned())?;
        }
        Ok(())
    }

    pub(crate) fn error_message(&mut self) -> Result<Option<String>, String> {
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
