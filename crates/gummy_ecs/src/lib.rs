//! Core Rust ECS storage primitives for Gummy Snake.
//!
//! The crate intentionally has no PyO3 dependency. The mandatory `gummy_canvas`
//! extension owns Python bindings and packaging. The contributor
//! [ownership map](../../../docs/contribute/ownership_map.md) is the canonical
//! cross-crate navigation document; do not duplicate its runtime contracts here.

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
pub use column::{coerce_value_for_storage, Column, EcsValue};
pub use command::{Command, CommandBuffer};
pub use diagnostics::Diagnostics;
pub use entity::{Entity, EntityAllocator};
pub use error::{EcsError, Result};
pub use event::{EventRecord, EventStore};
pub use execution::{
    ExecutionCanvasCommand, ExecutionCanvasFillBatch, ExecutionCanvasFillRecord, ExecutionReport,
    ExecutionWrite,
};
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
pub use schema::{ComponentSchema, FieldSchema, ListElementType, SchemaRegistry, StorageType};
pub use spatial::{
    Dimensions, HashGridIndex, HilbertIndex, OctreeIndex, QuadtreeIndex, SpatialAabb,
    SpatialAlgorithmKind, SpatialCapabilities, SpatialIndexBackend, SpatialIndexDescriptor,
    SpatialIndexRegistry, SpatialIndexSlot, SpatialIndexStats, SpatialMemoryStats, SpatialPoint,
    SpatialRecord,
};
pub use world::World;

pub const CRATE_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const ECS_ABI_VERSION: u32 = 5;

pub fn health_check() -> &'static str {
    "gummy-ecs 5"
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
    fn spatial_compatibility_modules_and_root_exports_resolve() {
        fn accepts_spatial_backend(_backend: &impl SpatialIndexBackend) {}

        let bounds_2d = SpatialAabb::point2(0.0, 0.0, 10.0, 10.0).unwrap();
        let hilbert = hilbert::HilbertIndex::new(bounds_2d.clone(), 8).unwrap();
        accepts_spatial_backend(&hilbert);
        let _: SpatialCapabilities = hilbert.capabilities();
        let _: HilbertIndex = hilbert;

        let quadtree = tree_spatial::QuadtreeIndex::new(bounds_2d, 16).unwrap();
        accepts_spatial_backend(&quadtree);
        let _: QuadtreeIndex = quadtree;

        let bounds_3d = SpatialAabb::point3(0.0, 0.0, 0.0, 10.0, 10.0, 10.0).unwrap();
        let octree = tree_spatial::OctreeIndex::new(bounds_3d, 16).unwrap();
        accepts_spatial_backend(&octree);
        let _: OctreeIndex = octree;

        let hash_grid = HashGridIndex::new(Dimensions::D2, 1.0).unwrap();
        accepts_spatial_backend(&hash_grid);

        let descriptor = spatial_registry::SpatialIndexDescriptor {
            name: Some("positions".to_string()),
            target_query: vec!["Position".to_string()],
            dimensions: 2,
            algorithm: spatial_registry::SpatialAlgorithmKind::HashGrid,
            update_policy: "auto".to_string(),
        };
        let _: SpatialIndexDescriptor = descriptor.clone();
        let _: SpatialAlgorithmKind = descriptor.algorithm.clone();
        let mut registry: SpatialIndexRegistry = spatial_registry::SpatialIndexRegistry::new();
        let id = registry.intern(descriptor);
        let slot: &SpatialIndexSlot = registry.get(id).unwrap();
        let _: SpatialIndexStats = slot.stats.clone();
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
