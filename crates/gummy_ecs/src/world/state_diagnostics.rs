use crate::column::EcsValue;
use crate::diagnostics::Diagnostics;

use super::World;

impl World {
    pub fn structural_revision(&self) -> u64 {
        self.structural_revision
    }

    pub fn field_revision(&self) -> u64 {
        self.field_revision
    }

    pub fn component_field_revision(&self, component: &str, field: &str) -> u64 {
        self.field_revisions
            .get(&(component.to_string(), field.to_string()))
            .copied()
            .unwrap_or(0)
    }

    pub fn set_input_state(&mut self, name: impl Into<String>, code: Option<i64>, value: EcsValue) {
        self.input_states.insert((name.into(), code), value);
    }

    pub(crate) fn input_state(&self, name: &str, code: Option<i64>) -> Option<EcsValue> {
        self.input_states.get(&(name.to_string(), code)).cloned()
    }

    pub fn archetype_count(&self) -> usize {
        self.archetypes.len()
    }

    pub fn staged_command_count(&self) -> usize {
        self.staged.len()
    }

    pub fn diagnostics(&self) -> Diagnostics {
        let mut diagnostics = self.diagnostics.clone();
        diagnostics.entities_alive = self.entities.alive_count();
        diagnostics.entity_generation_reuses = self.entities.generation_reuses();
        diagnostics.component_schemas_total = self.schemas.len();
        diagnostics.archetypes_total = self.archetypes.len();
        diagnostics.resources_total = self.resources.len();
        diagnostics.event_queues_total = self.events.queue_count();
        diagnostics
    }

    pub fn reset_diagnostics(&mut self) {
        self.diagnostics = Diagnostics::default();
    }

    pub(super) fn note_structural_revision(&mut self) {
        self.structural_revision = self.structural_revision.saturating_add(1);
        self.invalidate_query_cache();
    }

    pub(super) fn note_field_revision(&mut self, component: &str, field: &str) {
        self.note_field_revision_by(component, field, 1);
    }

    pub(super) fn note_field_revision_by(&mut self, component: &str, field: &str, count: u64) {
        if count == 0 {
            return;
        }
        self.field_revision = self.field_revision.saturating_add(count);
        let key = (component.to_string(), field.to_string());
        let revision = self.field_revisions.entry(key).or_default();
        *revision = revision.saturating_add(count);
    }
}
