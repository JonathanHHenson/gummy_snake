use crate::runtime::style::parse_style;
use crate::*;

impl Canvas {
    pub(crate) fn evict_image_cache_if_needed(&mut self, incoming_key: u64) {
        if self.image_cache.contains_key(&incoming_key)
            || self.image_cache.len() < IMAGE_CACHE_LIMIT
        {
            return;
        }
        if let Some(evicted_key) = self.image_cache.keys().next().copied() {
            self.image_cache.remove(&evicted_key);
            self.texture_cache_versions.remove(&evicted_key);
        }
    }

    pub(crate) fn evict_texture_cache_if_needed(&mut self, incoming_key: u64) {
        if self.texture_cache_versions.contains_key(&incoming_key)
            || self.texture_cache_versions.len() < TEXTURE_CACHE_LIMIT
        {
            return;
        }
        if let Some(evicted_key) = self.texture_cache_versions.keys().next().copied() {
            self.texture_cache_versions.remove(&evicted_key);
        }
    }

    pub(crate) fn cached_style(&mut self, style: &Bound<'_, PyAny>) -> PyResult<Style> {
        let key = style.as_ptr() as usize;
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

    pub(crate) fn draw_transformed_polygon(
        &mut self,
        points: &[Point],
        style: &Style,
        close: bool,
    ) -> PyResult<()> {
        let padding = if style.stroke.is_some() {
            stroke_width(style.stroke_weight, self.pixel_density) / 2.0
        } else {
            0.0
        };
        let bounds = clipped_bounds(points, padding, self.physical_width, self.physical_height);
        if self.can_queue_gpu_polygon(points, style, close) {
            self.draw_gpu_polygon(points, style, close, self.pixel_density)?;
            return Ok(());
        }
        self.prepare_cpu_composite();
        let Some(mut overlay) = OverlayRegion::from_bounds(
            bounds,
            self.physical_width,
            &mut self.pixels,
            &mut self.present_pixels,
            style.erasing,
            &style.blend_mode,
            self.clip_masks.last().map(Vec::as_slice),
        ) else {
            return Ok(());
        };
        draw_polygon_overlay(&mut overlay, points, style, close, self.pixel_density);
        self.upload_cpu_pixels()?;
        Ok(())
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
        for (index, rgba) in self.pixels.chunks_exact(4).enumerate() {
            self.present_pixels[index] = rgba_to_present_pixel(rgba);
        }
    }

    pub(crate) fn can_queue_gpu_primitives(&self, style: &Style) -> bool {
        self.gpu.is_some()
            && !self.cpu_compositing_active
            && !style.erasing
            && style.blend_mode == BLEND_MODE_BLEND
    }

    pub(crate) fn can_queue_gpu_polygon(
        &self,
        points: &[Point],
        style: &Style,
        close: bool,
    ) -> bool {
        self.can_queue_gpu_primitives(style)
            && (!close || style.fill.is_none() || polygon_is_convex(points))
    }

    pub(crate) fn cached_text_line(
        &mut self,
        line: &str,
        fill: Rgba,
        style: &Style,
    ) -> PyResult<CachedText> {
        let font_size = (style.text_size * self.pixel_density).round().max(1.0) as usize;
        let font_key = style
            .text_font_path
            .clone()
            .unwrap_or_else(|| format!("name:{}", style.text_font_name));
        let cache_key = format!(
            "{}|{}|{}:{}:{}:{}|{}",
            font_key, font_size, fill.r, fill.g, fill.b, fill.a, line
        );
        if let Some(cached) = self.text_cache.get(&cache_key) {
            let cached = cached.clone();
            self.performance_counters.text_cache_hits += 1;
            self.touch_text_cache_key(&cache_key);
            return Ok(cached);
        }
        self.performance_counters.text_cache_misses += 1;

        let font = self.load_text_font(style)?;
        let rendered = render_text_line(line, &font, font_size, fill);
        let texture_key = self.next_text_key;
        self.next_text_key = self.next_text_key.saturating_add(1);
        let cached = CachedText {
            texture_key,
            image: CachedImage {
                version: 0,
                width: rendered.width,
                height: rendered.height,
                pixels: rendered.pixels,
            },
            bbox_left: rendered.bbox_left,
            bbox_top: rendered.bbox_top,
            ascent: rendered.ascent,
        };
        self.evict_text_cache_if_needed();
        self.text_cache_order.push_back(cache_key.clone());
        self.text_cache.insert(cache_key, cached.clone());
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
                self.texture_cache_versions.remove(&evicted.texture_key);
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
        if let Some(font) = self.font_cache.get(path) {
            return Ok(font.clone());
        }
        let bytes = std::fs::read(path)
            .map_err(|err| PyValueError::new_err(format!("Could not load font {path}: {err}")))?;
        let font = FontArc::try_from_vec(bytes)
            .map_err(|_| PyValueError::new_err(format!("Could not parse font {path}.")))?;
        self.font_cache.insert(path.to_string(), font.clone());
        Ok(font)
    }
}
