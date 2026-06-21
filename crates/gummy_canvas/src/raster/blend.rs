use crate::image_ops::alpha_composite_pixel;
use crate::{
    BLEND_MODE_ADD, BLEND_MODE_BLEND, BLEND_MODE_DARKEST, BLEND_MODE_DIFFERENCE,
    BLEND_MODE_EXCLUSION, BLEND_MODE_LIGHTEST, BLEND_MODE_MULTIPLY, BLEND_MODE_REPLACE,
    BLEND_MODE_SCREEN,
};

pub(super) fn blend_pixel(dst: &mut [u8], src: &[u8], mode: &str) {
    if mode == BLEND_MODE_BLEND {
        alpha_composite_pixel(dst, src);
        return;
    }
    if mode == BLEND_MODE_REPLACE {
        alpha_composite_pixel(dst, src);
        return;
    }
    let alpha = src[3] as u32;
    if alpha == 0 {
        return;
    }
    let base = [dst[0], dst[1], dst[2]];
    let blend = [
        blend_channel(base[0], src[0], mode),
        blend_channel(base[1], src[1], mode),
        blend_channel(base[2], src[2], mode),
    ];
    let inv_alpha = 255 - alpha;
    for channel in 0..3 {
        dst[channel] =
            ((blend[channel] as u32 * alpha + base[channel] as u32 * inv_alpha + 127) / 255) as u8;
    }
}

fn blend_channel(base: u8, src: u8, mode: &str) -> u8 {
    match mode {
        BLEND_MODE_ADD => base.saturating_add(src),
        BLEND_MODE_DARKEST => base.min(src),
        BLEND_MODE_LIGHTEST => base.max(src),
        BLEND_MODE_DIFFERENCE => base.abs_diff(src),
        BLEND_MODE_EXCLUSION => {
            let base = base as u32;
            let src = src as u32;
            (base + src - (2 * base * src + 127) / 255).min(255) as u8
        }
        BLEND_MODE_MULTIPLY => ((base as u32 * src as u32 + 127) / 255) as u8,
        BLEND_MODE_SCREEN => {
            let inv = (255 - base as u32) * (255 - src as u32);
            (255 - (inv + 127) / 255) as u8
        }
        _ => src,
    }
}

pub(crate) fn fill_rgba_buffer(pixels: &mut [u8], color: &[u8; 4]) {
    if pixels.is_empty() {
        return;
    }
    let first_len = pixels.len().min(4);
    pixels[..first_len].copy_from_slice(&color[..first_len]);
    let mut filled = first_len;
    while filled < pixels.len() {
        let copy_len = filled.min(pixels.len() - filled);
        pixels.copy_within(0..copy_len, filled);
        filled += copy_len;
    }
}

pub(crate) fn rgba_to_present_pixel(rgba: &[u8]) -> u32 {
    ((rgba[3] as u32) << 24) | ((rgba[0] as u32) << 16) | ((rgba[1] as u32) << 8) | rgba[2] as u32
}
