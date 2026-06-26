use crate::*;

mod commands;
mod replay;
mod shapes;
mod sync;

impl Canvas {
    fn record_native_draw(&mut self) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.mark_gpu_output_dirty();
    }

    fn record_native_draw_with_blend(&mut self, blend_mode: BlendMode) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        if blend_mode != BlendMode::Blend {
            self.performance_counters.gpu_blend_commands += 1;
        }
        self.mark_gpu_output_dirty();
    }

    fn record_native_region_effect_draw(&mut self) {
        self.performance_counters.gpu_draws += 1;
        self.performance_counters.native_draw_commands += 1;
        self.performance_counters.gpu_blend_commands += 1;
        self.performance_counters.gpu_region_effect_passes += 1;
        self.mark_gpu_output_dirty();
    }
}
