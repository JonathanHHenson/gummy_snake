use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;

use crate::entity::Entity;

/// A frame epoch used to group ECS mutations for change-filter evaluation.
///
/// Epochs are assigned by the world host through [`crate::World::set_frame`]. They
/// are values rather than implicit counters so a host may restore or replay a
/// frame without changing its existing frame-number behavior.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ChangeEpoch(u64);

impl ChangeEpoch {
    pub const fn new(value: u64) -> Self {
        Self(value)
    }

    pub const fn get(self) -> u64 {
        self.0
    }
}

/// A monotonically increasing revision assigned to every recorded mutation.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ChangeRevision(u64);

impl ChangeRevision {
    pub const fn get(self) -> u64 {
        self.0
    }
}

/// A structural or field mutation recorded by the Rust-owned change journal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ChangeKind {
    Spawned,
    Despawned,
    ComponentAdded {
        component: Arc<str>,
    },
    ComponentRemoved {
        component: Arc<str>,
    },
    FieldChanged {
        component: Arc<str>,
        field: Arc<str>,
    },
    TagAdded {
        tag: Arc<str>,
    },
    TagRemoved {
        tag: Arc<str>,
    },
}

/// An ordered mutation record. `entity` includes its generation, so a reused
/// entity index cannot inherit the change state of its previous occupant.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChangeRecord {
    pub epoch: ChangeEpoch,
    pub revision: ChangeRevision,
    pub entity: Entity,
    pub kind: ChangeKind,
}

/// The latest component transitions for one entity within one epoch.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ComponentChange {
    pub added: Option<ChangeRevision>,
    pub removed: Option<ChangeRevision>,
    pub changed: Option<ChangeRevision>,
    pub changed_fields: BTreeMap<Arc<str>, ChangeRevision>,
}

/// The latest tag transitions for one entity within one epoch.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct TagChange {
    pub added: Option<ChangeRevision>,
    pub removed: Option<ChangeRevision>,
}

/// Per-entity summary of changes recorded during one epoch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EntityChange {
    pub epoch: ChangeEpoch,
    pub entity: Entity,
    pub spawned: Option<ChangeRevision>,
    pub despawned: Option<ChangeRevision>,
    pub components: BTreeMap<Arc<str>, ComponentChange>,
    pub tags: BTreeMap<Arc<str>, TagChange>,
}

impl EntityChange {
    fn new(epoch: ChangeEpoch, entity: Entity) -> Self {
        Self {
            epoch,
            entity,
            spawned: None,
            despawned: None,
            components: BTreeMap::new(),
            tags: BTreeMap::new(),
        }
    }
}

/// Rust-owned mutation history and per-epoch change index for a [`crate::World`].
///
/// The journal retains only the active epoch. Advancing to a different epoch
/// discards completed-epoch records and summaries, bounding retained memory by
/// mutations in the active epoch while revisions remain monotonic. Query filtering
/// consumes the compact summaries directly for Added/Changed/Removed component terms,
/// without Python-owned allowed-entity transport.
#[derive(Debug, Clone)]
pub struct ChangeJournal {
    current_epoch: ChangeEpoch,
    latest_revision: ChangeRevision,
    diagnostic_updates: usize,
    retained_records: usize,
    detailed_records: bool,
    summary_batch: Option<HashMap<Arc<str>, Vec<Option<u32>>>>,
    records: Vec<ChangeRecord>,
    changes: HashMap<(ChangeEpoch, Entity), EntityChange>,
}

impl Default for ChangeJournal {
    fn default() -> Self {
        Self {
            current_epoch: ChangeEpoch::default(),
            latest_revision: ChangeRevision::default(),
            diagnostic_updates: 0,
            retained_records: 0,
            detailed_records: true,
            summary_batch: None,
            records: Vec::new(),
            changes: HashMap::new(),
        }
    }
}

impl ChangeJournal {
    pub fn current_epoch(&self) -> ChangeEpoch {
        self.current_epoch
    }

    pub fn latest_revision(&self) -> ChangeRevision {
        self.latest_revision
    }

    pub(crate) fn diagnostic_updates(&self) -> usize {
        self.diagnostic_updates
    }

    pub(crate) fn reset_diagnostic_counters(&mut self) {
        self.diagnostic_updates = 0;
    }

    pub(crate) fn set_detailed_records(&mut self, enabled: bool) {
        self.detailed_records = enabled;
        self.summary_batch = None;
        if !enabled {
            self.records.clear();
        }
    }

    pub(crate) fn begin_summary_batch(&mut self) {
        if !self.detailed_records {
            self.summary_batch = Some(HashMap::new());
        }
    }

