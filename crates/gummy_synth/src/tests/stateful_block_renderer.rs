use crate::stateful_block_renderer::StatefulBlockRenderer;
use crate::wav_sink::StereoPcmWavSink;
use crate::*;
use std::cell::RefCell;
use std::io::{self, Cursor, Seek, SeekFrom, Write};
use std::rc::Rc;

#[derive(Clone, Default)]
struct SharedCursor(Rc<RefCell<Cursor<Vec<u8>>>>);

impl SharedCursor {
    fn bytes(&self) -> Vec<u8> {
        self.0.borrow().get_ref().clone()
    }
}

impl Write for SharedCursor {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        self.0.borrow_mut().write(buffer)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.0.borrow_mut().flush()
    }
}

impl Seek for SharedCursor {
    fn seek(&mut self, position: SeekFrom) -> io::Result<u64> {
        self.0.borrow_mut().seek(position)
    }
}

#[derive(Default)]
struct CollectingSink {
    samples: Vec<i16>,
    would_block_once: bool,
    finished: bool,
}

impl PcmSink for CollectingSink {
    fn write_interleaved_i16(&mut self, samples: &[i16]) -> SynthResult<SinkWrite> {
        if self.would_block_once {
            self.would_block_once = false;
            return Ok(SinkWrite::WouldBlock);
        }
        self.samples.extend_from_slice(samples);
        Ok(SinkWrite::Accepted)
    }

    fn finish(&mut self) -> SynthResult<()> {
        self.finished = true;
        Ok(())
    }
}

fn sine_event(node_id: u64, order: u64, time_seconds: f64, note: f64) -> EventPayload {
    EventPayload {
        node_id,
        seed: 320,
        order,
        kind: "play".to_owned(),
        time_seconds,
        value: SynthValue::Float(note),
        opts: OptMap::new(),
        synth_name: "_sine".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    }
}

fn render(
    program: CompiledSynthProgram,
    block_frames: usize,
    would_block_once: bool,
) -> (Vec<i16>, BlockRenderDiagnostics) {
    let mut renderer = StatefulBlockRenderer::new(program, BlockRenderConfig { block_frames })
        .expect("supported program constructs a stateful renderer");
    let mut sink = CollectingSink {
        would_block_once,
        ..CollectingSink::default()
    };
    loop {
        if renderer.step(&mut sink).expect("render step succeeds") == BlockRenderStep::Finished {
            break;
        }
    }
    assert!(sink.finished);
    (sink.samples, renderer.diagnostics())
}

#[test]
fn stateful_sine_renderer_is_exactly_partition_invariant() {
    let events = vec![sine_event(1, 0, 0.0, 60.0), sine_event(2, 1, 0.013, 67.0)];
    let program = CompiledSynthProgram::compile(events, 0.05, 8_000).unwrap();

    let (one, _) = render(program.clone(), 1, false);
    let (seven, _) = render(program.clone(), 7, false);
    let (sixty_three, _) = render(program, 63, false);

    assert_eq!(one, seven);
    assert_eq!(one, sixty_three);
    assert!(one.iter().any(|sample| *sample != 0));
}

#[test]
fn stateful_primitive_voices_are_partition_invariant() {
    for synth_name in [
        "_saw", "_tri", "_pulse", "_fm", "_noise", "_pnoise", "_bnoise", "_gnoise", "_cnoise",
    ] {
        let mut event = sine_event(1, 0, 0.0, 60.0);
        event.synth_name = synth_name.to_owned();
        let program = CompiledSynthProgram::compile(vec![event], 0.05, 8_000).unwrap();
        let (single, _) = render(program.clone(), 1, false);
        let (blocked, _) = render(program, 31, false);
        assert_eq!(single, blocked, "{synth_name} block partition changed PCM");
        assert!(single.iter().any(|sample| *sample != 0));
    }
}

