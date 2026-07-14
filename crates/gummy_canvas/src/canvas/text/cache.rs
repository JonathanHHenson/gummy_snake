use super::layout::physical_font_size;
use crate::assets::{CachedImage, CachedText};
use crate::canvas_state::Canvas;
use crate::config::*;
use crate::raster::{rgba_to_present_pixel, Matrix};
use crate::runtime::style::parse_style;
use crate::text::{default_font_paths, render_text_line};
use crate::types::{Rgba, Style};
use ab_glyph::FontArc;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyAny;
use pyo3::types::PyDict;
use std::sync::Arc;

impl Canvas {
    pub(crate) fn insert_image_cache_entry(&mut self, key: u64, image: CachedImage) -> bool {
        let (evictions, evicted_bytes, inserted) = self.image_cache.insert(key, image);
        self.performance_counters.image_cache_evictions += evictions as u64;
        self.performance_counters.image_cache_evicted_bytes += evicted_bytes as u64;
        self.update_image_cache_byte_counters();
        inserted
    }

    pub(crate) fn evict_texture_cache_if_needed(
        &mut self,
        incoming_key: u64,
        incoming_bytes: usize,
    ) -> PyResult<()> {
        if incoming_bytes > self.texture_cache_versions.max_bytes() {
            return Err(PyValueError::new_err(format!(
                "Image texture is {incoming_bytes} bytes, exceeding the bounded GPU texture cache budget of {} bytes.",
                self.texture_cache_versions.max_bytes()
            )));
        }
        let mut pinned_checks = 0;
        while self
            .texture_cache_versions
            .needs_eviction(incoming_key, incoming_bytes)
            && pinned_checks < self.texture_cache_versions.len()
        {
            let Some(evicted_key) = self.texture_cache_versions.oldest_key_except(incoming_key)
            else {
                break;
            };
            if self
                .gpu
                .as_ref()
                .is_some_and(|gpu| gpu.texture_is_pending(evicted_key))
            {
                self.texture_cache_versions.touch(evicted_key);
                pinned_checks += 1;
                continue;
            }
            let Some(evicted) = self.texture_cache_versions.remove(evicted_key) else {
                break;
            };
            self.performance_counters.texture_cache_evictions += 1;
            if evicted.is_atlas {
                self.performance_counters.image_atlas_evictions += 1;
            }
            if self
                .gpu
                .as_mut()
                .and_then(|gpu| gpu.remove_texture(evicted_key))
                .is_some()
            {
                self.performance_counters.texture_destructions += 1;
                if evicted.is_atlas {
                    self.performance_counters.image_atlas_destructions += 1;
                }
            }
        }
        self.update_texture_cache_byte_counters();
        Ok(())
    }

    pub(crate) fn record_texture_upload(
        &mut self,
        key: u64,
        version: u64,
        bytes: usize,
        is_atlas: bool,
        dirty: bool,
        replaced_gpu_bytes: Option<usize>,
    ) {
        self.performance_counters.texture_uploads += 1;
        self.performance_counters.texture_upload_bytes += bytes as u64;
        if dirty {
            self.performance_counters.texture_dirty_uploads += 1;
        }
        if replaced_gpu_bytes.is_some() {
            self.performance_counters.texture_destructions += 1;
            if is_atlas {
                self.performance_counters.image_atlas_destructions += 1;
            }
        }
        self.texture_cache_versions
            .insert(key, version, bytes, is_atlas);
        self.update_texture_cache_byte_counters();
    }

    pub(crate) fn remove_cached_texture_if_unpinned(&mut self, key: u64) {
        if self
            .gpu
            .as_ref()
            .is_some_and(|gpu| gpu.texture_is_pending(key))
        {
            return;
        }
        let Some(removed) = self.texture_cache_versions.remove(key) else {
            return;
        };
        self.performance_counters.texture_cache_evictions += 1;
        if removed.is_atlas {
            self.performance_counters.image_atlas_evictions += 1;
        }
        if self
            .gpu
            .as_mut()
            .and_then(|gpu| gpu.remove_texture(key))
            .is_some()
        {
            self.performance_counters.texture_destructions += 1;
            if removed.is_atlas {
                self.performance_counters.image_atlas_destructions += 1;
            }
        }
        self.update_texture_cache_byte_counters();
    }

    fn update_image_cache_byte_counters(&mut self) {
        let resident = self.image_cache.resident_bytes() as u64;
        self.performance_counters.image_cache_resident_bytes = resident;
        self.performance_counters.image_cache_peak_bytes = self
            .performance_counters
            .image_cache_peak_bytes
            .max(resident);
    }

    pub(crate) fn update_texture_cache_byte_counters(&mut self) {
        let persistent_atlas_resident = self
            .gpu
            .as_ref()
            .map_or(0, |gpu| gpu.persistent_image_atlas_resident_bytes() as u64);
        let resident = (self.texture_cache_versions.resident_bytes() as u64)
            .saturating_add(persistent_atlas_resident);
        let atlas_resident = (self.texture_cache_versions.atlas_resident_bytes() as u64)
            .saturating_add(persistent_atlas_resident);
        self.performance_counters.texture_resident_bytes = resident;
        self.performance_counters.texture_peak_bytes =
            self.performance_counters.texture_peak_bytes.max(resident);
        self.performance_counters.image_atlas_resident_bytes = atlas_resident;
        self.performance_counters.image_atlas_peak_bytes = self
            .performance_counters
            .image_atlas_peak_bytes
            .max(atlas_resident);
    }

