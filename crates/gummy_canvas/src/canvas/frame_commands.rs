use crate::canvas_state::Canvas;
use crate::frame_commands::{FrameCommandFamily, FRAME_COMMAND_ABI_VERSION};
use pyo3::prelude::*;
use pyo3::types::PyDict;

impl Canvas {
    pub(crate) fn begin_frame_command_generation(&mut self) {
        self.frame_command_recorder.begin_frame();
    }

    pub(crate) fn record_frame_command_ingress(
        &mut self,
        family: FrameCommandFamily,
        payloads: &[&[u8]],
        record_count: usize,
    ) {
        let byte_count = payloads.iter().map(|payload| payload.len()).sum::<usize>();
        if self
            .frame_command_recorder
            .record(family, payloads, record_count)
        {
            self.performance_counters.frame_command_storage_growths += 1;
        }
        self.performance_counters.typed_frame_command_batches += 1;
        self.performance_counters.typed_frame_command_records += record_count as u64;
        self.performance_counters.typed_frame_command_bytes += byte_count as u64;
        match family {
            FrameCommandFamily::Primitive => {
                self.performance_counters.typed_primitive_records += record_count as u64
            }
            FrameCommandFamily::Path => {
                self.performance_counters.typed_path_records += record_count as u64
            }
            FrameCommandFamily::Image => {
                self.performance_counters.typed_image_records += record_count as u64
            }
            FrameCommandFamily::Text => {
                self.performance_counters.typed_text_records += record_count as u64
            }
            FrameCommandFamily::Model => {
                self.performance_counters.typed_model_records += record_count as u64
            }
            FrameCommandFamily::Effect => {
                self.performance_counters.typed_effect_records += record_count as u64
            }
            FrameCommandFamily::Barrier => {
                self.performance_counters.typed_order_barriers += record_count as u64
            }
        }
    }

    pub(crate) fn frame_command_diagnostics_impl<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let diagnostics = PyDict::new_bound(py);
        diagnostics.set_item("abi_version", FRAME_COMMAND_ABI_VERSION)?;
        diagnostics.set_item("generation", self.frame_command_recorder.generation())?;
        diagnostics.set_item("storage_bytes", self.frame_command_recorder.storage_len())?;
        diagnostics.set_item(
            "storage_capacity_bytes",
            self.frame_command_recorder.storage_capacity(),
        )?;
        diagnostics.set_item("segments", self.frame_command_recorder.segments().len())?;
        diagnostics.set_item(
            "families",
            self.frame_command_recorder
                .segments()
                .iter()
                .map(|segment| segment.family.as_str())
                .collect::<Vec<_>>(),
        )?;
        diagnostics.set_item(
            "records",
            self.frame_command_recorder
                .segments()
                .iter()
                .map(|segment| segment.record_count)
                .sum::<usize>(),
        )?;
        diagnostics.set_item(
            "segment_bytes",
            self.frame_command_recorder
                .segments()
                .iter()
                .map(|segment| segment.byte_len)
                .sum::<usize>(),
        )?;
        diagnostics.set_item(
            "last_segment_offset",
            self.frame_command_recorder
                .segments()
                .last()
                .map(|segment| segment.offset),
        )?;
        Ok(diagnostics)
    }
}
