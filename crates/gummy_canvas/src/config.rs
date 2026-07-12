//! Internal canvas-runtime configuration shared by focused implementation modules.
//!
//! These values are intentionally crate-private. Python-visible capability and ABI
//! names are registered by `bindings` from the crate root.

pub(crate) const SUPPORTED_RENDERER: &str = "p2d";
pub(crate) const SUPPORTED_RENDERERS: &[&str] = &[SUPPORTED_RENDERER, "webgl", "webgpu"];
pub(crate) const SUPPORTED_MODE: &str = "headless";
pub(crate) const INTERACTIVE_MODE: &str = "interactive";
pub(crate) const BLEND_MODE_BLEND: &str = "blend";
pub(crate) const BLEND_MODE_ADD: &str = "add";
pub(crate) const BLEND_MODE_DARKEST: &str = "darkest";
pub(crate) const BLEND_MODE_LIGHTEST: &str = "lightest";
pub(crate) const BLEND_MODE_DIFFERENCE: &str = "difference";
pub(crate) const BLEND_MODE_EXCLUSION: &str = "exclusion";
pub(crate) const BLEND_MODE_MULTIPLY: &str = "multiply";
pub(crate) const BLEND_MODE_REPLACE: &str = "replace";
pub(crate) const BLEND_MODE_SCREEN: &str = "screen";
pub(crate) const IMAGE_CACHE_LIMIT: usize = 1024;
pub(crate) const TEXTURE_CACHE_LIMIT: usize = 1024;
pub(crate) const TEXT_CACHE_LIMIT: usize = 512;