#[test]
fn stateful_cutoff_envelope_options_are_supported_audible_and_partition_invariant() {
    let mut event = sine_event(1, 0, 0.0, 40.0);
    event.synth_name = "_saw".to_owned();
    event.opts = OptMap::from([
        ("attack".to_owned(), SynthValue::Float(0.0)),
        ("decay".to_owned(), SynthValue::Float(0.0)),
        ("sustain".to_owned(), SynthValue::Float(0.2)),
        ("release".to_owned(), SynthValue::Float(0.01)),
        ("sustain_level".to_owned(), SynthValue::Float(1.0)),
        ("cutoff".to_owned(), SynthValue::Float(120.0)),
        ("cutoff_min".to_owned(), SynthValue::Float(30.0)),
        ("cutoff_attack".to_owned(), SynthValue::Float(0.0)),
        ("cutoff_decay".to_owned(), SynthValue::Float(0.08)),
        ("cutoff_sustain".to_owned(), SynthValue::Float(0.12)),
        ("cutoff_release".to_owned(), SynthValue::Float(0.0)),
        ("cutoff_attack_level".to_owned(), SynthValue::Float(1.0)),
        ("cutoff_decay_level".to_owned(), SynthValue::Float(0.0)),
        ("cutoff_sustain_level".to_owned(), SynthValue::Float(0.0)),
        ("cutoff_env_curve".to_owned(), SynthValue::Float(2.0)),
        ("res".to_owned(), SynthValue::Float(0.9)),
    ]);
    let mut static_event = event.clone();
    static_event
        .opts
        .retain(|key, _| !key.starts_with("cutoff_"));
    let swept_program = CompiledSynthProgram::compile(vec![event], 0.21, 8_000).unwrap();
    let static_program = CompiledSynthProgram::compile(vec![static_event], 0.21, 8_000).unwrap();

    let (single, _) = render(swept_program.clone(), 1, false);
    let (blocked, _) = render(swept_program, 37, false);
    let (static_pcm, _) = render(static_program, 37, false);

    assert_eq!(single, blocked);
    assert_ne!(blocked, static_pcm);
    let left = blocked
        .chunks_exact(2)
        .map(|frame| frame[0])
        .collect::<Vec<_>>();
    let average_delta = |samples: &[i16]| {
        samples
            .windows(2)
            .map(|pair| (i32::from(pair[1]) - i32::from(pair[0])).unsigned_abs() as f64)
            .sum::<f64>()
            / samples.len().saturating_sub(1).max(1) as f64
    };
    let early = average_delta(&left[180..580]);
    let late = average_delta(&left[1_280..1_600]);
    assert!(early > late * 1.5, "early={early}, late={late}");
}

#[test]
fn stateful_layered_pulse_and_pre_filter_options_are_audible_and_partition_invariant() {
    let mut event = sine_event(1, 0, 0.0, 52.0);
    event.synth_name = "_layered".to_owned();
    event.opts = OptMap::from([
        ("attack".to_owned(), SynthValue::Float(0.0)),
        ("decay".to_owned(), SynthValue::Float(0.0)),
        ("sustain".to_owned(), SynthValue::Float(0.04)),
        ("release".to_owned(), SynthValue::Float(0.01)),
        ("pre_shape_normalise".to_owned(), SynthValue::Bool(true)),
        ("pre_shape_level".to_owned(), SynthValue::Float(0.8)),
        ("pre_filter_env".to_owned(), SynthValue::Bool(true)),
        (
            "pre_filter_shape".to_owned(),
            SynthValue::String("squared".to_owned()),
        ),
        (
            "layers".to_owned(),
            SynthValue::List(vec![SynthValue::Dict(OptMap::from([
                ("wave".to_owned(), SynthValue::String("pulse".to_owned())),
                ("transpose".to_owned(), SynthValue::Float(0.0)),
                ("amp".to_owned(), SynthValue::Float(1.0)),
                (
                    "opts".to_owned(),
                    SynthValue::Dict(OptMap::from([
                        ("pulse_width".to_owned(), SynthValue::Float(0.2)),
                        ("pulse_width_lfo_rate".to_owned(), SynthValue::Float(3.0)),
                        ("pulse_width_lfo_depth".to_owned(), SynthValue::Float(0.15)),
                        ("pulse_width_lfo_phase".to_owned(), SynthValue::Float(0.1)),
                        ("pulse_width_lfo_wave".to_owned(), SynthValue::Float(3.0)),
                    ])),
                ),
            ]))]),
        ),
    ]);
    let mut plain = event.clone();
    plain.opts.remove("pre_shape_normalise");
    plain.opts.remove("pre_shape_level");
    plain.opts.remove("pre_filter_env");
    plain.opts.remove("pre_filter_shape");
    let SynthValue::List(layers) = plain.opts.get_mut("layers").unwrap() else {
        unreachable!();
    };
    let SynthValue::Dict(layer) = &mut layers[0] else {
        unreachable!();
    };
    layer.insert("opts".to_owned(), SynthValue::Dict(OptMap::new()));
    let shaped_program = CompiledSynthProgram::compile(vec![event], 0.05, 8_000).unwrap();
    let plain_program = CompiledSynthProgram::compile(vec![plain], 0.05, 8_000).unwrap();

    let (single, _) = render(shaped_program.clone(), 1, false);
    let (blocked, _) = render(shaped_program, 29, false);
    let (plain_pcm, _) = render(plain_program, 29, false);

    assert_eq!(single, blocked);
    assert_ne!(blocked, plain_pcm);
}

