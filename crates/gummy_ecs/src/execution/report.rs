use crate::column::EcsValue;
use crate::entity::Entity;

#[derive(Debug, Clone, PartialEq)]
pub enum ExecutionWrite {
    ComponentField {
        entity: Entity,
        component: String,
        field: String,
        value: EcsValue,
    },
    ResourceField {
        resource: String,
        field: String,
        value: EcsValue,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionEvent {
    pub event_type: String,
    pub payload: EcsValue,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionCanvasCommand {
    pub command: String,
    pub args: Vec<EcsValue>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionCanvasFillRecord {
    pub kind: u8,
    pub a: f64,
    pub b: f64,
    pub c: f64,
    pub d: f64,
    pub e: f64,
    pub f: f64,
    pub r: u8,
    pub g: u8,
    pub blue: u8,
    pub alpha: u8,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ExecutionCanvasFillBatch {
    pub records: Vec<ExecutionCanvasFillRecord>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ExecutionReport {
    pub rows_scanned: usize,
    pub fields_written: usize,
    pub resource_fields_written: usize,
    pub events_emitted: usize,
    pub structural_commands: usize,
    pub duplicate_writes: usize,
    pub spatial_indexes_built: usize,
    pub spatial_candidate_rows: usize,
    pub spatial_exact_rows: usize,
    pub spatial_false_positive_rows: usize,
    pub spatial_deduplicated_pairs: usize,
    pub spatial_algorithm_hash_grid: usize,
    pub spatial_algorithm_quadtree: usize,
    pub spatial_algorithm_octree: usize,
    pub spatial_algorithm_hilbert_curve: usize,
    pub spatial_index_reuses: usize,
    pub spatial_index_full_rebuilds: usize,
    pub spatial_index_incremental_updates: usize,
    pub spatial_parallel_chunks: usize,
    pub spatial_parallel_workers: usize,
    pub spatial_thread_scratch_reuses: usize,
    pub spatial_candidate_buffer_growths: usize,
    pub writes: Vec<ExecutionWrite>,
    pub events: Vec<ExecutionEvent>,
    pub canvas_commands: Vec<ExecutionCanvasCommand>,
    pub canvas_fill_batches: Vec<ExecutionCanvasFillBatch>,
}
