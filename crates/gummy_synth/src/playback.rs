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

pub(crate) fn render_plan_window_samples_result(
    plan: &SynthPlaybackPlan,
    start_seconds: f64,
    duration_seconds: f64,
    sample_rate: u32,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    if start_seconds < 0.0 || duration_seconds < 0.0 {
        return Err(SynthError::new(
            "synth live render window start and duration cannot be negative.",
        ));
    }
    validate_finite_non_negative(start_seconds, "synth live render window start")?;
    validate_finite_non_negative(duration_seconds, "synth live render window duration")?;
    validate_sample_rate(sample_rate)?;
    if start_seconds >= plan.duration_seconds || duration_seconds <= 0.0 {
        return Ok((Vec::new(), Vec::new()));
    }

    let window_start = start_seconds;
    let window_duration = duration_seconds.min(plan.duration_seconds - window_start);
    let window_samples = checked_frame_count(
        window_duration,
        sample_rate,
        "synth live render window duration",
        0,
    )?;
    if window_samples == 0 {
        return Ok((Vec::new(), Vec::new()));
    }

    let context_start = (window_start - live_render_context_seconds()).max(0.0);
    let context_end = window_start + window_duration;
    let context_samples = checked_frame_count(
        context_end - context_start,
        sample_rate,
        "synth live render context duration",
        1,
    )?;
    let mut root = FxBusNode::root(context_samples, context_start);
    let mut sorted_events: Vec<(usize, &EventPayload)> = plan.events.iter().enumerate().collect();
    sorted_events.sort_by(|(_, a), (_, b)| a.time_seconds.total_cmp(&b.time_seconds));

    for (event_index, event) in sorted_events {
        if event.time_seconds >= context_end {
            break;
        }
        let signal = plan
            .dry_event_signal(event_index, event, sample_rate)
            .map_err(|error| SynthError::new(format!("ValueError: {error}")))?;
        let event_len = signal.left.len().max(signal.right.len());
        if event_len == 0 {
            continue;
        }
        let event_end = event.time_seconds + event_len as f64 / sample_rate as f64;
        if event_end <= context_start {
            continue;
        }
        let skip = ((context_start - event.time_seconds) * sample_rate as f64)
            .round()
            .max(0.0) as usize;
        let skip_left = skip.min(signal.left.len());
        let skip_right = skip.min(signal.right.len());
        let start = ((event.time_seconds - context_start) * sample_rate as f64)
            .round()
            .max(0.0) as usize;
        root.mix_event(
            &event.fx_chain,
            event.time_seconds,
            event.order,
            start,
            &signal.left[skip_left..],
            &signal.right[skip_right..],
        )?;
    }

    let (left, right) = root.render(sample_rate)?;
    let offset = ((window_start - context_start) * sample_rate as f64)
        .round()
        .max(0.0) as usize;
    Ok(output_limit_window(
        &left,
        &right,
        offset,
        window_samples,
        sample_rate,
    ))
}

pub(crate) fn live_render_context_seconds() -> f64 {
    4.0
}

impl SynthPlaybackPlan {
    pub fn from_serialized_plan(payload: &[u8]) -> SynthResult<Self> {
        let (events, duration_seconds) = parse_serialized_plan(payload)
            .map_err(|error| SynthError::new(format!("ValueError: {error}")))?;
        Ok(Self {
            events,
            duration_seconds,
            dry_event_cache: Mutex::new(HashMap::new()),
        })
    }

    pub fn from_compiled_program(program: &CompiledSynthProgram) -> Self {
        Self {
            events: program.events().to_vec(),
            duration_seconds: program.duration_seconds(),
            dry_event_cache: Mutex::new(HashMap::new()),
        }
    }

    pub fn duration_seconds(&self) -> f64 {
        self.duration_seconds
    }

    pub fn render_window_i16(
        &self,
        start_seconds: f64,
        duration_seconds: f64,
        sample_rate: u32,
    ) -> SynthResult<Vec<i16>> {
        let (left, right) =
            render_plan_window_samples_result(self, start_seconds, duration_seconds, sample_rate)?;
        Ok(samples_to_interleaved_i16(
            &left,
            &right,
            left.len().min(right.len()),
        ))
    }

