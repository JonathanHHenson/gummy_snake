use crate::*;

fn event(node_id: u64, order: u64, time_seconds: f64) -> EventPayload {
    EventPayload {
        node_id,
        seed: 17,
        order,
        kind: "play".to_owned(),
        time_seconds,
        value: SynthValue::Float(60.0),
        opts: OptMap::new(),
        synth_name: "_sine".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: vec![ControlPayload {
            time_seconds: time_seconds + 0.005,
            opts: OptMap::new(),
        }],
    }
}

#[test]
fn compiled_program_orders_same_frame_events_by_declared_order() {
    let program = CompiledSynthProgram::compile(
        vec![event(2, 4, 0.0031), event(1, 3, 0.0034), event(3, 2, 0.001)],
        0.1,
        1_000,
    )
    .expect("program compiles");

    assert_eq!(program.duration_frames(), 100);
    assert_eq!(program.event_count(), 3);
    assert_eq!(program.event_frame(0), Some(1));
    assert_eq!(program.event_frame(1), Some(3));
    assert_eq!(program.event_frame(2), Some(3));
    assert_eq!(program.events()[1].order, 3);
    assert_eq!(program.events()[2].order, 4);
    assert_eq!(program.control_time(0, 0).map(SynthFrame::get), Some(6));
}

#[test]
fn compiled_program_interns_execution_identifiers_and_reuses_target_indexes() {
    let mut first = event(9, 0, 0.0);
    first.synth_name = ":_SINE".to_owned();
    first.controls[0].opts = OptMap::from([
        ("pan".to_owned(), SynthValue::Float(0.25)),
        ("amp".to_owned(), SynthValue::Float(0.5)),
    ]);
    first.fx_chain.push(FxPayload {
        id: 44,
        name: ":_LPF".to_owned(),
        opts: OptMap::new(),
    });
    let mut second = event(9, 1, 0.01);
    second.synth_name = "_sine".to_owned();
    second.fx_chain.push(FxPayload {
        id: 45,
        name: "lpf".to_owned(),
        opts: OptMap::new(),
    });

    let program = CompiledSynthProgram::compile(vec![second, first], 0.1, 8_000).unwrap();
    let clone = program.clone();

    assert_eq!(program.event_id(0).map(CompiledEventId::get), Some(0));
    assert_eq!(program.event_id(1).map(CompiledEventId::get), Some(1));
    assert_eq!(program.event_kind(0), Some(CompiledEventKind::Play));
    assert_eq!(program.source_identifier(0), program.source_identifier(1));
    assert_eq!(
        program.identifier(program.source_identifier(0).unwrap()),
        Some("_sine")
    );
    assert_eq!(
        program
            .event_ids_for_node(9)
            .iter()
            .map(|id| id.get())
            .collect::<Vec<_>>(),
        vec![0, 1]
    );
    assert_eq!(
        program
            .event_ids_for_fx_target(44)
            .iter()
            .map(|id| id.get())
            .collect::<Vec<_>>(),
        vec![0]
    );
    let parameters = program.control_parameters(0, 0).unwrap();
    assert_eq!(parameters.len(), 2);
    assert_eq!(program.identifier(parameters[0]), Some("amp"));
    assert_eq!(program.identifier(parameters[1]), Some("pan"));
    assert_eq!(program.events().as_ptr(), clone.events().as_ptr());
}

#[test]
fn compiled_program_render_matches_the_typed_entry_point() {
    let events = vec![event(1, 0, 0.0), event(2, 1, 0.01)];
    let program = CompiledSynthProgram::compile(events.clone(), 0.05, 8_000).unwrap();

    let compiled = render_compiled_program_wav(&program).unwrap();
    let typed = render_plan_events(events, 0.05, 8_000).unwrap();

    assert_eq!(compiled, typed);
}

#[test]
fn compiled_program_rejects_out_of_budget_control_frames_before_execution() {
    let mut invalid = event(1, 0, 0.0);
    invalid.controls[0].time_seconds = 100_000.0;

    let error = CompiledSynthProgram::compile(vec![invalid], 0.1, 48_000).unwrap_err();

    assert!(error
        .to_string()
        .contains("synth control time exceeds the synth output budget"));
}
