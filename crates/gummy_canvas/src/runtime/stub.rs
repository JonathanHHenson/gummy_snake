use std::time::Duration;

use crate::runtime::event::RuntimeEvent;

pub const DEFAULT_POINTER_LOCK_MODE: &str = "clamped";

pub struct InteractiveRuntime;

impl InteractiveRuntime {
    pub fn open(_width: i64, _height: i64) -> Result<Self, String> {
        Err("Native canvas window support is unavailable on this platform.".to_string())
    }

    pub fn native_window_available() -> bool {
        false
    }

    pub fn display_density(&self) -> f64 {
        1.0
    }

    pub fn logical_size(&self) -> (i64, i64) {
        (1, 1)
    }

    pub fn should_close(&self) -> bool {
        true
    }

    pub fn poll_events(&mut self) -> Result<Vec<RuntimeEvent>, String> {
        Ok(Vec::new())
    }

    pub fn present(
        &mut self,
        _rgba_pixels: &[u8],
        _physical_width: usize,
        _physical_height: usize,
    ) -> Result<(), String> {
        Ok(())
    }

    pub fn request_resize(
        &mut self,
        _logical_width: i64,
        _logical_height: i64,
        _pixel_density: f64,
    ) -> Result<(), String> {
        Ok(())
    }

    pub fn request_pointer_lock(&mut self) -> Result<bool, String> {
        Err("Pointer lock is unavailable without native canvas window support.".to_string())
    }

    pub fn exit_pointer_lock(&mut self) -> Result<bool, String> {
        Ok(true)
    }

    pub fn pointer_locked(&self) -> bool {
        false
    }

    pub fn set_pointer_lock_mode(&mut self, mode: &str) -> Result<(), String> {
        match mode {
            "unclamped" | "clamped" | "fixed" => Ok(()),
            _ => Err(format!(
                "Pointer lock mode must be 'unclamped', 'clamped', or 'fixed', got {mode:?}."
            )),
        }
    }

    pub fn pointer_lock_mode(&self) -> &'static str {
        DEFAULT_POINTER_LOCK_MODE
    }

    pub fn start_text_input(&mut self) -> Result<bool, String> {
        Err("Text input is unavailable without native canvas window support.".to_string())
    }

    pub fn stop_text_input(&mut self) -> Result<bool, String> {
        Ok(false)
    }

    pub fn text_input_active(&self) -> bool {
        false
    }

    pub fn resize_recently(&self, _within: Duration) -> bool {
        false
    }

    pub fn close(&mut self) {}
}

pub fn native_window_available() -> bool {
    InteractiveRuntime::native_window_available()
}