    fn dry_event_signal(
        &self,
        event_index: usize,
        event: &EventPayload,
        sample_rate: u32,
    ) -> SynthResult<Arc<StereoEventSignal>> {
        let key = (event_index, sample_rate);
        if let Some(cached) = self
            .dry_event_cache
            .lock()
            .map_err(|_| SynthError::new("synth dry-event cache lock was poisoned."))?
            .get(&key)
            .cloned()
        {
            return Ok(cached);
        }

        let (left, right) = render_dry_event(event, sample_rate)?;
        let rendered = Arc::new(StereoEventSignal { left, right });
        let mut cache = self
            .dry_event_cache
            .lock()
            .map_err(|_| SynthError::new("synth dry-event cache lock was poisoned."))?;
        Ok(cache
            .entry(key)
            .or_insert_with(|| Arc::clone(&rendered))
            .clone())
    }
}

impl FxBusNode {
    fn root(total_samples: usize, time_origin_seconds: f64) -> Self {
        Self {
            fx: None,
            input_left: vec![0.0; total_samples],
            input_right: vec![0.0; total_samples],
            option_snapshots: Vec::new(),
            children: Vec::new(),
            time_origin_seconds,
        }
    }

    fn for_fx(fx: &FxPayload, total_samples: usize, time_origin_seconds: f64) -> Self {
        Self {
            fx: Some(fx.clone()),
            input_left: vec![0.0; total_samples],
            input_right: vec![0.0; total_samples],
            option_snapshots: Vec::new(),
            children: Vec::new(),
            time_origin_seconds,
        }
    }

    fn mix_event(
        &mut self,
        fx_chain: &[FxPayload],
        event_time_seconds: f64,
        event_order: u64,
        start_sample: usize,
        left: &[f64],
        right: &[f64],
    ) -> SynthResult<()> {
        if let Some((fx, remaining_chain)) = fx_chain.split_first() {
            let child = self.child_mut(fx);
            child.option_snapshots.push(FxOptionSnapshot {
                time_seconds: event_time_seconds,
                order: event_order,
                opts: fx.opts.clone(),
            });
            child.mix_event(
                remaining_chain,
                event_time_seconds,
                event_order,
                start_sample,
                left,
                right,
            )?;
            return Ok(());
        }
        mix_signal_into(
            &mut self.input_left,
            &mut self.input_right,
            start_sample,
            left,
            right,
        )
    }

    fn child_mut(&mut self, fx: &FxPayload) -> &mut FxBusNode {
        if let Some(index) = self.children.iter().position(|child| child.matches_fx(fx)) {
            return &mut self.children[index];
        }
        let total_samples = self.input_left.len().max(self.input_right.len()).max(1);
        self.children.push(FxBusNode::for_fx(
            fx,
            total_samples,
            self.time_origin_seconds,
        ));
        self.children
            .last_mut()
            .expect("FX bus child was just appended")
    }

    fn matches_fx(&self, fx: &FxPayload) -> bool {
        self.fx
            .as_ref()
            .is_some_and(|current| current.id == fx.id && current.name == fx.name)
    }

    fn render(mut self, sample_rate: u32) -> SynthResult<(Vec<f64>, Vec<f64>)> {
        for child in self.children {
            let (child_left, child_right) = child.render(sample_rate)?;
            mix_signal_into(
                &mut self.input_left,
                &mut self.input_right,
                0,
                &child_left,
                &child_right,
            )?;
        }
        let Some(fx) = self.fx else {
            return Ok((self.input_left, self.input_right));
        };
        render_fx_bus_signal(
            &fx,
            &self.option_snapshots,
            self.input_left,
            self.input_right,
            sample_rate,
            self.time_origin_seconds,
        )
    }
}

