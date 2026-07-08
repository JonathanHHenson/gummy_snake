use crate::archetype::ComponentRow;
use crate::column::EcsValue;
use crate::error::Result;
use crate::event::EventRecord;

use super::World;

impl World {
    pub fn insert_resource(&mut self, name: impl Into<String>, value: ComponentRow) -> Result<()> {
        let name = name.into();
        let value = self.coerce_component_row(&name, value)?;
        self.resources.insert(&self.schemas, name, value)
    }

    pub fn remove_resource(&mut self, name: &str) -> Result<ComponentRow> {
        self.resources.remove(name)
    }

    pub fn resource_field(&self, name: &str, field: &str) -> Result<EcsValue> {
        self.resources.get_field(name, field)
    }

    pub fn set_resource_field(&mut self, name: &str, field: &str, value: EcsValue) -> Result<()> {
        let value = self.coerce_value_for_component_field(name, field, value)?;
        self.resources.set_field(name, field, value)
    }

    pub fn has_resource(&self, name: &str) -> bool {
        self.resources.contains(name)
    }

    pub fn resource_count(&self) -> usize {
        self.resources.len()
    }

    pub fn resource_revision(&self, name: &str) -> u64 {
        self.resources.revision(name)
    }

    pub fn set_frame(&mut self, frame: u64) {
        self.current_frame = frame;
        self.events.begin_frame(frame);
    }

    pub fn emit_event(&mut self, event_type: &str, payload: EcsValue) -> Result<()> {
        self.events.validate_type(event_type)?;
        self.events.emit(event_type, self.current_frame, payload);
        Ok(())
    }

    pub fn read_events(&self, event_type: &str) -> Result<Vec<EventRecord>> {
        self.events.validate_type(event_type)?;
        Ok(self.events.read(event_type))
    }

    pub fn sum_event_numeric_payload_field(
        &self,
        event_type: &str,
        field: &str,
    ) -> Result<(usize, f64)> {
        self.events.validate_type(event_type)?;
        self.events.sum_numeric_payload_field(event_type, field)
    }

    pub fn clear_events(&mut self, event_type: Option<&str>) {
        self.events.clear(event_type);
    }

    pub fn event_queue_len(&self, event_type: &str) -> usize {
        self.events.queue_len(event_type)
    }
}
