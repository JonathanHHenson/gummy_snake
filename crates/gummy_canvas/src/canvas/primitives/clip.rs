use crate::*;

impl Canvas {
    pub(super) fn upload_current_clip_mask(&mut self) {
        let Some(gpu) = self.gpu.as_mut() else {
            return;
        };
        let Some(mask) = self.clip_masks.last() else {
            gpu.clear_clip_mask();
            return;
        };
        let bounds = self.clip_bounds.last().copied().unwrap_or((
            0,
            0,
            self.physical_width,
            self.physical_height,
        ));
        let width = bounds.2.saturating_sub(bounds.0).max(1);
        let height = bounds.3.saturating_sub(bounds.1).max(1);
        let mut rgba = vec![0_u8; width * height * 4];
        for y in bounds.1..bounds.3 {
            let source_row = y * self.physical_width;
            let dest_row = (y - bounds.1) * width;
            for x in bounds.0..bounds.2 {
                if mask[source_row + x] {
                    let offset = (dest_row + x - bounds.0) * 4;
                    rgba[offset..offset + 4].fill(255);
                }
            }
        }
        gpu.set_clip_mask(bounds.0, bounds.1, width, height, &rgba);
    }
}