pub(crate) fn render_fx_bus_signal(
    fx: &FxPayload,
    snapshots: &[FxOptionSnapshot],
    input_left: Vec<f64>,
    input_right: Vec<f64>,
    sample_rate: u32,
    time_origin_seconds: f64,
) -> SynthResult<(Vec<f64>, Vec<f64>)> {
    let segments = fx_option_segments(
        fx,
        snapshots,
        input_left.len().max(input_right.len()),
        sample_rate,
        time_origin_seconds,
    );
    if segments.len() == 1 && segments[0].0 == 0 {
        return apply_fx(
            &fx.name,
            input_left,
            input_right,
            &segments[0].2,
            sample_rate,
            time_origin_seconds,
        );
    }

    let mut output_left = vec![0.0; input_left.len().max(input_right.len())];
    let mut output_right = vec![0.0; input_left.len().max(input_right.len())];
    for (start, end, opts) in segments {
        if start >= end {
            continue;
        }
        let segment_left = slice_with_zeros(&input_left, start, end);
        let segment_right = slice_with_zeros(&input_right, start, end);
        if is_silent_pair(&segment_left, &segment_right) {
            continue;
        }
        let start_time_seconds = time_origin_seconds + start as f64 / sample_rate as f64;
        let (fx_left, fx_right) = apply_fx(
            &fx.name,
            segment_left,
            segment_right,
            &opts,
            sample_rate,
            start_time_seconds,
        )?;
        mix_signal_into(
            &mut output_left,
            &mut output_right,
            start,
            &fx_left,
            &fx_right,
        )?;
    }
    Ok((output_left, output_right))
}

pub(crate) fn fx_option_segments(
    fx: &FxPayload,
    snapshots: &[FxOptionSnapshot],
    input_len: usize,
    sample_rate: u32,
    time_origin_seconds: f64,
) -> Vec<(usize, usize, OptMap)> {
    let bounded_len = input_len.max(1);
    let mut sorted = snapshots.to_vec();
    sorted.sort_by(|a, b| {
        a.time_seconds
            .total_cmp(&b.time_seconds)
            .then_with(|| a.order.cmp(&b.order))
    });
    let mut starts = vec![(0usize, fx.opts.clone())];
    for snapshot in sorted {
        let start = ((snapshot.time_seconds - time_origin_seconds) * sample_rate as f64)
            .round()
            .max(0.0) as usize;
        let start = start.min(bounded_len);
        if starts.last().is_some_and(|(last_start, last_opts)| {
            *last_start == start && *last_opts == snapshot.opts
        }) {
            continue;
        }
        if starts
            .last()
            .is_some_and(|(_last_start, last_opts)| *last_opts == snapshot.opts)
        {
            continue;
        }
        starts.push((start, snapshot.opts));
    }
    starts.sort_by(|a, b| a.0.cmp(&b.0));
    let mut segments = Vec::with_capacity(starts.len());
    for (index, (start, opts)) in starts.iter().enumerate() {
        let end = starts
            .get(index + 1)
            .map(|(next_start, _)| *next_start)
            .unwrap_or(bounded_len);
        if *start < end {
            segments.push((*start, end, opts.clone()));
        }
    }
    if segments.is_empty() {
        segments.push((0, bounded_len, fx.opts.clone()));
    }
    segments
}

pub(crate) fn mix_signal_into(
    target_left: &mut Vec<f64>,
    target_right: &mut Vec<f64>,
    start: usize,
    left: &[f64],
    right: &[f64],
) -> SynthResult<()> {
    let required = start
        .checked_add(left.len().max(right.len()))
        .filter(|value| *value <= MAX_OUTPUT_FRAMES)
        .ok_or_else(|| {
            SynthError::new(format!(
                "synth mixed output exceeds the budget of {MAX_OUTPUT_FRAMES} frames."
            ))
        })?;
    if target_left.len() < required {
        target_left.resize(required, 0.0);
    }
    if target_right.len() < required {
        target_right.resize(required, 0.0);
    }
    for index in 0..required.saturating_sub(start) {
        target_left[start + index] += left.get(index).copied().unwrap_or(0.0);
        target_right[start + index] += right.get(index).copied().unwrap_or(0.0);
    }
    Ok(())
}

pub(crate) fn slice_with_zeros(samples: &[f64], start: usize, end: usize) -> Vec<f64> {
    (start..end)
        .map(|index| samples.get(index).copied().unwrap_or(0.0))
        .collect()
}

pub(crate) fn is_silent_pair(left: &[f64], right: &[f64]) -> bool {
    left.iter()
        .chain(right.iter())
        .all(|sample| sample.abs() <= f64::EPSILON)
}
