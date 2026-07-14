use sdl3::audio::AudioStreamOwner;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use gummy_synth::{
    BlockRenderConfig, BlockRenderStep, CompiledSynthProgram, PcmSink, SinkWrite,
    StatefulBlockRenderer, SynthError, SynthResult,
};
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
    pub(crate) fn start(program: CompiledSynthProgram) -> PyResult<Self> {
        let stop = Arc::new(AtomicBool::new(false));
        let state = Arc::new((Mutex::new(LivePlanWorkerState::default()), Condvar::new()));
        let worker_stop = Arc::clone(&stop);
        let worker_state = Arc::clone(&state);
        let thread = thread::spawn(move || {
            run_live_plan_worker(program, worker_stop, worker_state);
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

struct SdlQueueSink<'a> {
    stream: &'a AudioStreamOwner,
}

impl PcmSink for SdlQueueSink<'_> {
    fn write_interleaved_i16(&mut self, samples: &[i16]) -> SynthResult<SinkWrite> {
        if !samples.len().is_multiple_of(2) {
            return Err(SynthError::new(
                "SDL synth queue received an incomplete stereo PCM frame.",
            ));
        }
        self.stream.put_data_i16(samples).map_err(|error| {
            SynthError::new(format!(
                "Failed to queue SDL3 synth playback samples: {error}"
            ))
        })?;
        Ok(SinkWrite::Accepted)
    }

    fn finish(&mut self) -> SynthResult<()> {
        self.stream.flush().map_err(|error| {
            SynthError::new(format!(
                "Failed to flush SDL3 synth playback stream: {error}"
            ))
        })
    }
}

fn run_live_plan_worker(
    program: CompiledSynthProgram,
    stop: Arc<AtomicBool>,
    state: Arc<(Mutex<LivePlanWorkerState>, Condvar)>,
) {
    let result = run_live_plan_worker_inner(program, &stop, &state);
    if let Err(error) = result {
        set_live_worker_error(&state, error);
    }
    set_live_worker_finished(&state);
}

fn run_live_plan_worker_inner(
    program: CompiledSynthProgram,
    stop: &AtomicBool,
    state: &Arc<(Mutex<LivePlanWorkerState>, Condvar)>,
) -> Result<(), String> {
    let sample_rate = program.sample_rate();
    let (_sdl, stream) = open_sdl_audio_stream(sample_rate, 2)
        .map_err(|err| format!("Failed to open SDL3 synth live playback stream: {err}"))?;
    let mut renderer = StatefulBlockRenderer::new(program, BlockRenderConfig::default())
        .map_err(|error| format!("Rust synth live playback compile failed: {error}"))?;
    let mut sink = SdlQueueSink { stream: &stream };
    let mut finished = render_until_queue_target(
        &mut renderer,
        &mut sink,
        &stream,
        stop,
        live_stream_initial_ahead_frames(sample_rate),
    )?;
    if stop.load(Ordering::SeqCst) {
        return stop_stream(&stream);
    }
    stream
        .resume()
        .map_err(|err| format!("Failed to start SDL3 synth live playback: {err}"))?;
    set_live_worker_started(state);

    while !stop.load(Ordering::SeqCst) && !finished {
        let queued_frames = queued_stereo_frames(&stream)?;
        if queued_frames <= live_stream_low_water_frames(sample_rate) {
            finished = render_until_queue_target(
                &mut renderer,
                &mut sink,
                &stream,
                stop,
                live_stream_high_water_frames(sample_rate),
            )?;
        } else {
            thread::sleep(Duration::from_millis(2));
        }
    }

    if stop.load(Ordering::SeqCst) {
        return stop_stream(&stream);
    }
    while !stop.load(Ordering::SeqCst) && queued_stereo_frames(&stream)? > 0 {
        thread::sleep(Duration::from_millis(5));
    }
    if stop.load(Ordering::SeqCst) {
        stop_stream(&stream)?;
    }
    Ok(())
}

fn render_until_queue_target(
    renderer: &mut StatefulBlockRenderer,
    sink: &mut SdlQueueSink<'_>,
    stream: &AudioStreamOwner,
    stop: &AtomicBool,
    target_frames: u64,
) -> Result<bool, String> {
    while !stop.load(Ordering::SeqCst) && queued_stereo_frames(stream)? < target_frames {
        match renderer
            .step(sink)
            .map_err(|error| format!("Rust synth live block render failed: {error}"))?
        {
            BlockRenderStep::Produced { .. } => {}
            BlockRenderStep::Finished => return Ok(true),
        }
    }
    Ok(false)
}

fn queued_stereo_frames(stream: &AudioStreamOwner) -> Result<u64, String> {
    let queued_bytes = stream
        .queued_bytes()
        .map_err(|err| format!("Failed to query SDL3 synth live playback queue: {err}"))?;
    let queued_bytes = u64::try_from(queued_bytes.max(0))
        .map_err(|_| "SDL3 synth live playback queue size was invalid.".to_owned())?;
    Ok(queued_bytes / (std::mem::size_of::<i16>() as u64 * 2))
}

fn stop_stream(stream: &AudioStreamOwner) -> Result<(), String> {
    let pause_result = stream.pause();
    let clear_result = stream.clear();
    pause_result.map_err(|err| format!("Failed to pause SDL3 synth live playback: {err}"))?;
    clear_result.map_err(|err| format!("Failed to clear SDL3 synth live playback: {err}"))?;
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

fn live_stream_initial_ahead_frames(sample_rate: u32) -> u64 {
    (0.5 * sample_rate as f64).ceil().max(1.0) as u64
}

fn live_stream_low_water_frames(sample_rate: u32) -> u64 {
    (0.75 * sample_rate as f64).ceil().max(1.0) as u64
}

fn live_stream_high_water_frames(sample_rate: u32) -> u64 {
    (1.5 * sample_rate as f64).ceil().max(1.0) as u64
}