#[test]
fn stateful_sine_amp_and_pan_controls_apply_at_the_compiled_frame() {
    let mut controlled = sine_event(1, 0, 0.0, 69.0);
    controlled.controls.push(ControlPayload {
        time_seconds: 0.001,
        opts: OptMap::from([
            ("amp".to_owned(), SynthValue::Float(0.0)),
            ("pan".to_owned(), SynthValue::Float(1.0)),
        ]),
    });
    let program = CompiledSynthProgram::compile(vec![controlled], 0.05, 8_000).unwrap();
    let mut renderer =
        StatefulBlockRenderer::new(program, BlockRenderConfig { block_frames: 7 }).unwrap();
    let mut sink = MemoryPcmSink::default();

    renderer.render_to_sink(&mut sink).unwrap();

    let frames = sink.samples().chunks_exact(2).collect::<Vec<_>>();
    assert!(frames[..8]
        .iter()
        .any(|frame| frame[0] != 0 || frame[1] != 0));
    assert!(frames[8..]
        .iter()
        .all(|frame| frame[0] == 0 && frame[1] == 0));
}

#[test]
fn stateful_renderer_normaliser_preserves_partition_equivalence_and_flushes_latency() {
    let events = vec![sine_event(1, 0, 0.0, 60.0), sine_event(2, 1, 0.013, 67.0)];
    let program = CompiledSynthProgram::compile(events, 0.05, 8_000).unwrap();
    let render_normalised = |block_frames| {
        let mut renderer = StatefulBlockRenderer::new_with_normaliser(
            program.clone(),
            BlockRenderConfig { block_frames },
            CausalNormaliserConfig::default(),
        )
        .unwrap();
        let mut sink = MemoryPcmSink::default();
        renderer.render_to_sink(&mut sink).unwrap();
        (sink.into_samples(), renderer.diagnostics())
    };

    let (one, one_diagnostics) = render_normalised(1);
    let (sixty_three, sixty_three_diagnostics) = render_normalised(63);

    assert_eq!(one, sixty_three);
    assert!(one_diagnostics.normaliser_latency_frames > 0);
    assert_eq!(
        one_diagnostics.rendered_output_frames,
        sixty_three_diagnostics.rendered_output_frames
    );
    assert!(one_diagnostics.rendered_output_frames > 0);
}

#[test]
fn stateful_renderer_drains_one_session_to_the_canonical_memory_sink() {
    let program =
        CompiledSynthProgram::compile(vec![sine_event(1, 0, 0.0, 69.0)], 0.05, 8_000).unwrap();
    let mut renderer =
        StatefulBlockRenderer::new(program, BlockRenderConfig { block_frames: 32 }).unwrap();
    let mut sink = MemoryPcmSink::default();

    renderer.render_to_sink(&mut sink).unwrap();

    assert!(sink.is_finished());
    assert!(!sink.samples().is_empty());
    assert_eq!(
        sink.samples().len() / 2,
        renderer.diagnostics().rendered_output_frames as usize
    );
}

#[test]
fn stateful_renderer_writes_one_streaming_wav_through_the_same_session() {
    let program =
        CompiledSynthProgram::compile(vec![sine_event(1, 0, 0.0, 69.0)], 0.05, 8_000).unwrap();
    let mut renderer =
        StatefulBlockRenderer::new(program, BlockRenderConfig { block_frames: 31 }).unwrap();
    let writer = SharedCursor::default();
    let observer = writer.clone();
    let mut sink = StereoPcmWavSink::new(writer, 8_000).unwrap();

    renderer.render_to_sink(&mut sink).unwrap();

    let wav = observer.bytes();
    assert_eq!(&wav[..4], b"RIFF");
    assert_eq!(&wav[8..12], b"WAVE");
    assert_eq!(
        u32::from_le_bytes(wav[40..44].try_into().unwrap()) as usize,
        wav.len() - 44
    );
    assert_eq!(
        wav.len() - 44,
        renderer.diagnostics().rendered_output_frames as usize * 4
    );
}

