use std::collections::{BTreeSet, HashMap};
use std::ops::Range;
use std::sync::OnceLock;

use rayon::prelude::*;
use rayon::{ThreadPool, ThreadPoolBuilder};

use crate::error::{EcsError, Result};

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum AccessKey {
    Component(String),
    Resource(String),
    Event(String),
    Hidden(String),
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AccessSummary {
    pub reads: BTreeSet<AccessKey>,
    pub writes: BTreeSet<AccessKey>,
    pub structural: bool,
}

impl AccessSummary {
    pub fn conflicts_with(&self, other: &Self) -> bool {
        self.structural
            || other.structural
            || self
                .writes
                .iter()
                .any(|key| other.writes.contains(key) || other.reads.contains(key))
            || other.writes.iter().any(|key| self.reads.contains(key))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScheduledSystem {
    pub id: u64,
    pub name: String,
    pub order: i32,
    pub before: Vec<u64>,
    pub after: Vec<u64>,
    pub access: AccessSummary,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScheduleWave {
    pub systems: Vec<u64>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SchedulePlan {
    pub waves: Vec<ScheduleWave>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SchedulerOptions {
    pub worker_count: usize,
    pub force_single_thread: bool,
    pub chunk_threshold: usize,
    pub chunk_size: usize,
}

impl Default for SchedulerOptions {
    fn default() -> Self {
        Self {
            worker_count: ecs_worker_count(),
            force_single_thread: false,
            chunk_threshold: 4_096,
            chunk_size: 1_024,
        }
    }
}

static ECS_WORKER_POOL: OnceLock<std::result::Result<ThreadPool, String>> = OnceLock::new();

pub fn ecs_worker_count() -> usize {
    if let Some(count) = std::env::var_os("GUMMY_ECS_WORKERS")
        .and_then(|value| value.to_str().map(str::to_owned))
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|count| *count > 0)
    {
        return count;
    }
    let logical_cores = std::thread::available_parallelism().map_or(1, usize::from);
    logical_cores.saturating_sub(2).max(1).min(11)
}

pub(crate) fn install_on_ecs_worker_pool<R, F>(op: F) -> Result<R>
where
    R: Send,
    F: FnOnce() -> Result<R> + Send,
{
    let worker_count = ecs_worker_count();
    let pool_result = ECS_WORKER_POOL.get_or_init(|| {
        ThreadPoolBuilder::new()
            .num_threads(worker_count)
            .thread_name(|index| format!("gummy-ecs-{index}"))
            .build()
            .map_err(|err| err.to_string())
    });
    let pool = pool_result.as_ref().map_err(|err| {
        EcsError::InvalidSchedule(format!("failed to initialize ECS worker pool: {err}"))
    })?;
    pool.install(op)
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SchedulerDiagnostics {
    pub worker_count: usize,
    pub waves: usize,
    pub chunks: usize,
    pub sequential_conflict_fallbacks: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandBatch<C> {
    pub phase: i32,
    pub order: i32,
    pub system_id: u64,
    pub archetype: usize,
    pub chunk: usize,
    pub commands: Vec<C>,
}

pub fn build_deterministic_waves(systems: &[ScheduledSystem]) -> Result<SchedulePlan> {
    let by_id = systems
        .iter()
        .map(|system| (system.id, system))
        .collect::<HashMap<_, _>>();
    let mut incoming = systems
        .iter()
        .map(|system| (system.id, BTreeSet::new()))
        .collect::<HashMap<_, BTreeSet<u64>>>();
    let mut outgoing = incoming.clone();
    for system in systems {
        for target in &system.before {
            if !by_id.contains_key(target) {
                return Err(EcsError::InvalidSchedule(format!(
                    "unknown system {target}"
                )));
            }
            outgoing.entry(system.id).or_default().insert(*target);
            incoming.entry(*target).or_default().insert(system.id);
        }
        for source in &system.after {
            if !by_id.contains_key(source) {
                return Err(EcsError::InvalidSchedule(format!(
                    "unknown system {source}"
                )));
            }
            outgoing.entry(*source).or_default().insert(system.id);
            incoming.entry(system.id).or_default().insert(*source);
        }
    }

    let stable_key = |id: u64| {
        let system = by_id[&id];
        (system.order, system.id)
    };
    let mut ready = incoming
        .iter()
        .filter_map(|(id, deps)| deps.is_empty().then_some(*id))
        .collect::<Vec<_>>();
    ready.sort_by_key(|id| stable_key(*id));
    let mut remaining = systems.len();
    let mut waves = Vec::new();
    while !ready.is_empty() {
        let mut wave = Vec::new();
        let mut deferred = Vec::new();
        for id in ready.drain(..) {
            let system = by_id[&id];
            if wave
                .iter()
                .any(|other_id| by_id[other_id].access.conflicts_with(&system.access))
            {
                deferred.push(id);
            } else {
                wave.push(id);
            }
        }
        if wave.is_empty() {
            return Err(EcsError::InvalidSchedule(
                "schedule wave construction stalled".to_string(),
            ));
        }
        wave.sort_by_key(|id| stable_key(*id));
        remaining -= wave.len();
        for id in &wave {
            for target in outgoing
                .get(id)
                .into_iter()
                .flatten()
                .copied()
                .collect::<Vec<_>>()
            {
                if let Some(deps) = incoming.get_mut(&target) {
                    deps.remove(id);
                    if deps.is_empty() {
                        deferred.push(target);
                    }
                }
            }
        }
        deferred.sort_by_key(|id| stable_key(*id));
        deferred.dedup();
        ready = deferred;
        waves.push(ScheduleWave { systems: wave });
    }
    if remaining != 0 {
        return Err(EcsError::InvalidSchedule(
            "ECS system dependency cycle detected".to_string(),
        ));
    }
    Ok(SchedulePlan { waves })
}

pub fn execute_deterministic_waves<R, F>(
    systems: &[ScheduledSystem],
    options: SchedulerOptions,
    run: F,
) -> Result<(Vec<(u64, R)>, SchedulerDiagnostics)>
where
    R: Send,
    F: Fn(u64) -> R + Sync,
{
    let plan = build_deterministic_waves(systems)?;
    let worker_count = if options.force_single_thread {
        1
    } else {
        options.worker_count.max(1)
    };
    let mut diagnostics = SchedulerDiagnostics {
        worker_count,
        waves: plan.waves.len(),
        chunks: 0,
        sequential_conflict_fallbacks: 0,
    };
    let mut output = Vec::new();
    if worker_count == 1 {
        for wave in plan.waves {
            if wave.systems.len() > 1 {
                diagnostics.sequential_conflict_fallbacks += 1;
            }
            for id in wave.systems {
                output.push((id, run(id)));
            }
        }
        return Ok((output, diagnostics));
    }

    let pool = ThreadPoolBuilder::new()
        .num_threads(worker_count)
        .build()
        .map_err(|err| EcsError::InvalidSchedule(err.to_string()))?;
    for wave in plan.waves {
        let mut results = pool.install(|| {
            wave.systems
                .par_iter()
                .map(|id| (*id, run(*id)))
                .collect::<Vec<_>>()
        });
        let order = wave
            .systems
            .iter()
            .enumerate()
            .map(|(index, id)| (*id, index))
            .collect::<HashMap<_, _>>();
        results.sort_by_key(|(id, _)| order[id]);
        output.extend(results);
    }
    Ok((output, diagnostics))
}

pub fn deterministic_chunks(
    rows: usize,
    chunk_threshold: usize,
    chunk_size: usize,
) -> Vec<Range<usize>> {
    if rows == 0 {
        return Vec::new();
    }
    if rows < chunk_threshold || chunk_size == 0 {
        return std::iter::once(0..rows).collect();
    }
    let mut chunks = Vec::new();
    let mut start = 0;
    while start < rows {
        let end = (start + chunk_size).min(rows);
        chunks.push(start..end);
        start = end;
    }
    chunks
}

pub fn merge_command_batches_stably<C>(
    batches: impl IntoIterator<Item = CommandBatch<C>>,
) -> Vec<C> {
    let mut batches = batches.into_iter().collect::<Vec<_>>();
    batches.sort_by_key(|batch| {
        (
            batch.phase,
            batch.order,
            batch.system_id,
            batch.archetype,
            batch.chunk,
        )
    });
    batches
        .into_iter()
        .flat_map(|batch| batch.commands)
        .collect::<Vec<_>>()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn system(id: u64, order: i32, access: AccessSummary) -> ScheduledSystem {
        ScheduledSystem {
            id,
            name: format!("s{id}"),
            order,
            before: Vec::new(),
            after: Vec::new(),
            access,
        }
    }

    #[test]
    fn scheduler_groups_non_conflicting_systems_and_splits_writes() {
        let mut write_a = AccessSummary::default();
        write_a.writes.insert(AccessKey::Component("A".to_string()));
        let mut read_b = AccessSummary::default();
        read_b.reads.insert(AccessKey::Component("B".to_string()));
        let mut read_a = AccessSummary::default();
        read_a.reads.insert(AccessKey::Component("A".to_string()));
        let plan = build_deterministic_waves(&[
            system(1, 0, write_a),
            system(2, 0, read_b),
            system(3, 0, read_a),
        ])
        .unwrap();
        assert_eq!(plan.waves[0].systems, vec![1, 2]);
        assert_eq!(plan.waves[1].systems, vec![3]);
    }

    #[test]
    fn default_worker_count_reserves_main_and_window_threads() {
        let logical_cores = std::thread::available_parallelism().map_or(1, usize::from);
        let expected = logical_cores.saturating_sub(2).max(1).min(11);
        assert_eq!(ecs_worker_count(), expected);
        assert_eq!(SchedulerOptions::default().worker_count, expected);
    }

    #[test]
    fn parallel_wave_execution_matches_forced_single_thread_order() {
        let systems = [
            system(3, 0, AccessSummary::default()),
            system(1, 0, AccessSummary::default()),
            system(2, 0, AccessSummary::default()),
        ];
        let single = execute_deterministic_waves(
            &systems,
            SchedulerOptions {
                force_single_thread: true,
                ..SchedulerOptions::default()
            },
            |id| id * 10,
        )
        .unwrap()
        .0;
        let parallel = execute_deterministic_waves(
            &systems,
            SchedulerOptions {
                worker_count: 2,
                ..SchedulerOptions::default()
            },
            |id| id * 10,
        )
        .unwrap()
        .0;
        assert_eq!(single, parallel);
        assert_eq!(parallel, vec![(1, 10), (2, 20), (3, 30)]);
    }

    #[test]
    fn chunking_and_command_merge_are_stable() {
        assert_eq!(deterministic_chunks(5, 4, 2), vec![0..2, 2..4, 4..5]);
        assert_eq!(deterministic_chunks(3, 4, 2), vec![0..3]);
        let merged = merge_command_batches_stably([
            CommandBatch {
                phase: 0,
                order: 0,
                system_id: 2,
                archetype: 0,
                chunk: 0,
                commands: vec!["late"],
            },
            CommandBatch {
                phase: 0,
                order: 0,
                system_id: 1,
                archetype: 0,
                chunk: 1,
                commands: vec!["second"],
            },
            CommandBatch {
                phase: 0,
                order: 0,
                system_id: 1,
                archetype: 0,
                chunk: 0,
                commands: vec!["first"],
            },
        ]);
        assert_eq!(merged, vec!["first", "second", "late"]);
    }
}
