use crate::*;

impl Canvas {
    pub(crate) fn mark_gpu_output_dirty(&mut self) {
        self.render_dirty = true;
        self.offscreen_dirty = true;
        self.pixels_stale = true;
    }

    pub(crate) fn mark_gpu_output_texture_current(&mut self) {
        self.mark_gpu_output_dirty();
        self.texture_stale = false;
    }

    pub(crate) fn mark_cpu_pixels_uploaded(&mut self) {
        self.render_dirty = true;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = true;
    }

    pub(crate) fn mark_render_clean(&mut self) {
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = false;
        self.texture_stale = false;
    }

    pub(crate) fn mark_gpu_rendered_without_readback(&mut self) {
        self.render_dirty = false;
        self.offscreen_dirty = false;
        self.pixels_stale = true;
        self.texture_stale = false;
    }

    pub(crate) fn reset_render_sync_state(&mut self) {
        self.mark_render_clean();
        self.last_reusable_text_frame_signature = None;
        self.pending_reusable_text_frame_signature = None;
        self.cpu_compositing_active = false;
    }
}
