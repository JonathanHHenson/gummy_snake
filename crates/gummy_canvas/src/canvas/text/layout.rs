use crate::assets::{CachedText, CachedTextMetrics};
use crate::types::Style;

pub(crate) enum TextLineIter<'a> {
    Empty(std::iter::Once<&'a str>),
    Split(std::str::Split<'a, char>),
}

impl<'a> Iterator for TextLineIter<'a> {
    type Item = &'a str;

    fn next(&mut self) -> Option<Self::Item> {
        match self {
            Self::Empty(iter) => iter.next(),
            Self::Split(iter) => iter.next(),
        }
    }
}

pub(crate) struct CachedTextLineLayout {
    pub(crate) dx: f64,
    pub(crate) dy: f64,
    pub(crate) width: f64,
    pub(crate) height: f64,
}

pub(crate) struct GpuTextLineLayout {
    pub(crate) dx: f64,
    pub(crate) dy: f64,
    pub(crate) draw_width: f64,
    pub(crate) draw_height: f64,
    pub(crate) line_height: f64,
}

pub(crate) fn text_lines(value: &str) -> TextLineIter<'_> {
    if value.is_empty() {
        TextLineIter::Empty(std::iter::once(""))
    } else {
        TextLineIter::Split(value.split('\n'))
    }
}

pub(crate) fn physical_font_size(style: &Style, pixel_density: f64) -> usize {
    (style.text_size * pixel_density).round().max(1.0) as usize
}

pub(crate) fn layout_cached_text_line(
    cached: &CachedText,
    x: f64,
    y: f64,
    line_index: usize,
    style: &Style,
    pixel_density: f64,
) -> Option<CachedTextLineLayout> {
    if cached.image.width == 0 || cached.image.height == 0 {
        return None;
    }
    let width = cached.image.width as f64 / pixel_density;
    let height = cached.image.height as f64 / pixel_density;
    let (mut dx, mut dy) = aligned_text_origin(
        x,
        y,
        line_index,
        width,
        height,
        cached.ascent,
        style,
        pixel_density,
    );
    dx += cached.bbox_left as f64 / pixel_density;
    dy += cached.bbox_top as f64 / pixel_density;
    Some(CachedTextLineLayout {
        dx,
        dy,
        width,
        height,
    })
}

pub(crate) fn layout_gpu_text_line(
    metrics: CachedTextMetrics,
    x: f64,
    y: f64,
    line_index: usize,
    style: &Style,
    font_size: usize,
    pixel_density: f64,
) -> Option<GpuTextLineLayout> {
    if metrics.width <= 0.0 {
        return None;
    }
    let width = metrics.width / pixel_density;
    let height = (metrics.ascent + metrics.descent).max(font_size as f64) / pixel_density;
    let (dx, dy) = aligned_text_origin(
        x,
        y,
        line_index,
        width,
        height,
        metrics.ascent,
        style,
        pixel_density,
    );
    Some(GpuTextLineLayout {
        dx,
        dy,
        draw_width: (width * pixel_density + font_size as f64).max(1.0),
        draw_height: (height * pixel_density + font_size as f64 * 0.5).max(style.text_leading),
        line_height: (style.text_leading * pixel_density).max(font_size as f64),
    })
}

fn aligned_text_origin(
    x: f64,
    y: f64,
    line_index: usize,
    width: f64,
    height: f64,
    ascent: f64,
    style: &Style,
    pixel_density: f64,
) -> (f64, f64) {
    let mut dx = x;
    let mut dy = y + line_index as f64 * style.text_leading;
    if style.text_align_x == "center" {
        dx -= width / 2.0;
    } else if style.text_align_x == "right" {
        dx -= width;
    }
    if style.text_align_y == "center" {
        dy -= height / 2.0;
    } else if style.text_align_y == "bottom" {
        dy -= height;
    } else if style.text_align_y == "baseline" {
        dy -= ascent / pixel_density;
    }
    (dx, dy)
}
