use crate::Rgba;

use crate::raster::blend::{blend_pixel, rgba_to_present_pixel};

pub(crate) type Matrix = (f64, f64, f64, f64, f64, f64);

pub(crate) type Point = (f64, f64);

pub(crate) struct OverlayRegion<'a> {
    pub(crate) min_x: usize,
    pub(crate) min_y: usize,
    pub(super) width: usize,
    pub(super) height: usize,
    pub(super) canvas_width: usize,
    pub(super) pixels: &'a mut [u8],
    pub(super) present_pixels: &'a mut [u32],
    pub(super) erasing: bool,
    pub(super) blend_mode: &'a str,
    pub(super) clip_mask: Option<&'a [bool]>,
}

impl<'a> OverlayRegion<'a> {
    pub(crate) fn from_bounds(
        bounds: (usize, usize, usize, usize),
        canvas_width: usize,
        pixels: &'a mut [u8],
        present_pixels: &'a mut [u32],
        erasing: bool,
        blend_mode: &'a str,
        clip_mask: Option<&'a [bool]>,
    ) -> Option<Self> {
        let (min_x, min_y, max_x, max_y) = bounds;
        let width = max_x.saturating_sub(min_x);
        let height = max_y.saturating_sub(min_y);
        if width == 0 || height == 0 {
            return None;
        }
        Some(Self {
            min_x,
            min_y,
            width,
            height,
            canvas_width,
            pixels,
            present_pixels,
            erasing,
            blend_mode,
            clip_mask,
        })
    }

    pub(crate) fn max_x(&self) -> usize {
        self.min_x + self.width
    }

    pub(crate) fn max_y(&self) -> usize {
        self.min_y + self.height
    }

    pub(crate) fn set_pixel(&mut self, x: usize, y: usize, color: Rgba) {
        let pixel_index = y * self.canvas_width + x;
        if self
            .clip_mask
            .is_some_and(|mask| !mask.get(pixel_index).copied().unwrap_or(false))
        {
            return;
        }
        let offset = pixel_index * 4;
        let dst = &mut self.pixels[offset..offset + 4];
        let color = color.as_array();
        if self.erasing {
            dst[3] = dst[3].saturating_sub(color[3]);
        } else {
            blend_pixel(dst, &color, self.blend_mode);
        }
        self.present_pixels[pixel_index] = rgba_to_present_pixel(dst);
    }
}