#[test]
fn canonical_wav_output_matches_arbitrary_block_partitions_exactly() {
    let mut hot = sine_event(1, 0, 0.0, 60.0);
    hot.opts.insert("amp".to_owned(), SynthValue::Float(1.8));
    let mut second = sine_event(2, 1, 0.007, 67.0);
    second.opts.insert("amp".to_owned(), SynthValue::Float(1.4));
    let program = CompiledSynthProgram::compile(vec![hot, second], 0.08, 8_000).unwrap();
    let canonical = render_compiled_program_wav(&program).unwrap();

    for block_frames in [1, 7, 31, 257] {
        let (samples, diagnostics) = render(program.clone(), block_frames, false);
        let mut payload = Vec::with_capacity(samples.len() * 2);
        for sample in samples {
            payload.extend_from_slice(&sample.to_le_bytes());
        }
        assert_eq!(&canonical[44..], payload, "partition {block_frames}");
        assert_eq!(diagnostics.rendered_output_frames, 640);
        assert_eq!(diagnostics.limiter_latency_frames, 80);
        assert!(diagnostics.scratch_peak_bytes < 128 * 1024);
    }
}

#[test]
fn stateful_renderer_reoffers_pending_block_without_advancing_state() {
    let program =
        CompiledSynthProgram::compile(vec![sine_event(1, 0, 0.0, 69.0)], 0.05, 8_000).unwrap();
    let (accepted, accepted_diagnostics) = render(program.clone(), 16, false);
    let (backpressured, backpressured_diagnostics) = render(program, 16, true);

    assert_eq!(accepted, backpressured);
    assert_eq!(
        accepted_diagnostics.rendered_output_frames,
        backpressured_diagnostics.rendered_output_frames
    );
    assert_eq!(backpressured_diagnostics.sink_would_block_count, 1);
    assert_eq!(backpressured_diagnostics.sink_pending_peak_frames, 16);
}

#[test]
fn stateful_multi_note_and_layered_note_controls_preserve_intervals_and_partitions() {
    for layered in [false, true] {
        let mut event = sine_event(1, 0, 0.0, 60.0);
        event.value = SynthValue::List(vec![SynthValue::Float(60.0), SynthValue::Float(64.0)]);
        if layered {
            event.synth_name = "_layered".to_owned();
            let layer = OptMap::from([
                ("wave".to_owned(), SynthValue::String("sine".to_owned())),
                ("transpose".to_owned(), SynthValue::Float(0.0)),
                ("amp".to_owned(), SynthValue::Float(1.0)),
                ("opts".to_owned(), SynthValue::Dict(OptMap::new())),
            ]);
            event.opts.insert(
                "layers".to_owned(),
                SynthValue::List(vec![SynthValue::Dict(layer)]),
            );
        }
        event.controls.push(ControlPayload {
            time_seconds: 0.004,
            opts: OptMap::from([
                ("note".to_owned(), SynthValue::Float(67.0)),
                ("note_slide".to_owned(), SynthValue::Float(0.003)),
            ]),
        });
        let mut uncontrolled = event.clone();
        uncontrolled.controls.clear();
        let program = CompiledSynthProgram::compile(vec![event], 0.05, 8_000).unwrap();
        let baseline = CompiledSynthProgram::compile(vec![uncontrolled], 0.05, 8_000).unwrap();

        let (single, _) = render(program.clone(), 1, false);
        let (blocked, _) = render(program, 29, false);
        let (dry_control, _) = render(baseline, 29, false);

        assert_eq!(single, blocked, "layered={layered}");
        assert_ne!(blocked, dry_control, "layered={layered}");
    }
}

#[test]
fn stateful_krush_is_audible_and_exactly_partition_invariant() {
    let mut wet = sine_event(1, 0, 0.0, 62.0);
    wet.fx_chain.push(FxPayload {
        id: 8,
        name: "_krush".to_owned(),
        opts: OptMap::from([
            ("gain".to_owned(), SynthValue::Float(5.0)),
            ("cutoff".to_owned(), SynthValue::Float(90.0)),
            ("res".to_owned(), SynthValue::Float(0.2)),
            ("mix".to_owned(), SynthValue::Float(1.0)),
        ]),
    });
    let dry = sine_event(1, 0, 0.0, 62.0);
    let wet_program = CompiledSynthProgram::compile(vec![wet], 0.06, 8_000).unwrap();
    let dry_program = CompiledSynthProgram::compile(vec![dry], 0.06, 8_000).unwrap();

    let (one, _) = render(wet_program.clone(), 1, false);
    let (thirty_one, _) = render(wet_program, 31, false);
    let (dry_pcm, _) = render(dry_program, 31, false);

    assert_eq!(one, thirty_one);
    assert_ne!(one, dry_pcm);
}

