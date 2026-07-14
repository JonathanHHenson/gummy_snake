use std::collections::{HashMap, VecDeque};

use crate::column::EcsValue;
use crate::error::{EcsError, Result};
use crate::schema::ComponentId;

pub const DEFAULT_EVENT_QUEUE_CAPACITY: usize = 65_536;

#[derive(Debug, Clone, PartialEq)]
pub struct EventRecord {
    pub frame: u64,
    pub sequence: u64,
    pub payload: EcsValue,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct EventReaderCursor {
    pub next_sequence: u64,
}

#[derive(Debug, Clone, PartialEq)]
struct EventQueue {
    schema: Option<ComponentId>,
    records: VecDeque<EventRecord>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EventStore {
    queues: HashMap<String, EventQueue>,
    next_sequence: u64,
    retention_frames: u64,
    queue_capacity: usize,
    dropped_records: usize,
}

impl Default for EventStore {
    fn default() -> Self {
        Self {
            queues: HashMap::new(),
            next_sequence: 0,
            retention_frames: 1,
            queue_capacity: DEFAULT_EVENT_QUEUE_CAPACITY,
            dropped_records: 0,
        }
    }
}

impl EventStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_retention_frames(&mut self, frames: u64) {
        self.retention_frames = frames.max(1);
    }

    pub fn set_queue_capacity(&mut self, records: usize) {
        self.queue_capacity = records.max(1);
        for queue in self.queues.values_mut() {
            while queue.records.len() > self.queue_capacity {
                queue.records.pop_front();
                self.dropped_records += 1;
            }
        }
    }

    pub fn emit(
        &mut self,
        event_type: impl Into<String>,
        schema: Option<ComponentId>,
        frame: u64,
        payload: EcsValue,
    ) {
        let sequence = self.next_sequence;
        self.next_sequence = self.next_sequence.wrapping_add(1);
        let queue = self
            .queues
            .entry(event_type.into())
            .or_insert_with(|| EventQueue {
                schema,
                records: VecDeque::new(),
            });
        debug_assert!(queue.schema == schema || queue.schema.is_none() || schema.is_none());
        if queue.records.len() == self.queue_capacity {
            queue.records.pop_front();
            self.dropped_records += 1;
        }
        queue.records.push_back(EventRecord {
            frame,
            sequence,
            payload,
        });
    }

    /// Materialize records for an explicit external boundary.
    pub fn read(&self, event_type: &str) -> Vec<EventRecord> {
        self.queues
            .get(event_type)
            .map(|queue| queue.records.iter().cloned().collect())
            .unwrap_or_default()
    }

    pub fn read_since(&self, event_type: &str, cursor: &mut EventReaderCursor) -> Vec<EventRecord> {
        let records = self
            .queues
            .get(event_type)
            .map(|queue| {
                queue
                    .records
                    .iter()
                    .filter(|record| record.sequence >= cursor.next_sequence)
                    .cloned()
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        if let Some(last) = records.last() {
            cursor.next_sequence = last.sequence.wrapping_add(1);
        }
        records
    }

    pub fn payloads(&self, event_type: &str) -> impl Iterator<Item = &EcsValue> {
        self.queues
            .get(event_type)
            .into_iter()
            .flat_map(|queue| queue.records.iter().map(|record| &record.payload))
    }

    pub fn sum_numeric_payload_field(&self, event_type: &str, field: &str) -> Result<(usize, f64)> {
        let Some(events) = self.queues.get(event_type) else {
            return Ok((0, 0.0));
        };
        let mut sum = 0.0;
        for event in &events.records {
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
                EcsValue::Bool(value) => usize::from(*value) as f64,
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
        Ok((events.records.len(), sum))
    }

    pub fn clear(&mut self, event_type: Option<&str>) -> usize {
        if let Some(event_type) = event_type {
            self.queues
                .remove(event_type)
                .map_or(0, |queue| queue.records.len())
        } else {
            let removed = self.record_count();
            self.queues.clear();
            removed
        }
    }

    pub fn begin_frame(&mut self, frame: u64) -> usize {
        let before = self.record_count();
        let min_frame = frame.saturating_sub(self.retention_frames);
        self.queues.retain(|_, queue| {
            while queue
                .records
                .front()
                .is_some_and(|event| event.frame < min_frame)
            {
                queue.records.pop_front();
            }
            !queue.records.is_empty()
        });
        before - self.record_count()
    }

    pub fn queue_len(&self, event_type: &str) -> usize {
        self.queues
            .get(event_type)
            .map_or(0, |queue| queue.records.len())
    }

    pub fn queue_count(&self) -> usize {
        self.queues.len()
    }

    pub fn record_count(&self) -> usize {
        self.queues.values().map(|queue| queue.records.len()).sum()
    }

    pub fn dropped_records(&self) -> usize {
        self.dropped_records
    }

    pub fn reset_diagnostic_counters(&mut self) {
        self.dropped_records = 0;
    }

    pub fn estimated_bytes(&self) -> usize {
        self.queues
            .iter()
            .map(|(name, queue)| {
                name.capacity() + queue.records.capacity() * std::mem::size_of::<EventRecord>()
            })
            .sum()
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
    fn event_store_orders_retains_and_cursors_without_queue_clones() {
        let mut events = EventStore::new();
        events.emit("Ping", None, 0, EcsValue::I64(1));
        events.emit("Ping", None, 1, EcsValue::I64(2));
        assert_eq!(events.payloads("Ping").count(), 2);
        let mut cursor = EventReaderCursor::default();
        assert_eq!(events.read_since("Ping", &mut cursor).len(), 2);
        assert!(events.read_since("Ping", &mut cursor).is_empty());
        events.begin_frame(2);
        let read = events.read("Ping");
        assert_eq!(read.len(), 1);
        assert_eq!(read[0].payload, EcsValue::I64(2));
    }

    #[test]
    fn event_ring_is_bounded_and_reports_drops() {
        let mut events = EventStore::new();
        events.set_queue_capacity(2);
        for value in 0..3 {
            events.emit("Ping", None, 0, EcsValue::I64(value));
        }
        assert_eq!(events.queue_len("Ping"), 2);
        assert_eq!(events.dropped_records(), 1);
        assert_eq!(events.read("Ping")[0].payload, EcsValue::I64(1));
    }
}