    pub(crate) fn end_summary_batch(&mut self) {
        let Some(batch) = self.summary_batch.take() else {
            return;
        };
        let revision = self.latest_revision;
        let epoch = self.current_epoch;
        for (component, generations) in batch {
            for (index, generation) in generations.into_iter().enumerate() {
                let Some(generation) = generation else {
                    continue;
                };
                let entity = Entity {
                    index: index as u32,
                    generation,
                };
                self.changes
                    .entry((epoch, entity))
                    .or_insert_with(|| EntityChange::new(epoch, entity))
                    .components
                    .entry(component.clone())
                    .or_default()
                    .changed = Some(revision);
            }
        }
    }

    pub fn len(&self) -> usize {
        self.retained_records
    }

    pub fn is_empty(&self) -> bool {
        self.retained_records == 0
    }

    pub fn records(&self) -> &[ChangeRecord] {
        &self.records
    }

    pub fn records_for_epoch(&self, epoch: ChangeEpoch) -> impl Iterator<Item = &ChangeRecord> {
        self.records
            .iter()
            .filter(move |record| record.epoch == epoch)
    }

    pub fn entity_change(&self, epoch: ChangeEpoch, entity: Entity) -> Option<&EntityChange> {
        self.changes.get(&(epoch, entity))
    }

    pub(crate) fn set_epoch(&mut self, epoch: u64) {
        let epoch = ChangeEpoch::new(epoch);
        if self.current_epoch != epoch {
            self.current_epoch = epoch;
            self.retained_records = 0;
            self.summary_batch = None;
            self.records.clear();
            self.changes.clear();
        }
    }

    pub(crate) fn record_field_changes(
        &mut self,
        component: Arc<str>,
        field: Arc<str>,
        entities: &[Entity],
    ) {
        if entities.is_empty() {
            return;
        }
        if self.detailed_records || self.summary_batch.is_none() {
            for entity in entities.iter().copied() {
                self.record(
                    entity,
                    ChangeKind::FieldChanged {
                        component: component.clone(),
                        field: field.clone(),
                    },
                );
            }
            return;
        }

        let count = entities.len() as u64;
        self.latest_revision = ChangeRevision(self.latest_revision.0.saturating_add(count));
        self.diagnostic_updates = self.diagnostic_updates.saturating_add(entities.len());
        self.retained_records = self.retained_records.saturating_add(entities.len());
        let batch = self
            .summary_batch
            .as_mut()
            .expect("summary batch checked above");
        let generations = if let Some(generations) = batch.get_mut(component.as_ref()) {
            generations
        } else {
            batch.insert(component.clone(), Vec::new());
            batch
                .get_mut(component.as_ref())
                .expect("inserted summary component")
        };
        for entity in entities.iter().copied() {
            let index = entity.index as usize;
            if generations.len() <= index {
                generations.resize(index + 1, None);
            }
            generations[index] = Some(entity.generation);
        }
    }

    pub(crate) fn record(&mut self, entity: Entity, kind: ChangeKind) -> ChangeRevision {
        self.latest_revision = ChangeRevision(self.latest_revision.0.saturating_add(1));
        self.diagnostic_updates = self.diagnostic_updates.saturating_add(1);
        self.retained_records = self.retained_records.saturating_add(1);
        let revision = self.latest_revision;
        if !self.detailed_records {
            if let ChangeKind::FieldChanged { component, .. } = &kind {
                if let Some(batch) = self.summary_batch.as_mut() {
                    let generations = if let Some(generations) = batch.get_mut(component.as_ref()) {
                        generations
                    } else {
                        batch.insert(component.clone(), Vec::new());
                        batch
                            .get_mut(component.as_ref())
                            .expect("inserted summary component")
                    };
                    let index = entity.index as usize;
                    if generations.len() <= index {
                        generations.resize(index + 1, None);
                    }
                    generations[index] = Some(entity.generation);
                    return revision;
                }
            }
        }
        let epoch = self.current_epoch;
        let record = ChangeRecord {
            epoch,
            revision,
            entity,
            kind,
        };
        self.update_change_summary(&record);
        if self.detailed_records {
            self.records.push(record);
        }
        revision
    }

