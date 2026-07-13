use crate::*;
use std::sync::{Mutex, OnceLock};

fn executor_test_lock() -> &'static Mutex<()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
}

fn parallel_event(node_id: u64, order: u64, time_seconds: f64) -> EventPayload {
    let mut opts = OptMap::new();
    opts.insert("attack".to_owned(), SynthValue::Float(0.005));
    opts.insert("sustain".to_owned(), SynthValue::Float(0.12));
    opts.insert("release".to_owned(), SynthValue::Float(0.08));
    opts.insert("amp".to_owned(), SynthValue::Float(0.08));
    EventPayload {
        node_id,
        seed: 91,
        order,
        kind: "play".to_owned(),
        time_seconds,
        value: SynthValue::Float(60.0 + (node_id % 7) as f64),
        opts,
        synth_name: "_sine".to_owned(),
        synth_opts: OptMap::new(),
        fx_chain: Vec::new(),
        controls: Vec::new(),
    }
}

#[test]
fn offline_render_is_bitwise_identical_across_worker_counts() {
    let _guard = executor_test_lock().lock().expect("executor test lock");
    let sample_rate = 48_000;
    let events = (0..16)
        .map(|index| parallel_event(index + 1, index, index as f64 * 0.005))
        .collect::<Vec<_>>();

    set_worker_count(Some(1)).expect("single-worker configuration is valid");
    let expected =
        render_plan_events(events.clone(), 0.35, sample_rate).expect("single-worker plan renders");

    for worker_count in [2, 4, 8] {
        reset_diagnostics();
        set_worker_count(Some(worker_count)).expect("explicit worker configuration is valid");
        let actual =
            render_plan_events(events.clone(), 0.35, sample_rate).expect("parallel plan renders");
        assert_eq!(
            actual, expected,
            "worker count {worker_count} changed PCM bytes"
        );
        let diagnostics = diagnostics();
        assert_eq!(diagnostics.worker_count, worker_count);
        assert!(diagnostics.parallel_regions > 0);
        assert!(diagnostics.parallel_tasks >= 2);
        assert!(
            diagnostics.parallel_scratch_peak_bytes <= diagnostics.parallel_scratch_limit_bytes
        );
        assert!(diagnostics.worker_pool_initializations <= 1);
    }

    reset_diagnostics();
    set_worker_count(None).expect("automatic worker configuration is valid");
    let actual =
        render_plan_events(events, 0.35, sample_rate).expect("automatic-worker plan renders");
    assert_eq!(actual, expected);
}

#[test]
fn worker_pool_is_persistent_and_configuration_is_bounded() {
    let _guard = executor_test_lock().lock().expect("executor test lock");
    assert!(set_worker_count(Some(3)).is_err());
    assert!(set_worker_count(Some(16)).is_err());

    let events = vec![parallel_event(1, 0, 0.0), parallel_event(2, 1, 0.01)];
    set_worker_count(Some(2)).expect("two workers are supported");
    render_plan_events(events.clone(), 0.3, 48_000).expect("first render succeeds");
    let first_initializations = diagnostics().worker_pool_initializations;
    render_plan_events(events, 0.3, 48_000).expect("second render succeeds");
    assert_eq!(
        diagnostics().worker_pool_initializations,
        first_initializations,
        "a render call must not create another worker pool"
    );
    assert!(first_initializations <= 1);
    set_worker_count(None).expect("automatic worker configuration is restored");
}
