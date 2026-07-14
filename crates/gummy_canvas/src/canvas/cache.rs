use crate::assets::{CachedImage, CachedText, CachedTextMetrics};
use crate::config::*;
use ab_glyph::{FontArc, GlyphId};
use std::collections::{HashMap, VecDeque};

#[derive(Debug)]
pub(crate) struct ImageCache {
    entries: HashMap<u64, CachedImage>,
    order: VecDeque<u64>,
    resident_bytes: usize,
    max_entries: usize,
    max_bytes: usize,
}

impl Default for ImageCache {
    fn default() -> Self {
        Self::with_limits(IMAGE_CACHE_LIMIT, IMAGE_CACHE_BYTE_LIMIT)
    }
}

impl ImageCache {
    pub(crate) fn with_limits(max_entries: usize, max_bytes: usize) -> Self {
        Self {
            entries: HashMap::new(),
            order: VecDeque::new(),
            resident_bytes: 0,
            max_entries,
            max_bytes,
        }
    }

    pub(crate) fn needs_update(&self, key: u64, version: u64, width: usize, height: usize) -> bool {
        self.entries
            .get(&key)
            .map(|cached| {
                cached.version != version || cached.width != width || cached.height != height
            })
            .unwrap_or(true)
    }

    pub(crate) fn get(&mut self, key: u64) -> Option<&CachedImage> {
        self.touch(key);
        self.entries.get(&key)
    }

    pub(crate) fn insert(&mut self, key: u64, image: CachedImage) -> (usize, usize, bool) {
        let incoming_bytes = image.pixels.len();
        if self.max_entries == 0 || incoming_bytes > self.max_bytes {
            return (0, 0, false);
        }
        self.remove_entry(key);
        let mut evictions = 0;
        let mut evicted_bytes = 0;
        while self.entries.len() >= self.max_entries
            || self.resident_bytes.saturating_add(incoming_bytes) > self.max_bytes
        {
            let Some(evicted_key) = self.order.pop_front() else {
                break;
            };
            if let Some(evicted) = self.entries.remove(&evicted_key) {
                let bytes = evicted.pixels.len();
                self.resident_bytes = self.resident_bytes.saturating_sub(bytes);
                evictions += 1;
                evicted_bytes += bytes;
            }
        }
        self.resident_bytes = self.resident_bytes.saturating_add(incoming_bytes);
        self.order.push_back(key);
        self.entries.insert(key, image);
        (evictions, evicted_bytes, true)
    }

    #[cfg(test)]
    pub(crate) fn len(&self) -> usize {
        self.entries.len()
    }

    pub(crate) fn resident_bytes(&self) -> usize {
        self.resident_bytes
    }

    pub(crate) fn max_bytes(&self) -> usize {
        self.max_bytes
    }

    fn touch(&mut self, key: u64) {
        if let Some(index) = self.order.iter().position(|candidate| *candidate == key) {
            self.order.remove(index);
            self.order.push_back(key);
        }
    }

    fn remove_entry(&mut self, key: u64) {
        if let Some(previous) = self.entries.remove(&key) {
            self.resident_bytes = self.resident_bytes.saturating_sub(previous.pixels.len());
        }
        if let Some(index) = self.order.iter().position(|candidate| *candidate == key) {
            self.order.remove(index);
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct TextureCacheEntry {
    pub(crate) version: u64,
    pub(crate) bytes: usize,
    pub(crate) is_atlas: bool,
}

#[derive(Debug)]
pub(crate) struct TextureCache {
    entries: HashMap<u64, TextureCacheEntry>,
    order: VecDeque<u64>,
    resident_bytes: usize,
    atlas_resident_bytes: usize,
    max_entries: usize,
    max_bytes: usize,
}

impl Default for TextureCache {
    fn default() -> Self {
        Self::with_limits(TEXTURE_CACHE_LIMIT, TEXTURE_CACHE_BYTE_LIMIT)
    }
}

impl TextureCache {
    pub(crate) fn with_limits(max_entries: usize, max_bytes: usize) -> Self {
        Self {
            entries: HashMap::new(),
            order: VecDeque::new(),
            resident_bytes: 0,
            atlas_resident_bytes: 0,
            max_entries,
            max_bytes,
        }
    }

    pub(crate) fn version(&mut self, key: u64) -> Option<u64> {
        self.touch(key);
        self.entries.get(&key).map(|entry| entry.version)
    }

    pub(crate) fn insert(
        &mut self,
        key: u64,
        version: u64,
        bytes: usize,
        is_atlas: bool,
    ) -> Option<TextureCacheEntry> {
        let previous = self.remove(key);
        self.entries.insert(
            key,
            TextureCacheEntry {
                version,
                bytes,
                is_atlas,
            },
        );
        self.order.push_back(key);
        self.resident_bytes = self.resident_bytes.saturating_add(bytes);
        if is_atlas {
            self.atlas_resident_bytes = self.atlas_resident_bytes.saturating_add(bytes);
        }
        previous
    }

    #[cfg(test)]
    pub(crate) fn contains_key(&self, key: &u64) -> bool {
        self.entries.contains_key(key)
    }

    pub(crate) fn remove(&mut self, key: u64) -> Option<TextureCacheEntry> {
        let removed = self.entries.remove(&key)?;
        self.resident_bytes = self.resident_bytes.saturating_sub(removed.bytes);
        if removed.is_atlas {
            self.atlas_resident_bytes = self.atlas_resident_bytes.saturating_sub(removed.bytes);
        }
        if let Some(index) = self.order.iter().position(|candidate| *candidate == key) {
            self.order.remove(index);
        }
        Some(removed)
    }

    pub(crate) fn needs_eviction(&self, incoming_key: u64, incoming_bytes: usize) -> bool {
        let previous = self.entries.get(&incoming_key);
        let entry_count = self.entries.len() - usize::from(previous.is_some());
        let resident_bytes = self
            .resident_bytes
            .saturating_sub(previous.map_or(0, |entry| entry.bytes));
        entry_count >= self.max_entries
            || resident_bytes.saturating_add(incoming_bytes) > self.max_bytes
    }

    pub(crate) fn oldest_key_except(&self, excluded_key: u64) -> Option<u64> {
        self.order
            .iter()
            .copied()
            .find(|candidate| *candidate != excluded_key)
    }

    pub(crate) fn touch(&mut self, key: u64) {
        if let Some(index) = self.order.iter().position(|candidate| *candidate == key) {
            self.order.remove(index);
            self.order.push_back(key);
        }
    }

    pub(crate) fn len(&self) -> usize {
        self.entries.len()
    }

    pub(crate) fn resident_bytes(&self) -> usize {
        self.resident_bytes
    }

    pub(crate) fn atlas_resident_bytes(&self) -> usize {
        self.atlas_resident_bytes
    }

    pub(crate) fn max_bytes(&self) -> usize {
        self.max_bytes
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