    fn update_change_summary(&mut self, record: &ChangeRecord) {
        let change = self
            .changes
            .entry((record.epoch, record.entity))
            .or_insert_with(|| EntityChange::new(record.epoch, record.entity));
        match &record.kind {
            ChangeKind::Spawned => change.spawned = Some(record.revision),
            ChangeKind::Despawned => change.despawned = Some(record.revision),
            ChangeKind::ComponentAdded { component } => {
                change
                    .components
                    .entry(component.clone())
                    .or_default()
                    .added = Some(record.revision);
            }
            ChangeKind::ComponentRemoved { component } => {
                change
                    .components
                    .entry(component.clone())
                    .or_default()
                    .removed = Some(record.revision);
            }
            ChangeKind::FieldChanged { component, field } => {
                let component_change = change.components.entry(component.clone()).or_default();
                component_change.changed = Some(record.revision);
                if self.detailed_records {
                    component_change
                        .changed_fields
                        .insert(field.clone(), record.revision);
                }
            }
            ChangeKind::TagAdded { tag } => {
                change.tags.entry(tag.clone()).or_default().added = Some(record.revision);
            }
            ChangeKind::TagRemoved { tag } => {
                change.tags.entry(tag.clone()).or_default().removed = Some(record.revision);
            }
        }
    }
}

impl ComponentChange {
    /// Whether the component's final structural transition in this epoch is an add.
    pub(crate) fn is_currently_added(&self) -> bool {
        self.added
            .is_some_and(|added| self.removed.is_none_or(|removed| added > removed))
    }

    /// Whether the component's final structural transition in this epoch is a removal.
    pub(crate) fn is_currently_removed(&self) -> bool {
        self.removed
            .is_some_and(|removed| self.added.is_none_or(|added| removed > added))
    }

    /// Whether the component changed while present at the end of this epoch.
    /// A final add is itself a change; field writes before a later removal are not.
    pub(crate) fn is_currently_changed(&self) -> bool {
        self.is_currently_added()
            || self
                .changed
                .is_some_and(|changed| self.removed.is_none_or(|removed| changed > removed))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn journal_orders_revisions_and_summarizes_an_entity_epoch() {
        let entity = Entity {
            index: 4,
            generation: 2,
        };
        let mut journal = ChangeJournal::default();
        journal.set_epoch(7);
        journal.record(entity, ChangeKind::Spawned);
        journal.record(
            entity,
            ChangeKind::ComponentAdded {
                component: Arc::from("Position"),
            },
        );
        journal.record(
            entity,
            ChangeKind::FieldChanged {
                component: Arc::from("Position"),
                field: Arc::from("x"),
            },
        );

        assert_eq!(journal.latest_revision().get(), 3);
        assert_eq!(journal.records()[2].epoch, ChangeEpoch::new(7));
        let change = journal
            .entity_change(ChangeEpoch::new(7), entity)
            .expect("entity change summary");
        assert_eq!(change.spawned.unwrap().get(), 1);
        assert_eq!(change.components["Position"].changed_fields["x"].get(), 3);
    }

    #[test]
    fn summary_only_journal_preserves_change_filters_without_detailed_records() {
        let entity = Entity {
            index: 8,
            generation: 3,
        };
        let mut journal = ChangeJournal::default();
        journal.set_detailed_records(false);
        journal.set_epoch(4);
        journal.begin_summary_batch();
        for field in ["x", "y"] {
            journal.record_field_changes(Arc::from("Position"), Arc::from(field), &[entity]);
        }
        assert!(journal.entity_change(ChangeEpoch::new(4), entity).is_none());
        journal.end_summary_batch();

        assert_eq!(journal.len(), 2);
        assert!(journal.records().is_empty());
        let change = journal
            .entity_change(ChangeEpoch::new(4), entity)
            .expect("summary-only entity change");
        let component = &change.components["Position"];
        assert_eq!(component.changed.expect("component change").get(), 2);
        assert!(component.changed_fields.is_empty());
        assert!(component.is_currently_changed());

        journal.set_epoch(5);
        assert!(journal.is_empty());
        assert!(journal.entity_change(ChangeEpoch::new(4), entity).is_none());
    }

    #[test]
    fn journal_keeps_generation_reuses_and_epochs_distinct() {
        let old = Entity {
            index: 1,
            generation: 0,
        };
        let reused = Entity {
            index: 1,
            generation: 1,
        };
        let mut journal = ChangeJournal::default();
        journal.record(old, ChangeKind::Despawned);
        journal.set_epoch(1);
        journal.record(reused, ChangeKind::Spawned);

        assert!(journal.entity_change(ChangeEpoch::new(0), reused).is_none());
        assert!(journal.entity_change(ChangeEpoch::new(1), old).is_none());
        assert_eq!(
            journal
                .records_for_epoch(ChangeEpoch::new(1))
                .map(|record| record.entity)
                .collect::<Vec<_>>(),
            vec![reused]
        );
    }
}
