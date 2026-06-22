use crate::{BlendMode, BLEND_MODE_BLEND};

use crate::raster::blend::{blend_pixel, rgba_to_present_pixel};
use crate::raster::types::Matrix;

#[allow(clippy::too_many_arguments)]
pub(crate) fn blit_scaled_region(
    dst: &mut [u8],
    present_pixels: &mut [u32],
    dst_width: usize,
    src: &[u8],
    src_width: usize,
    sx: usize,
    sy: usize,
    sw: usize,
    sh: usize,
    dx: usize,
    dy: usize,
    dw: usize,
    dh: usize,
    erasing: bool,
    blend_mode: &str,
    sampling: &str,
    clip_mask: Option<&[bool]>,
) {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 {
        return;
    }
    let nearest = sampling == "nearest";
    let default_blend = blend_mode == BLEND_MODE_BLEND;
    let blend_mode = BlendMode::parse(blend_mode).unwrap_or(BlendMode::Blend);
    for out_y in 0..dh {
        let local_y = if nearest {
            (out_y * sh / dh).min(sh - 1) as f64
        } else {
            (out_y as f64 + 0.5) * sh as f64 / dh as f64 - 0.5
        };
        for out_x in 0..dw {
            let local_x = if nearest {
                (out_x * sw / dw).min(sw - 1) as f64
            } else {
                (out_x as f64 + 0.5) * sw as f64 / dw as f64 - 0.5
            };
            let src_pixel =
                sample_image_pixel(src, src_width, sx, sy, sw, sh, local_x, local_y, nearest);
            if src_pixel[3] == 0 {
                continue;
            }
            let dst_pixel_index = (dy + out_y) * dst_width + dx + out_x;
            if clip_mask.is_some_and(|mask| !mask[dst_pixel_index]) {
                continue;
            }
            let dst_offset = dst_pixel_index * 4;
            let dst_pixel = &mut dst[dst_offset..dst_offset + 4];
            if erasing {
                dst_pixel[3] = dst_pixel[3].saturating_sub(src_pixel[3]);
            } else if default_blend && src_pixel[3] == 255 {
                dst_pixel.copy_from_slice(&src_pixel);
            } else {
                blend_pixel(dst_pixel, &src_pixel, blend_mode);
            }
            present_pixels[dst_pixel_index] = rgba_to_present_pixel(dst_pixel);
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn blit_affine_region(
    dst: &mut [u8],
    present_pixels: &mut [u32],
    dst_width: usize,
    src: &[u8],
    src_width: usize,
    sx: usize,
    sy: usize,
    sw: usize,
    sh: usize,
    dx: usize,
    dy: usize,
    dw: usize,
    dh: usize,
    canvas_to_image: Matrix,
    erasing: bool,
    blend_mode: &str,
    sampling: &str,
    clip_mask: Option<&[bool]>,
) {
    if sw == 0 || sh == 0 || dw == 0 || dh == 0 {
        return;
    }
    let nearest = sampling == "nearest";
    let default_blend = blend_mode == BLEND_MODE_BLEND;
    let blend_mode = BlendMode::parse(blend_mode).unwrap_or(BlendMode::Blend);
    let (a, b, c, d, e, f) = canvas_to_image;
    for out_y in 0..dh {
        let canvas_y = dy + out_y;
        let sample_y = canvas_y as f64 + 0.5;
        let mut local_x = a * (dx as f64 + 0.5) + c * sample_y + e;
        let mut local_y = b * (dx as f64 + 0.5) + d * sample_y + f;
        for out_x in 0..dw {
            let canvas_x = dx + out_x;
            if local_x < 0.0 || local_y < 0.0 || local_x >= sw as f64 || local_y >= sh as f64 {
                local_x += a;
                local_y += b;
                continue;
            }
            let src_pixel =
                sample_image_pixel(src, src_width, sx, sy, sw, sh, local_x, local_y, nearest);
            if src_pixel[3] == 0 {
                local_x += a;
                local_y += b;
                continue;
            }
            let dst_pixel_index = canvas_y * dst_width + canvas_x;
            if clip_mask.is_some_and(|mask| !mask[dst_pixel_index]) {
                local_x += a;
                local_y += b;
                continue;
            }
            let dst_offset = dst_pixel_index * 4;
            let dst_pixel = &mut dst[dst_offset..dst_offset + 4];
            if erasing {
                dst_pixel[3] = dst_pixel[3].saturating_sub(src_pixel[3]);
            } else if default_blend && src_pixel[3] == 255 {
                dst_pixel.copy_from_slice(&src_pixel);
            } else {
                blend_pixel(dst_pixel, &src_pixel, blend_mode);
            }
            present_pixels[dst_pixel_index] = rgba_to_present_pixel(dst_pixel);
            local_x += a;
            local_y += b;
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn sample_image_pixel(
    src: &[u8],
    src_width: usize,
    sx: usize,
    sy: usize,
    sw: usize,
    sh: usize,
    local_x: f64,
    local_y: f64,
    nearest: bool,
) -> [u8; 4] {
    if nearest {
        let x = sx + local_x.floor().clamp(0.0, (sw - 1) as f64) as usize;
        let y = sy + local_y.floor().clamp(0.0, (sh - 1) as f64) as usize;
        let offset = (y * src_width + x) * 4;
        return [
            src[offset],
            src[offset + 1],
            src[offset + 2],
            src[offset + 3],
        ];
    }

    let clamped_x = local_x.clamp(0.0, (sw - 1) as f64);
    let clamped_y = local_y.clamp(0.0, (sh - 1) as f64);
    let x0 = clamped_x.floor() as usize;
    let y0 = clamped_y.floor() as usize;
    let x1 = (x0 + 1).min(sw - 1);
    let y1 = (y0 + 1).min(sh - 1);
    let tx = clamped_x - x0 as f64;
    let ty = clamped_y - y0 as f64;

    let p00 = source_pixel(src, src_width, sx + x0, sy + y0);
    let p10 = source_pixel(src, src_width, sx + x1, sy + y0);
    let p01 = source_pixel(src, src_width, sx + x0, sy + y1);
    let p11 = source_pixel(src, src_width, sx + x1, sy + y1);

    let mut out = [0_u8; 4];
    for channel in 0..4 {
        let top = p00[channel] as f64 * (1.0 - tx) + p10[channel] as f64 * tx;
        let bottom = p01[channel] as f64 * (1.0 - tx) + p11[channel] as f64 * tx;
        out[channel] = (top * (1.0 - ty) + bottom * ty).round().clamp(0.0, 255.0) as u8;
    }
    out
}

fn source_pixel(src: &[u8], src_width: usize, x: usize, y: usize) -> [u8; 4] {
    let offset = (y * src_width + x) * 4;
    [
        src[offset],
        src[offset + 1],
        src[offset + 2],
        src[offset + 3],
    ]
}
