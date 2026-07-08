//! Core Rust ECS storage primitives for Gummy Snake.
//!
//! The crate intentionally has no PyO3 dependency. The mandatory `gummy_canvas`
//! extension owns Python bindings and packaging.

pub mod archetype;
pub mod benchmark;
pub mod column;
pub mod command;
pub mod diagnostics;
pub mod entity;
pub mod error;
pub mod event;
pub mod execution;
pub mod hilbert;
pub mod plan;
pub mod query;
pub mod resource;
pub mod scheduler;
pub mod schema;
pub mod spatial;
pub mod spatial_registry;
pub mod tree_spatial;
pub mod world;

pub use archetype::{Archetype, ComponentRow, ComponentSetKey, ComponentTable, EntityRowData};
pub use column::{Column, EcsValue};
pub use command::{Command, CommandBuffer};
pub use diagnostics::Diagnostics;
pub use entity::{Entity, EntityAllocator};
pub use error::{EcsError, Result};
pub use event::{EventRecord, EventStore};
pub use execution::{
    ExecutionCanvasCommand, ExecutionCanvasFillBatch, ExecutionCanvasFillRecord, ExecutionReport,
    ExecutionWrite,
};
pub use hilbert::HilbertIndex;
pub use plan::{
    compile_bridge_plan, validate_plan, ActionNode, BridgePlanPayload, BridgeQueryPayload,
    CanvasCommandNode, ExprNode, PhysicalPlan, PhysicalPlanHandle, PhysicalQuery, PlanCache,
    SpatialAlgorithmNode, SpatialBoundsExprNode, SpatialRelationNode, BRIDGE_PLAN_VERSION,
};
pub use query::{CachedQuery, QueryFilter, QuerySnapshot, QueryTerm};
pub use resource::ResourceStore;
pub use scheduler::{
    build_deterministic_waves, deterministic_chunks, ecs_worker_count, execute_deterministic_waves,
    merge_command_batches_stably, AccessKey, AccessSummary, CommandBatch, SchedulePlan,
    ScheduleWave, ScheduledSystem, SchedulerDiagnostics, SchedulerOptions,
};
pub use schema::{ComponentSchema, FieldSchema, SchemaRegistry, StorageType};
pub use spatial::{
    Dimensions, HashGridIndex, SpatialAabb, SpatialCapabilities, SpatialIndexBackend,
    SpatialMemoryStats, SpatialPoint, SpatialRecord,
};
pub use spatial_registry::{
    SpatialAlgorithmKind, SpatialIndexDescriptor, SpatialIndexRegistry, SpatialIndexSlot,
    SpatialIndexStats,
};
pub use tree_spatial::{OctreeIndex, QuadtreeIndex};
pub use world::World;

pub const ECS_ABI_VERSION: u32 = 3;

pub fn health_check() -> &'static str {
    "gummy-ecs 3"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn world_allocates_reuses_and_tracks_generation() {
        let mut world = World::new();
        let first = world.spawn_empty();
        assert_eq!(first.index, 0);
        assert_eq!(first.generation, 0);
        assert_eq!(world.alive_count(), 1);

        world.despawn(first).unwrap();
        assert_eq!(world.alive_count(), 0);
        assert!(world.despawn(first).is_err());

        let reused = world.spawn_empty();
        assert_eq!(reused.index, first.index);
        assert_eq!(reused.generation, first.generation + 1);
        assert_eq!(world.alive_count(), 1);
    }

    #[test]
    fn world_registers_scalar_schema() {
        let mut world = World::new();
        world
            .register_schema(ComponentSchema::new(
                "Position",
                vec![
                    FieldSchema::new("x", StorageType::Float64),
                    FieldSchema::new("y", StorageType::Float64),
                ],
            ))
            .unwrap();
        assert_eq!(world.schema_count(), 1);
        assert_eq!(world.schema("Position").unwrap().fields.len(), 2);
    }
}
