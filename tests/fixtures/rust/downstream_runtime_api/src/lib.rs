//! Compile-only external-consumer contract for runtime workspace crates.
//!
//! `cargo check` type-checks these uncalled probes. Keep additions limited to
//! public Rust APIs consumed across crates; the Python extension remains the
//! supported `gummy_canvas` boundary.

use gummy_ecs as ecs;
use pyo3::types::PyBytesMethods;

const _: [(); 4] = [(); ecs::ECS_ABI_VERSION as usize];
const _: [(); 2] = [(); ecs::BRIDGE_PLAN_VERSION as usize];

#[allow(dead_code)]
fn ecs_root_reexports_compile() {
    let _: &'static str = ecs::health_check();
    let entity = ecs::Entity {
        index: 1,
        generation: 0,
    };
    let _: ecs::Entity = entity;
    let _: ecs::World = ecs::World::new();
    let _: ecs::ComponentSchema = ecs::ComponentSchema::new(
        "Position",
        vec![ecs::FieldSchema::new("x", ecs::StorageType::Float64)],
    );

    // These are root re-exports used by bridge consumers. `size_of` checks
    // visibility without constructing intentionally private internals.
    let _ = std::mem::size_of::<ecs::BridgePlanPayload>();
    let _ = std::mem::size_of::<ecs::BridgeQueryPayload>();
    let _ = std::mem::size_of::<ecs::PhysicalPlan>();
    let _ = std::mem::size_of::<ecs::PhysicalPlanHandle>();
    let _ = std::mem::size_of::<ecs::PhysicalQuery>();
    let _ = std::mem::size_of::<ecs::ActionNode>();
    let _ = std::mem::size_of::<ecs::ExprNode>();
    let _ = std::mem::size_of::<ecs::ExecutionReport>();
    let _ = std::mem::size_of::<ecs::ExecutionWrite>();
    let _ = std::mem::size_of::<ecs::ExecutionCanvasCommand>();
    let _ = std::mem::size_of::<ecs::ExecutionCanvasFillBatch>();
    let _ = std::mem::size_of::<ecs::ExecutionCanvasFillRecord>();
    let _ = std::mem::size_of::<ecs::AccessKey>();
    let _ = std::mem::size_of::<ecs::AccessSummary>();
    let _ = std::mem::size_of::<ecs::ScheduledSystem>();
    let _ = std::mem::size_of::<ecs::SchedulePlan>();
    let _ = std::mem::size_of::<ecs::SchedulerOptions>();
    let _ = std::mem::size_of::<ecs::SpatialAlgorithmKind>();
    let _ = std::mem::size_of::<ecs::SpatialIndexDescriptor>();
    let _ = std::mem::size_of::<ecs::SpatialIndexRegistry>();
    let _ = std::mem::size_of::<ecs::SpatialIndexStats>();
    let _ = std::mem::size_of::<ecs::HashGridIndex>();
    let _ = std::mem::size_of::<ecs::QuadtreeIndex>();
    let _ = std::mem::size_of::<ecs::OctreeIndex>();
    let _ = std::mem::size_of::<ecs::HilbertIndex>();
}

#[allow(dead_code)]
fn synth_stable_domain_api_compiles(plan: &gummy_synth::SynthPlaybackPlan) -> f64 {
    plan.duration_seconds()
}

/// Transitional PyO3-coupled source APIs. PBI 019 may migrate these atomically
/// while preserving the Python `_canvas` surface and behavior.
#[allow(dead_code)]
fn synth_transitional_pyo3_api_compiles() {
    pyo3::Python::with_gil(|py| {
        let module = pyo3::types::PyModule::new_bound(py, "runtime_contract")
            .expect("contract module creation must compile");
        let event = pyo3::types::PyDict::new_bound(py);
        let events = pyo3::types::PyList::empty_bound(py);
        let bytes = pyo3::types::PyBytes::new_bound(py, b"");

        let _: pyo3::PyResult<()> = gummy_synth::register_pyfunctions(&module);
        let _: pyo3::PyResult<pyo3::Bound<'_, pyo3::types::PyBytes>> =
            gummy_synth::synth_render_event_wav(py, &event, 44_100);
        let _: pyo3::PyResult<pyo3::Bound<'_, pyo3::types::PyBytes>> =
            gummy_synth::synth_render_plan_wav(py, &events, 0.0, 44_100);
        let _: pyo3::PyResult<pyo3::Bound<'_, pyo3::types::PyBytes>> =
            gummy_synth::synth_render_serialized_plan_wav(py, &bytes, 44_100);
        let _: pyo3::PyResult<f64> = gummy_synth::synth_sample_duration(bytes.as_any());
        let _: pyo3::PyResult<Vec<u8>> =
            gummy_synth::render_serialized_plan_wav_bytes(bytes.as_bytes(), 44_100);
        let _: pyo3::PyResult<gummy_synth::SynthPlaybackPlan> =
            gummy_synth::SynthPlaybackPlan::from_serialized_plan(bytes.as_bytes());
    });
}

// `gummy_canvas_runtime` is deliberately an unused direct dependency: cargo
// still builds it as an external consumer, while its Python extension remains
// the supported contract rather than a new public Rust API.
