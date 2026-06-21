use crate::runtime::event::RuntimeEvent;

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

    pub fn close(&mut self) {}
}

pub fn native_window_available() -> bool {
    InteractiveRuntime::native_window_available()
}
