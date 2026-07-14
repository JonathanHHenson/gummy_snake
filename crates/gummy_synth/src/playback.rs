use super::*;
use crate::stateful_block_renderer::StatefulBlockRenderer;
use crate::wav_sink::StereoPcmWavSink;
use std::io::{Cursor, Seek, Write};
use std::sync::atomic::{AtomicU64, Ordering};

/// Compile typed events and render them to a stereo WAV payload.
pub fn render_plan_events(
    parsed_events: Vec<EventPayload>,
    duration_seconds: f64,
    sample_rate: u32,
) -> SynthResult<Vec<u8>> {
    if duration_seconds < 0.0 {
        return Err(SynthError::new(
            "synth plan render duration cannot be negative.",
        ));
    }
    let program = CompiledSynthProgram::compile(parsed_events, duration_seconds, sample_rate)?;
    render_compiled_program_wav(&program)
}

/// Render an immutable Rust-owned program without reparsing or rescheduling it.
///
/// The returned WAV bytes are the only duration-sized allocation. Renderer
/// workspace, buses, processor state, and PCM conversion remain block-bounded.
pub fn render_compiled_program_wav(program: &CompiledSynthProgram) -> SynthResult<Vec<u8>> {
    let writer = render_compiled_program_wav_writer(program, Cursor::new(Vec::new()))?;
    Ok(writer.into_inner())
}

fn render_compiled_program_wav_writer<W: Write + Seek>(
    program: &CompiledSynthProgram,
    writer: W,
) -> SynthResult<W> {
    let mut renderer = StatefulBlockRenderer::new(program.clone(), BlockRenderConfig::default())?;
    let mut sink = StereoPcmWavSink::new(writer, program.sample_rate())
        .map_err(|error| SynthError::new(error.to_string()))?;
    renderer.render_to_sink(&mut sink)?;
    sink.into_finished_writer()
        .map_err(|error| SynthError::new(error.to_string()))
}

pub fn render_serialized_plan_wav_bytes(payload: &[u8], sample_rate: u32) -> SynthResult<Vec<u8>> {
    let program = CompiledSynthProgram::from_serialized_plan(payload, sample_rate)?;
    render_compiled_program_wav(&program)
}

pub fn render_serialized_plan_wav_file(
    payload: &[u8],
    sample_rate: u32,
    path: &Path,
) -> SynthResult<()> {
    let program = CompiledSynthProgram::from_serialized_plan(payload, sample_rate)?;
    render_compiled_program_wav_file(&program, path)
}

/// Stream a compiled program to a same-directory temporary destination and
/// atomically replace the requested WAV only after the sink finalizes cleanly.
pub fn render_compiled_program_wav_file(
    program: &CompiledSynthProgram,
    path: &Path,
) -> SynthResult<()> {
    // Construct first so unsupported routes fail without creating any output.
    let renderer = StatefulBlockRenderer::new(program.clone(), BlockRenderConfig::default())?;
    let temporary_path = atomic_output_path(path)?;
    let result = (|| {
        let file = fs::File::create(&temporary_path).map_err(|error| {
            SynthError::new(format!(
                "could not create temporary synth WAV {}: {error}",
                temporary_path.display()
            ))
        })?;
        let mut renderer = renderer;
        let mut sink = StereoPcmWavSink::new(file, program.sample_rate())
            .map_err(|error| SynthError::new(error.to_string()))?;
        renderer.render_to_sink(&mut sink)?;
        let file = sink
            .into_finished_writer()
            .map_err(|error| SynthError::new(error.to_string()))?;
        file.sync_all().map_err(|error| {
            SynthError::new(format!(
                "could not synchronize temporary synth WAV {}: {error}",
                temporary_path.display()
            ))
        })?;
        fs::rename(&temporary_path, path).map_err(|error| {
            SynthError::new(format!(
                "could not atomically replace rendered synth WAV {}: {error}",
                path.display()
            ))
        })
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary_path);
    }
    result
}

fn atomic_output_path(path: &Path) -> SynthResult<PathBuf> {
    static NEXT_OUTPUT_ID: AtomicU64 = AtomicU64::new(1);
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| {
            SynthError::new(format!(
                "rendered synth WAV destination {} has no valid file name.",
                path.display()
            ))
        })?;
    let id = NEXT_OUTPUT_ID.fetch_add(1, Ordering::Relaxed);
    Ok(parent.join(format!(
        ".{file_name}.gummysnake-{}-{id}.tmp",
        std::process::id()
    )))
}
