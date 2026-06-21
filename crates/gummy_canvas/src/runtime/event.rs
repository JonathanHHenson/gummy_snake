use std::time::Instant;

#[derive(Clone, Debug)]
pub struct RuntimeEvent {
    pub event_type: &'static str,
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub dx: Option<f64>,
    pub dy: Option<f64>,
    pub button: Option<String>,
    pub scroll_x: Option<f64>,
    pub scroll_y: Option<f64>,
    pub modifiers: Option<u32>,
    pub key: Option<String>,
    pub code: Option<String>,
    pub text: Option<String>,
    pub width: Option<i64>,
    pub height: Option<i64>,
    pub pixel_density: Option<f64>,
    pub coordinates: Option<&'static str>,
    pub touch_id: Option<u64>,
    pub phase: Option<&'static str>,
    pub pressure: Option<f64>,
    pub timestamp: Option<f64>,
    pub device: Option<String>,
}

impl RuntimeEvent {
    pub(super) fn new(event_type: &'static str) -> Self {
        Self {
            event_type,
            x: None,
            y: None,
            dx: None,
            dy: None,
            button: None,
            scroll_x: None,
            scroll_y: None,
            modifiers: None,
            key: None,
            code: None,
            text: None,
            width: None,
            height: None,
            pixel_density: None,
            coordinates: None,
            touch_id: None,
            phase: None,
            pressure: None,
            timestamp: None,
            device: None,
        }
    }

    pub(super) fn close() -> Self {
        Self::new("close")
    }

    pub(super) fn resized(width: i64, height: i64, pixel_density: f64) -> Self {
        let mut event = Self::new("resized");
        event.width = Some(width);
        event.height = Some(height);
        event.pixel_density = Some(pixel_density);
        event
    }

    pub(super) fn mouse(
        event_type: &'static str,
        x: f64,
        y: f64,
        dx: f64,
        dy: f64,
        button: Option<String>,
        modifiers: u32,
    ) -> Self {
        let mut event = Self::new(event_type);
        event.x = Some(x);
        event.y = Some(y);
        event.dx = Some(dx);
        event.dy = Some(dy);
        event.button = button;
        event.modifiers = Some(modifiers);
        event
    }

    pub(super) fn mouse_wheel(
        x: f64,
        y: f64,
        scroll_x: f64,
        scroll_y: f64,
        modifiers: u32,
    ) -> Self {
        let mut event = Self::new("mouse_wheel");
        event.x = Some(x);
        event.y = Some(y);
        event.scroll_x = Some(scroll_x);
        event.scroll_y = Some(scroll_y);
        event.modifiers = Some(modifiers);
        event
    }

    pub(super) fn key(
        event_type: &'static str,
        key: Option<String>,
        code: Option<String>,
        modifiers: u32,
    ) -> Self {
        let mut event = Self::new(event_type);
        event.key = key;
        event.code = code;
        event.modifiers = Some(modifiers);
        event
    }

    pub(super) fn key_typed(text: String) -> Self {
        let mut event = Self::new("key_typed");
        event.text = Some(text);
        event
    }

    pub(super) fn touch(
        event_type: &'static str,
        touch_id: u64,
        x: f64,
        y: f64,
        phase: &'static str,
        pressure: Option<f64>,
    ) -> Self {
        let mut event = Self::new(event_type);
        event.touch_id = Some(touch_id);
        event.x = Some(x);
        event.y = Some(y);
        event.phase = Some(phase);
        event.pressure = pressure;
        event.timestamp = Some(Instant::now().elapsed().as_secs_f64());
        event
    }
}
