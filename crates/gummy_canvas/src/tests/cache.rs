use crate::*;

#[test]
fn cached_images_are_bounded() {
    let mut canvas = Canvas::new(1, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    for key in 0..(IMAGE_CACHE_LIMIT as u64 + 3) {
        canvas.evict_image_cache_if_needed(key);
        canvas.image_cache.insert(
            key,
            CachedImage {
                version: 0,
                width: 1,
                height: 1,
                pixels: vec![key as u8, 0, 0, 255],
            },
        );
    }

    assert!(canvas.image_cache.len() <= IMAGE_CACHE_LIMIT);
}

#[test]
fn cached_text_entries_are_bounded_and_report_evictions() {
    let mut canvas = Canvas::new(1, 1, 1.0, SUPPORTED_MODE, SUPPORTED_RENDERER).unwrap();
    for index in 0..(TEXT_CACHE_LIMIT + 3) {
        canvas.evict_text_cache_if_needed();
        let texture_key = 1_000 + index as u64;
        let cache_key = format!("text-{index}");
        canvas.texture_cache_versions.insert(texture_key, 0);
        canvas.text_cache_order.push_back(cache_key.clone());
        canvas.text_cache.insert(
            cache_key,
            CachedText {
                texture_key,
                image: CachedImage {
                    version: 0,
                    width: 1,
                    height: 1,
                    pixels: vec![255, 255, 255, 255],
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