#[test]
fn stateful_compiled_fx_chain_is_native_and_partition_invariant() {
    let mut event = sine_event(1, 0, 0.0, 62.0);
    event.fx_chain.push(FxPayload {
        id: 9,
        name: "_chain".to_owned(),
        opts: OptMap::from([
            (
                "ops".to_owned(),
                SynthValue::List(vec![
                    SynthValue::Dict(OptMap::from([
                        (
                            "op".to_owned(),
                            SynthValue::String("distortion_shape".to_owned()),
                        ),
                        ("distort".to_owned(), SynthValue::Float(0.6)),
                    ])),
                    SynthValue::Dict(OptMap::from([
                        ("op".to_owned(), SynthValue::String("filter".to_owned())),
                        ("kind".to_owned(), SynthValue::String("lowpass".to_owned())),
                        ("cutoff".to_owned(), SynthValue::Float(85.0)),
                    ])),
                ]),
            ),
            ("mix".to_owned(), SynthValue::Float(1.0)),
        ]),
    });
    let program = CompiledSynthProgram::compile(vec![event], 0.06, 8_000).unwrap();

    let (one, _) = render(program.clone(), 1, false);
    let (blocked, diagnostics) = render(program, 43, false);

    assert_eq!(one, blocked);
    assert!(blocked.iter().any(|sample| *sample != 0));
    assert!(diagnostics.processor_state_bytes < 2 * 1024 * 1024);
}

#[test]
fn shared_fx_controls_normalisation_and_tails_are_partition_invariant_and_bounded() {
    let mut first = sine_event(1, 0, 0.0, 57.0);
    first
        .opts
        .insert("sustain".to_owned(), SynthValue::Float(0.006));
    first
        .opts
        .insert("release".to_owned(), SynthValue::Float(0.004));
    first.fx_chain = vec![
        FxPayload {
            id: 10,
            name: "_compressor".to_owned(),
            opts: OptMap::from([
                ("threshold".to_owned(), SynthValue::Float(0.05)),
                ("slope_above".to_owned(), SynthValue::Float(0.2)),
                ("mix".to_owned(), SynthValue::Float(1.0)),
            ]),
        },
        FxPayload {
            id: 11,
            name: "_normaliser".to_owned(),
            opts: OptMap::from([
                ("level".to_owned(), SynthValue::Float(0.7)),
                ("mix".to_owned(), SynthValue::Float(1.0)),
            ]),
        },
        FxPayload {
            id: 12,
            name: "_echo".to_owned(),
            opts: OptMap::from([
                ("phase".to_owned(), SynthValue::Float(0.003)),
                ("decay".to_owned(), SynthValue::Float(0.012)),
                ("max_phase".to_owned(), SynthValue::Float(0.02)),
                ("mix".to_owned(), SynthValue::Float(1.0)),
            ]),
        },
    ];
    let mut second = first.clone();
    second.node_id = 2;
    second.order = 2;
    second.value = SynthValue::Float(64.0);
    second.fx_chain[0]
        .opts
        .insert("threshold".to_owned(), SynthValue::Float(0.08));
    let mut independent = second.clone();
    independent.fx_chain[0].id = 20;
    independent.fx_chain[1].id = 21;
    independent.fx_chain[2].id = 22;

    let shared = CompiledSynthProgram::compile(vec![first.clone(), second], 0.06, 8_000).unwrap();
    let separate = CompiledSynthProgram::compile(vec![first, independent], 0.06, 8_000).unwrap();
    let (one, one_diagnostics) = render(shared.clone(), 1, false);
    let (blocked, blocked_diagnostics) = render(shared, 37, false);
    let (separate_pcm, _) = render(separate, 37, false);

    assert_eq!(one, blocked);
    assert_ne!(blocked, separate_pcm);
    assert!(
        blocked
            .iter()
            .map(|sample| sample.unsigned_abs())
            .max()
            .unwrap()
            <= 32_112
    );
    assert!(one_diagnostics.tail_frames_rendered > 0);
    assert!(blocked_diagnostics.tail_frames_rendered > 0);
    assert!(one_diagnostics.processor_state_bytes < 2 * 1024 * 1024);
    assert!(blocked_diagnostics.processor_state_bytes < 2 * 1024 * 1024);
}

#[test]
fn stateful_renderer_rejects_unmigrated_controls_without_fallback() {
    let mut controlled = sine_event(1, 0, 0.0, 60.0);
    controlled.controls.push(ControlPayload {
        time_seconds: 0.01,
        opts: OptMap::from([("attack".to_owned(), SynthValue::Float(0.01))]),
    });
    let program = CompiledSynthProgram::compile(vec![controlled], 0.05, 8_000).unwrap();
    assert!(
        StatefulBlockRenderer::new(program, BlockRenderConfig::default())
            .unwrap_err()
            .to_string()
            .contains("does not support control field")
    );
}
