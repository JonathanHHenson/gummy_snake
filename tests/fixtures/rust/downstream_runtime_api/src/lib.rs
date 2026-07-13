//! Compile-only external-consumer contract for runtime workspace crates.
//!
//! `cargo check` type-checks these uncalled probes. Keep additions limited to
//! public Rust APIs consumed across crates; the Python extension remains the
//! supported `gummy_canvas` boundary.

use gummy_ecs as ecs;

const _: [(); 5] = [(); ecs::ECS_ABI_VERSION as usize];
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

/// Typed synth APIs are ordinary Rust domain calls. The Python `_canvas`
/// functions are intentionally owned and registered by `gummy_canvas`.
#[allow(dead_code)]
fn synth_typed_api_compiles() {
    let bytes = b"";
    let _: gummy_synth::SynthResult<Vec<u8>> =
        gummy_synth::render_serialized_plan_wav_bytes(bytes, 44_100);
    let _: gummy_synth::SynthResult<gummy_synth::SynthPlaybackPlan> =
        gummy_synth::SynthPlaybackPlan::from_serialized_plan(bytes);
}

// `gummy_canvas_runtime` is deliberately an unused direct dependency: cargo
// still builds it as an external consumer, while its Python extension remains
// the supported contract rather than a new public Rust API.
