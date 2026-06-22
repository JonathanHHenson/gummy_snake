use ab_glyph::{point, Font, FontArc, GlyphId, PxScale, ScaleFont};

use crate::Rgba;

pub(crate) struct RenderedTextLine {
    pub(crate) width: usize,
    pub(crate) height: usize,
    pub(crate) pixels: Vec<u8>,
    pub(crate) bbox_left: i32,
    pub(crate) bbox_top: i32,
    pub(crate) ascent: f64,
}

pub(crate) fn render_text_line(
    line: &str,
    font: &FontArc,
    font_size: usize,
    fill: Rgba,
) -> RenderedTextLine {
    let scale = PxScale::from(font_size as f32);
    let scaled_font = font.as_scaled(scale);
    let ascent = scaled_font.ascent().ceil().max(0.0) as f64;
    let mut caret = 0.0_f32;
    let mut glyphs = Vec::new();
    let mut previous: Option<GlyphId> = None;
    for ch in line.chars() {
        let glyph_id = scaled_font.glyph_id(ch);
        if let Some(previous_id) = previous {
            caret += scaled_font.kern(previous_id, glyph_id);
        }
        glyphs.push(glyph_id.with_scale_and_position(scale, point(caret, ascent as f32)));
        caret += scaled_font.h_advance(glyph_id);
        previous = Some(glyph_id);
    }

    let outlines: Vec<_> = glyphs
        .into_iter()
        .filter_map(|glyph| font.outline_glyph(glyph))
        .collect();
    if outlines.is_empty() {
        return RenderedTextLine {
            width: 1,
            height: font_size.max(1),
            pixels: vec![0; font_size.max(1) * 4],
            bbox_left: 0,
            bbox_top: 0,
            ascent,
        };
    }

    let mut min_x = i32::MAX;
    let mut min_y = i32::MAX;
    let mut max_x = i32::MIN;
    let mut max_y = i32::MIN;
    for outline in &outlines {
        let bounds = outline.px_bounds();
        min_x = min_x.min(bounds.min.x.floor() as i32);
        min_y = min_y.min(bounds.min.y.floor() as i32);
        max_x = max_x.max(bounds.max.x.ceil() as i32);
        max_y = max_y.max(bounds.max.y.ceil() as i32);
    }

    let width = (max_x - min_x).max(1) as usize;
    let height = (max_y - min_y).max(1) as usize;
    let mut pixels = vec![0; width * height * 4];
    for outline in outlines {
        let bounds = outline.px_bounds();
        let glyph_min_x = bounds.min.x.floor() as i32;
        let glyph_min_y = bounds.min.y.floor() as i32;
        outline.draw(|gx, gy, coverage| {
            let x = gx as i32 + glyph_min_x - min_x;
            let y = gy as i32 + glyph_min_y - min_y;
            if x < 0 || y < 0 {
                return;
            }
            let x = x as usize;
            let y = y as usize;
            if x >= width || y >= height {
                return;
            }
            let offset = (y * width + x) * 4;
            pixels[offset] = fill.r;
            pixels[offset + 1] = fill.g;
            pixels[offset + 2] = fill.b;
            pixels[offset + 3] = ((fill.a as f32 * coverage).round() as i32).clamp(0, 255) as u8;
        });
    }

    RenderedTextLine {
        width,
        height,
        pixels,
        bbox_left: min_x,
        bbox_top: min_y,
        ascent,
    }
}

pub(crate) fn text_ascent(font: &FontArc, font_size: usize) -> f64 {
    let scaled_font = font.as_scaled(PxScale::from(font_size as f32));
    scaled_font.ascent().ceil().max(0.0) as f64
}

pub(crate) fn text_descent(font: &FontArc, font_size: usize) -> f64 {
    let scaled_font = font.as_scaled(PxScale::from(font_size as f32));
    scaled_font.descent().abs().ceil().max(0.0) as f64
}

pub(crate) fn default_font_paths() -> &'static [&'static str] {
    &[
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
    ]
}
