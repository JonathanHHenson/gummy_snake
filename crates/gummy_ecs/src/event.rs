use std::collections::HashMap;

use crate::column::EcsValue;
use crate::error::{EcsError, Result};

#[derive(Debug, Clone, PartialEq)]
pub struct EventRecord {
    pub frame: u64,
    pub sequence: u64,
    pub payload: EcsValue,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EventStore {
    queues: HashMap<String, Vec<EventRecord>>,
    next_sequence: u64,
    retention_frames: u64,
}

impl Default for EventStore {
    fn default() -> Self {
        Self {
            queues: HashMap::new(),
            next_sequence: 0,
            retention_frames: 1,
        }
    }
}

impl EventStore {
    pub fn new() -> Self {
        Self {
            queues: HashMap::new(),
            next_sequence: 0,
            retention_frames: 1,
        }
    }

    pub fn set_retention_frames(&mut self, frames: u64) {
        self.retention_frames = frames.max(1);
    }

    pub fn emit(&mut self, event_type: impl Into<String>, frame: u64, payload: EcsValue) {
        let sequence = self.next_sequence;
        self.next_sequence = self.next_sequence.wrapping_add(1);
        self.queues
            .entry(event_type.into())
            .or_default()
            .push(EventRecord {
                frame,
                sequence,
                payload,
            });
    }

    pub fn read(&self, event_type: &str) -> Vec<EventRecord> {
        self.queues.get(event_type).cloned().unwrap_or_default()
    }

    pub fn sum_numeric_payload_field(&self, event_type: &str, field: &str) -> Result<(usize, f64)> {
        let Some(events) = self.queues.get(event_type) else {
            return Ok((0, 0.0));
        };
        let mut sum = 0.0;
        for event in events {
            let EcsValue::Struct(fields) = &event.payload else {
                return Err(EcsError::InvalidPlan(format!(
                    "event payload for '{event_type}' must be a struct to read field '{field}'"
                )));
            };
            let value = fields.get(field).ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "event payload for '{event_type}' has no field '{field}'"
                ))
            })?;
            sum += match value {
                EcsValue::Bool(value) => {
                    if *value {
                        1.0
                    } else {
                        0.0
                    }
                }
                EcsValue::I64(value) => *value as f64,
                EcsValue::U64(value) => *value as f64,
                EcsValue::F64(value) => *value,
                other => {
                    return Err(EcsError::InvalidPlan(format!(
                        "event field '{field}' must be numeric, got {}",
                        other.kind_name()
                    )));
                }
            };
        }
        Ok((events.len(), sum))
    }

    pub fn clear(&mut self, event_type: Option<&str>) {
        if let Some(event_type) = event_type {
            self.queues.remove(event_type);
        } else {
            self.queues.clear();
        }
    }

    pub fn begin_frame(&mut self, frame: u64) {
        let min_frame = frame.saturating_sub(self.retention_frames);
        self.queues.retain(|_, events| {
            events.retain(|event| event.frame >= min_frame);
            !events.is_empty()
        });
    }

    pub fn queue_len(&self, event_type: &str) -> usize {
        self.queues.get(event_type).map_or(0, Vec::len)
    }

    pub fn queue_count(&self) -> usize {
        self.queues.len()
    }

    pub fn validate_type(&self, event_type: &str) -> Result<()> {
        if event_type.is_empty() {
            return Err(EcsError::InvalidEventType);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn event_store_orders_and_retains_frames() {
        let mut events = EventStore::new();
        events.emit("Ping", 0, EcsValue::I64(1));
        events.emit("Ping", 1, EcsValue::I64(2));
        assert_eq!(events.read("Ping").len(), 2);
        events.begin_frame(2);
        let read = events.read("Ping");
        assert_eq!(read.len(), 1);
        assert_eq!(read[0].payload, EcsValue::I64(2));
    }
}
