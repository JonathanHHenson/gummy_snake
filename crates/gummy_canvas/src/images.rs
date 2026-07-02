use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

pub(crate) fn validate_rgba_buffer(length: usize, width: usize, height: usize) -> PyResult<()> {
    let expected = width
        .checked_mul(height)
        .and_then(|pixels| pixels.checked_mul(4))
        .ok_or_else(|| PyValueError::new_err("Image dimensions are too large."))?;
    if length == expected {
        Ok(())
    } else {
        Err(PyValueError::new_err(format!(
            "RGBA buffer length must be {expected}, got {length}."
        )))
    }
}

pub(crate) fn resize_rgba_nearest(
    pixels: &[u8],
    width: usize,
    height: usize,
    target_width: usize,
    target_height: usize,
) -> Vec<u8> {
    let mut resized = vec![0_u8; target_width * target_height * 4];
    for y in 0..target_height {
        let sy = (y * height / target_height).min(height - 1);
        for x in 0..target_width {
            let sx = (x * width / target_width).min(width - 1);
            let src = (sy * width + sx) * 4;
            let dst = (y * target_width + x) * 4;
            resized[dst..dst + 4].copy_from_slice(&pixels[src..src + 4]);
        }
    }
    resized
}

pub(crate) fn crop_rgba_with_padding(
    pixels: &[u8],
    width: usize,
    height: usize,
    sx: i64,
    sy: i64,
    sw: usize,
    sh: usize,
) -> Vec<u8> {
    let mut cropped = vec![0_u8; sw * sh * 4];
    let copy_x0 = sx.max(0).min(width as i64) as usize;
    let copy_y0 = sy.max(0).min(height as i64) as usize;
    let copy_x1 = (sx + sw as i64).max(0).min(width as i64) as usize;
    let copy_y1 = (sy + sh as i64).max(0).min(height as i64) as usize;
    if copy_x0 >= copy_x1 || copy_y0 >= copy_y1 {
        return cropped;
    }
    let row_bytes = (copy_x1 - copy_x0) * 4;
    for src_y in copy_y0..copy_y1 {
        let dst_y = (src_y as i64 - sy) as usize;
        let src = (src_y * width + copy_x0) * 4;
        let dst = (dst_y * sw + (copy_x0 as i64 - sx) as usize) * 4;
        cropped[dst..dst + row_bytes].copy_from_slice(&pixels[src..src + row_bytes]);
    }
    cropped
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn alpha_composite_rgba_region(
    dst: &mut [u8],
    dst_width: usize,
    dst_height: usize,
    src: &[u8],
    src_width: usize,
    src_height: usize,
    dx: i64,
    dy: i64,
) {
    let dst_x0 = dx.max(0).min(dst_width as i64) as usize;
    let dst_y0 = dy.max(0).min(dst_height as i64) as usize;
    let dst_x1 = (dx + src_width as i64).max(0).min(dst_width as i64) as usize;
    let dst_y1 = (dy + src_height as i64).max(0).min(dst_height as i64) as usize;
    if dst_x0 >= dst_x1 || dst_y0 >= dst_y1 {
        return;
    }
    for ty in dst_y0..dst_y1 {
        let src_y = (ty as i64 - dy) as usize;
        for tx in dst_x0..dst_x1 {
            let src_x = (tx as i64 - dx) as usize;
            let dst_offset = (ty * dst_width + tx) * 4;
            let src_offset = (src_y * src_width + src_x) * 4;
            alpha_composite_pixel(
                &mut dst[dst_offset..dst_offset + 4],
                &src[src_offset..src_offset + 4],
            );
        }
    }
}

pub(crate) fn apply_rgba_mask(
    pixels: &mut [u8],
    width: usize,
    height: usize,
    mask_pixels: &[u8],
    mask_width: usize,
    mask_height: usize,
) {
    for y in 0..height {
        let my = (y * mask_height / height).min(mask_height - 1);
        for x in 0..width {
            let mx = (x * mask_width / width).min(mask_width - 1);
            let mask_offset = (my * mask_width + mx) * 4;
            let mask_alpha = ((mask_pixels[mask_offset] as u32
                + mask_pixels[mask_offset + 1] as u32
                + mask_pixels[mask_offset + 2] as u32)
                * mask_pixels[mask_offset + 3] as u32
                + 382)
                / 765;
            let offset = (y * width + x) * 4 + 3;
            pixels[offset] = ((pixels[offset] as u32 * mask_alpha + 127) / 255) as u8;
        }
    }
}

pub(crate) fn filter_rgba(pixels: &mut [u8], mode: &str, value: Option<f64>) -> PyResult<()> {
    match mode {
        "gray" => {
            for pixel in pixels.chunks_exact_mut(4) {
                let gray = luma(pixel);
                pixel[0] = gray;
                pixel[1] = gray;
                pixel[2] = gray;
            }
        }
        "invert" => {
            for pixel in pixels.chunks_exact_mut(4) {
                pixel[0] = 255 - pixel[0];
                pixel[1] = 255 - pixel[1];
                pixel[2] = 255 - pixel[2];
            }
        }
        "threshold" => {
            let threshold = ((value.unwrap_or(0.5) * 255.0).round()).clamp(0.0, 255.0) as u8;
            for pixel in pixels.chunks_exact_mut(4) {
                let bw = if luma(pixel) >= threshold { 255 } else { 0 };
                pixel[0] = bw;
                pixel[1] = bw;
                pixel[2] = bw;
            }
        }
        "blur" | "posterize" | "erode" | "dilate" => {}
        _ => {
            return Err(PyValueError::new_err(format!(
                "Unsupported image filter {mode:?}."
            )));
        }
    }
    Ok(())
}

pub(crate) fn convert_media_frame_to_rgba(
    width: usize,
    height: usize,
    channels: usize,
    pixels: &[u8],
) -> PyResult<Vec<u8>> {
    if !matches!(channels, 1 | 3 | 4) {
        return Err(PyValueError::new_err(
            "Decoded media frames must have 1, 3, or 4 channels.",
        ));
    }
    let mut rgba = vec![0_u8; width * height * 4];
    match channels {
        1 => {
            for (src, dst) in pixels
                .iter()
                .take(width * height)
                .zip(rgba.chunks_exact_mut(4))
            {
                dst.copy_from_slice(&[*src, *src, *src, 255]);
            }
        }
        3 => {
            for index in 0..(width * height) {
                let src = index * 3;
                let dst = index * 4;
                rgba[dst..dst + 4].copy_from_slice(&[
                    pixels[src + 2],
                    pixels[src + 1],
                    pixels[src],
                    255,
                ]);
            }
        }
        4 => {
            for index in 0..(width * height) {
                let src = index * 4;
                let dst = index * 4;
                rgba[dst..dst + 4].copy_from_slice(&[
                    pixels[src + 2],
                    pixels[src + 1],
                    pixels[src],
                    pixels[src + 3],
                ]);
            }
        }
        _ => unreachable!(),
    }
    Ok(rgba)
}

pub(crate) fn alpha_composite_pixel(dst: &mut [u8], src: &[u8]) {
    let src_alpha = src[3] as u32;
    if src_alpha == 255 {
        dst.copy_from_slice(src);
        return;
    }
    let dst_alpha = dst[3] as u32;
    if src_alpha == 0 {
        return;
    }
    let inv_src_alpha = 255 - src_alpha;
    let out_alpha = src_alpha + (dst_alpha * inv_src_alpha + 127) / 255;
    if out_alpha == 0 {
        dst.copy_from_slice(&[0, 0, 0, 0]);
        return;
    }
    for channel in 0..3 {
        let src_premul = src[channel] as u32 * src_alpha;
        let dst_premul = dst[channel] as u32 * dst_alpha * inv_src_alpha / 255;
        dst[channel] = ((src_premul + dst_premul + out_alpha / 2) / out_alpha) as u8;
    }
    dst[3] = out_alpha as u8;
}

fn luma(pixel: &[u8]) -> u8 {
    (pixel[0] as f64 * 0.299 + pixel[1] as f64 * 0.587 + pixel[2] as f64 * 0.114).round() as u8
}
