use crate::prelude::*;
use ab_glyph::{FontArc, GlyphId};
use std::collections::HashMap;

#[derive(Debug, Default)]
pub(crate) struct ImageCache {
    entries: HashMap<u64, CachedImage>,
}

impl ImageCache {
    pub(crate) fn needs_update(&self, key: u64, version: u64, width: usize, height: usize) -> bool {
        self.entries
            .get(&key)
            .map(|cached| {
                cached.version != version || cached.width != width || cached.height != height
            })
            .unwrap_or(true)
    }

    pub(crate) fn get(&self, key: u64) -> Option<&CachedImage> {
        self.entries.get(&key)
    }

    pub(crate) fn insert(&mut self, key: u64, image: CachedImage) {
        self.entries.insert(key, image);
    }

    pub(crate) fn len(&self) -> usize {
        self.entries.len()
    }

    pub(crate) fn evict_if_needed(&mut self, incoming_key: u64) -> Option<u64> {
        if self.entries.contains_key(&incoming_key) || self.len() < IMAGE_CACHE_LIMIT {
            return None;
        }
        let evicted_key = self.entries.keys().next().copied()?;
        self.entries.remove(&evicted_key);
        Some(evicted_key)
    }
}

#[derive(Debug, Default)]
pub(crate) struct TextureCache {
    versions: HashMap<u64, u64>,
}

impl TextureCache {
    pub(crate) fn version(&self, key: u64) -> Option<u64> {
        self.versions.get(&key).copied()
    }

    pub(crate) fn insert(&mut self, key: u64, version: u64) {
        self.versions.insert(key, version);
    }

    pub(crate) fn contains_key(&self, key: &u64) -> bool {
        self.versions.contains_key(key)
    }

    pub(crate) fn remove(&mut self, key: u64) {
        self.versions.remove(&key);
    }

    pub(crate) fn evict_if_needed(&mut self, incoming_key: u64) -> Option<u64> {
        if self.contains_key(&incoming_key) || self.versions.len() < TEXTURE_CACHE_LIMIT {
            return None;
        }
        let evicted_key = self.versions.keys().next().copied()?;
        self.versions.remove(&evicted_key);
        Some(evicted_key)
    }
}

#[derive(Debug)]
pub(crate) struct TextCache {
    lines: HashMap<String, CachedText>,
    metrics: HashMap<String, CachedTextMetrics>,
    glyph_advances: HashMap<(String, usize, char), (GlyphId, f32)>,
    kerns: HashMap<(String, usize, GlyphId, GlyphId), f32>,
    fonts: HashMap<String, FontArc>,
    next_texture_key: u64,
}

impl Default for TextCache {
    fn default() -> Self {
        Self {
            lines: HashMap::new(),
            metrics: HashMap::new(),
            glyph_advances: HashMap::new(),
            kerns: HashMap::new(),
            fonts: HashMap::new(),
            next_texture_key: 1_u64 << 62,
        }
    }
}

impl TextCache {
    pub(crate) fn get_line(&self, key: &str) -> Option<&CachedText> {
        self.lines.get(key)
    }

    pub(crate) fn insert_line(&mut self, key: String, cached: CachedText) {
        self.insert(key, cached);
    }

    pub(crate) fn insert(&mut self, key: String, cached: CachedText) {
        self.lines.insert(key, cached);
    }

    pub(crate) fn len(&self) -> usize {
        self.lines.len()
    }

    pub(crate) fn remove(&mut self, key: &str) -> Option<CachedText> {
        self.lines.remove(key)
    }

    pub(crate) fn clear_layout_entries(&mut self) {
        self.lines.clear();
        self.metrics.clear();
        self.glyph_advances.clear();
        self.kerns.clear();
    }

    pub(crate) fn next_texture_key(&mut self) -> u64 {
        let texture_key = self.next_texture_key;
        self.next_texture_key = self.next_texture_key.saturating_add(1);
        texture_key
    }

    pub(crate) fn get_metrics(&self, key: &str) -> Option<&CachedTextMetrics> {
        self.metrics.get(key)
    }

    pub(crate) fn insert_metrics(&mut self, key: String, metrics: CachedTextMetrics) {
        self.metrics.insert(key, metrics);
    }

    pub(crate) fn get_glyph_advance(&self, key: &(String, usize, char)) -> Option<&(GlyphId, f32)> {
        self.glyph_advances.get(key)
    }

    pub(crate) fn insert_glyph_advance(
        &mut self,
        key: (String, usize, char),
        value: (GlyphId, f32),
    ) {
        self.glyph_advances.insert(key, value);
    }

    pub(crate) fn get_kern(&self, key: &(String, usize, GlyphId, GlyphId)) -> Option<&f32> {
        self.kerns.get(key)
    }

    pub(crate) fn insert_kern(&mut self, key: (String, usize, GlyphId, GlyphId), value: f32) {
        self.kerns.insert(key, value);
    }

    pub(crate) fn get_font(&self, path: &str) -> Option<&FontArc> {
        self.fonts.get(path)
    }

    pub(crate) fn insert_font(&mut self, path: String, font: FontArc) {
        self.fonts.insert(path, font);
    }
}