    pub(crate) fn cached_style(&mut self, style: &Bound<'_, PyAny>) -> PyResult<Style> {
        let dict = style.downcast::<PyDict>().ok();
        let revision = dict
            .as_ref()
            .and_then(|dict| dict.get_item("_style_revision").ok().flatten())
            .and_then(|value| value.extract::<i64>().ok());
        let Some(revision) = revision else {
            return parse_style(style);
        };
        let payload_key = dict
            .as_ref()
            .and_then(|dict| dict.get_item("_style_cache_key").ok().flatten())
            .and_then(|value| value.extract::<usize>().ok())
            .unwrap_or_else(|| style.as_ptr() as usize);
        let key = (payload_key, revision);
        if self.cached_style_key == Some(key) {
            if let Some(cached) = self.cached_style.as_ref() {
                return Ok(cached.clone());
            }
        }
        let parsed = parse_style(style)?;
        self.cached_style_key = Some(key);
        self.cached_style = Some(parsed.clone());
        Ok(parsed)
    }

    pub(crate) fn axis_aligned_ellipse_geometry(
        &self,
        matrix: Matrix,
        x: f64,
        y: f64,
        width: f64,
        height: f64,
    ) -> Option<(f64, f64, f64, f64)> {
        let (a, b, c, d, e, f) = matrix;
        if b.abs() > f64::EPSILON || c.abs() > f64::EPSILON {
            return None;
        }
        let cx = x + width / 2.0;
        let cy = y + height / 2.0;
        Some((
            (a * cx + e) * self.pixel_density,
            (d * cy + f) * self.pixel_density,
            (width * a * self.pixel_density / 2.0).abs(),
            (height * d * self.pixel_density / 2.0).abs(),
        ))
    }

    pub(crate) fn sync_present_pixels_from_rgba(&mut self) {
        self.ensure_present_pixel_buffer();
        for (index, rgba) in self.pixels.chunks_exact(4).enumerate() {
            self.present_pixels[index] = rgba_to_present_pixel(rgba);
        }
    }

    pub(crate) fn can_queue_gpu_primitives(&self, style: &Style) -> bool {
        self.gpu.is_some()
            && !self.cpu_compositing_active
            && !style.erasing
            && style.blend_mode_kind.gpu_fixed_function_supported()
    }

    pub(crate) fn can_queue_gpu_erase(&self, style: &Style) -> bool {
        self.gpu.is_some()
            && !self.cpu_compositing_active
            && style.erasing
            && style.blend_mode == BLEND_MODE_BLEND
    }

    pub(crate) fn cached_text_line(
        &mut self,
        line: &str,
        fill: Rgba,
        style: &Style,
    ) -> PyResult<CachedText> {
        let font_size = physical_font_size(style, self.pixel_density);
        let font_key = style
            .text_font_path
            .clone()
            .unwrap_or_else(|| format!("name:{}", style.text_font_name));
        let cache_key = format!(
            "{}|{}|{}:{}:{}:{}|{}",
            font_key, font_size, fill.r, fill.g, fill.b, fill.a, line
        );
        if let Some(cached) = self.text_cache.get_line(&cache_key) {
            let cached = cached.clone();
            self.performance_counters.text_cache_hits += 1;
            self.touch_text_cache_key(&cache_key);
            return Ok(cached);
        }
        self.performance_counters.text_cache_misses += 1;

        let font = self.load_text_font(style)?;
        let rendered = render_text_line(line, &font, font_size, fill);
        let texture_key = self.text_cache.next_texture_key();
        let cached = CachedText {
            texture_key,
            image: CachedImage {
                version: 0,
                width: rendered.width,
                height: rendered.height,
                pixels: Arc::new(rendered.pixels),
            },
            bbox_left: rendered.bbox_left,
            bbox_top: rendered.bbox_top,
            ascent: rendered.ascent,
        };
        self.evict_text_cache_if_needed();
        self.text_cache_order.push_back(cache_key.clone());
        self.text_cache.insert_line(cache_key, cached.clone());
        Ok(cached)
    }

    pub(crate) fn touch_text_cache_key(&mut self, cache_key: &str) {
        if let Some(index) = self
            .text_cache_order
            .iter()
            .position(|key| key == cache_key)
        {
            if let Some(key) = self.text_cache_order.remove(index) {
                self.text_cache_order.push_back(key);
            }
        }
    }

    pub(crate) fn evict_text_cache_if_needed(&mut self) {
        while self.text_cache.len() >= TEXT_CACHE_LIMIT {
            let Some(evicted_key) = self.text_cache_order.pop_front() else {
                break;
            };
            if let Some(evicted) = self.text_cache.remove(&evicted_key) {
                self.remove_cached_texture_if_unpinned(evicted.texture_key);
                self.performance_counters.text_cache_evictions += 1;
            }
        }
    }

    pub(crate) fn load_text_font(&mut self, style: &Style) -> PyResult<FontArc> {
        if let Some(path) = style.text_font_path.as_ref() {
            return self.load_text_font_path(path);
        }
        for path in default_font_paths() {
            if let Ok(font) = self.load_text_font_path(path) {
                return Ok(font);
            }
        }
        Err(PyValueError::new_err(
            "Could not load a default system font for canvas text.",
        ))
    }

    pub(crate) fn load_text_font_path(&mut self, path: &str) -> PyResult<FontArc> {
        if let Some(font) = self.text_cache.get_font(path) {
            return Ok(font.clone());
        }
        let bytes = std::fs::read(path)
            .map_err(|err| PyValueError::new_err(format!("Could not load font {path}: {err}")))?;
        let font = FontArc::try_from_vec(bytes)
            .map_err(|_| PyValueError::new_err(format!("Could not parse font {path}.")))?;
        self.text_cache.insert_font(path.to_string(), font.clone());
        Ok(font)
    }
}
