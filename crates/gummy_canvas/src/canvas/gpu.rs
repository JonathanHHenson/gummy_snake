use crate::*;

mod commands;
mod replay;
mod shapes;
mod sync;

impl Canvas {
    fn record_native_blend(&mut self, blend_mode: BlendMode) {
        if blend_mode != BlendMode::Blend {
            self.performance_counters.gpu_blend_commands += 1;
        }
    }

    fn record_native_text_draw(&mut self) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_text_commands += 1;
        self.mark_gpu_output_dirty();
    }

    fn record_native_triangle_draw(&mut self, blend_mode: BlendMode, vertex_count: usize) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_triangle_commands += 1;
        self.performance_counters.native_staged_primitive_vertices += vertex_count as u64;
        self.record_native_blend(blend_mode);
        self.mark_gpu_output_dirty();
    }

    fn record_native_ellipse_draw(&mut self, blend_mode: BlendMode) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_ellipse_commands += 1;
        self.record_native_blend(blend_mode);
        self.mark_gpu_output_dirty();
    }

    fn record_native_primitive_instance_draw(&mut self, blend_mode: BlendMode) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_primitive_instance_commands += 1;
        self.record_native_blend(blend_mode);
        self.mark_gpu_output_dirty();
    }

    fn record_native_erase_draw(&mut self, vertex_count: usize) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_erase_commands += 1;
        self.performance_counters.native_staged_primitive_vertices += vertex_count as u64;
        self.mark_gpu_output_dirty();
    }

    pub(crate) fn record_native_image_draw(&mut self, blend_mode: BlendMode, vertex_count: usize) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_image_commands += 1;
        self.performance_counters.native_staged_image_vertices += vertex_count as u64;
        self.record_native_blend(blend_mode);
        self.mark_gpu_output_texture_current();
    }

    pub(crate) fn record_native_model_draw(&mut self) {
        self.performance_counters.direct_model_draws += 1;
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_model_commands += 1;
        self.mark_gpu_output_texture_current();
    }

    pub(crate) fn record_native_model_batch_draw(&mut self, instance_count: usize) {
        self.performance_counters.direct_model_draws += instance_count as u64;
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_model_commands += 1;
        self.mark_gpu_output_texture_current();
    }

    pub(crate) fn record_native_region_effect_draw(&mut self, blend_command: bool) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.native_region_effect_commands += 1;
        if blend_command {
            self.performance_counters.gpu_blend_commands += 1;
        }
        self.performance_counters.gpu_region_effect_passes += 1;
        self.mark_gpu_output_dirty();
    }
}
