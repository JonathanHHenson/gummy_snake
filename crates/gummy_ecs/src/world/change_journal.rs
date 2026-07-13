use std::collections::{BTreeMap, HashMap};

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
    ComponentAdded { component: String },
    ComponentRemoved { component: String },
    FieldChanged { component: String, field: String },
    TagAdded { tag: String },
    TagRemoved { tag: String },
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
    pub changed_fields: BTreeMap<String, ChangeRevision>,
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
    pub components: BTreeMap<String, ComponentChange>,
    pub tags: BTreeMap<String, TagChange>,
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
/// mutations in the active epoch while revisions remain monotonic. Query
/// filtering consumes the compact summaries directly for Added/Changed/Removed
/// component terms, without Python-owned allowed-entity transport.
#[derive(Debug, Clone, Default)]
pub struct ChangeJournal {
    current_epoch: ChangeEpoch,
    latest_revision: ChangeRevision,
    diagnostic_updates: usize,
    records: Vec<ChangeRecord>,
    changes: HashMap<(ChangeEpoch, Entity), EntityChange>,
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

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
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
            self.records.clear();
            self.changes.clear();
        }
    }

    pub(crate) fn record(&mut self, entity: Entity, kind: ChangeKind) -> ChangeRevision {
        self.latest_revision = ChangeRevision(self.latest_revision.0.saturating_add(1));
        self.diagnostic_updates = self.diagnostic_updates.saturating_add(1);
        let revision = self.latest_revision;
        let epoch = self.current_epoch;
        let record = ChangeRecord {
            epoch,
            revision,
            entity,
            kind,
        };
        self.update_change_summary(&record);
        self.records.push(record);
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
                change
                    .components
                    .entry(component.clone())
                    .or_default()
                    .changed_fields
                    .insert(field.clone(), record.revision);
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
                .changed_fields
                .values()
                .any(|changed| self.removed.is_none_or(|removed| *changed > removed))
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
                component: "Position".to_string(),
            },
        );
        journal.record(
            entity,
            ChangeKind::FieldChanged {
                component: "Position".to_string(),
                field: "x".to_string(),
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
