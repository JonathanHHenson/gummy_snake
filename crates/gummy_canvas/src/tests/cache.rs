use crate::assets::{CachedImage, CachedText};
use crate::canvas::cache::{ImageCache, TextureCache};
use crate::canvas_state::Canvas;
use crate::config::*;
use std::sync::Arc;

#[test]
fn cached_images_are_bounded() {
    let mut canvas = Canvas::new(1, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    for key in 0..(IMAGE_CACHE_LIMIT as u64 + 3) {
        canvas.insert_image_cache_entry(
            key,
            CachedImage {
                version: 0,
                width: 1,
                height: 1,
                pixels: Arc::new(vec![key as u8, 0, 0, 255]),
            },
        );
    }

    assert!(canvas.image_cache.len() <= IMAGE_CACHE_LIMIT);
    assert_eq!(canvas.performance_counters.image_cache_evictions, 3);
    assert_eq!(
        canvas.performance_counters.image_cache_resident_bytes,
        (IMAGE_CACHE_LIMIT * 4) as u64
    );
}

#[test]
fn cached_text_entries_are_bounded_and_report_evictions() {
    let mut canvas = Canvas::new(1, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    for index in 0..(TEXT_CACHE_LIMIT + 3) {
        canvas.evict_text_cache_if_needed();
        let texture_key = 1_000 + index as u64;
        let cache_key = format!("text-{index}");
        canvas
            .texture_cache_versions
            .insert(texture_key, 0, 4, false);
        canvas.text_cache_order.push_back(cache_key.clone());
        canvas.text_cache.insert(
            cache_key,
            CachedText {
                texture_key,
                image: CachedImage {
                    version: 0,
                    width: 1,
                    height: 1,
                    pixels: Arc::new(vec![255, 255, 255, 255]),
                },
                bbox_left: 0,
                bbox_top: 0,
                ascent: 1.0,
            },
        );
    }

    assert_eq!(canvas.text_cache.len(), TEXT_CACHE_LIMIT);
    assert_eq!(canvas.text_cache_order.len(), TEXT_CACHE_LIMIT);
    assert_eq!(canvas.performance_counters.text_cache_evictions, 3);
    assert!(!canvas.texture_cache_versions.contains_key(&1_000));
}

#[test]
fn image_cache_uses_shared_payloads_and_evicts_by_bytes() {
    let mut cache = ImageCache::with_limits(8, 8);
    let first = Arc::new(vec![1, 2, 3, 4]);
    let second = Arc::new(vec![5, 6, 7, 8]);
    let third = Arc::new(vec![9, 10, 11, 12]);

    let (_, _, inserted) = cache.insert(
        1,
        CachedImage {
            version: 0,
            width: 1,
            height: 1,
            pixels: Arc::clone(&first),
        },
    );
    assert!(inserted);
    assert!(Arc::ptr_eq(&cache.get(1).unwrap().pixels, &first));
    cache.insert(
        2,
        CachedImage {
            version: 0,
            width: 1,
            height: 1,
            pixels: second,
        },
    );
    let (evictions, evicted_bytes, inserted) = cache.insert(
        3,
        CachedImage {
            version: 0,
            width: 1,
            height: 1,
            pixels: third,
        },
    );

    assert!(inserted);
    assert_eq!(evictions, 1);
    assert_eq!(evicted_bytes, 4);
    assert_eq!(cache.resident_bytes(), 8);
    assert!(cache.get(1).is_none());
}

#[test]
fn texture_cache_tracks_byte_budget_and_atlas_residency() {
    let mut cache = TextureCache::with_limits(8, 8);
    cache.insert(1, 0, 4, false);
    cache.insert(2, 0, 4, true);

    assert_eq!(cache.resident_bytes(), 8);
    assert_eq!(cache.atlas_resident_bytes(), 4);
    assert!(cache.needs_eviction(3, 4));
    assert_eq!(cache.oldest_key_except(3), Some(1));

    let evicted = cache.remove(1).unwrap();
    assert_eq!(evicted.bytes, 4);
    assert!(!evicted.is_atlas);
    assert!(!cache.needs_eviction(3, 4));
    cache.insert(3, 0, 4, false);

    assert_eq!(cache.resident_bytes(), 8);
    assert_eq!(cache.atlas_resident_bytes(), 4);
}
