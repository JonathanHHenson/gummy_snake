mod events;
mod input;

use std::sync::Arc;
use std::time::{Duration, Instant};

use sdl3::keyboard::Mod;
use sdl3::video::Window;
use sdl3::{EventPump, Sdl, VideoSubsystem};

use crate::runtime::event::RuntimeEvent;

const LIVE_RESIZE_EVENT_COOLDOWN: Duration = Duration::from_millis(80);
const WINDOW_TITLE: &str = "Gummy Snake";
const DOUBLE_CLICK_INTERVAL: Duration = Duration::from_millis(500);
const DOUBLE_CLICK_DISTANCE: f64 = 6.0;
pub const DEFAULT_POINTER_LOCK_MODE: &str = "clamped";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PointerLockMode {
    Unclamped,
    Clamped,
    Fixed,
}

impl PointerLockMode {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "unclamped" => Ok(Self::Unclamped),
            "clamped" => Ok(Self::Clamped),
            "fixed" => Ok(Self::Fixed),
            _ => Err(format!(
                "Pointer lock mode must be 'unclamped', 'clamped', or 'fixed', got {value:?}."
            )),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Unclamped => "unclamped",
            Self::Clamped => "clamped",
            Self::Fixed => "fixed",
        }
    }
}

pub struct InteractiveRuntime {
    _sdl: Sdl,
    _video: VideoSubsystem,
    event_pump: EventPump,
    window: Option<Arc<Window>>,
    window_id: u32,
    events: Vec<RuntimeEvent>,
    logical_width: i64,
    logical_height: i64,
    pixel_density: f64,
    physical_width: u32,
    physical_height: u32,
    cursor_position: Option<(f64, f64)>,
    modifiers: Mod,
    pressed_button: Option<String>,
    last_click: Option<ClickState>,
    pointer_locked: bool,
    pointer_lock_mode: PointerLockMode,
    mouse_inside_window: bool,
    text_input_active: bool,
    closed: bool,
    has_close_event: bool,
    last_resize_at: Option<Instant>,
}

impl InteractiveRuntime {
    pub fn open(width: i64, height: i64) -> Result<Self, String> {
        let sdl = sdl3::init().map_err(|err| format!("Failed to initialize SDL3: {err}"))?;
        let video = sdl
            .video()
            .map_err(|err| format!("Failed to initialize SDL3 video: {err}"))?;
        let mut window = video.window(WINDOW_TITLE, width.max(1) as u32, height.max(1) as u32);
        window.position_centered().resizable().high_pixel_density();
        #[cfg(target_os = "macos")]
        window.metal_view();
        let window = window
            .build()
            .map_err(|err| format!("Failed to create SDL3 native canvas window: {err}"))?;
        let _ = window.sync();
        let window_id = window.id();
        let event_pump = sdl
            .event_pump()
            .map_err(|err| format!("Failed to create SDL3 event pump: {err}"))?;
        let mut runtime = Self {
            _sdl: sdl,
            _video: video,
            event_pump,
            window: Some(Arc::new(window)),
            window_id,
            events: Vec::new(),
            logical_width: width.max(1),
            logical_height: height.max(1),
            pixel_density: 1.0,
            physical_width: width.max(1) as u32,
            physical_height: height.max(1) as u32,
            cursor_position: None,
            modifiers: Mod::NOMOD,
            pressed_button: None,
            last_click: None,
            pointer_locked: false,
            pointer_lock_mode: PointerLockMode::Clamped,
            mouse_inside_window: false,
            text_input_active: false,
            closed: false,
            has_close_event: false,
            last_resize_at: None,
        };
        runtime.refresh_window_metrics(true);
        Ok(runtime)
    }

    pub fn native_window_available() -> bool {
        true
    }

    pub fn display_density(&self) -> f64 {
        self.pixel_density.max(1.0)
    }

    pub fn should_close(&self) -> bool {
        self.closed
    }

    pub fn poll_events(&mut self) -> Result<Vec<RuntimeEvent>, String> {
        self.pump_events()?;
        if self.resize_recently(LIVE_RESIZE_EVENT_COOLDOWN) {
            return Ok(self.drain_events_except_resize());
        }
        Ok(self.drain_events())
    }

    pub fn request_resize(
        &mut self,
        logical_width: i64,
        logical_height: i64,
        pixel_density: f64,
    ) -> Result<(), String> {
        self.logical_width = logical_width.max(1);
        self.logical_height = logical_height.max(1);
        self.pixel_density = pixel_density.max(1.0);
        if let Some(window) = self.window.as_mut().and_then(Arc::get_mut) {
            let current_size = window.size();
            if current_size != (self.logical_width as u32, self.logical_height as u32) {
                window
                    .set_size(self.logical_width as u32, self.logical_height as u32)
                    .map_err(|err| format!("Failed to resize SDL3 native canvas window: {err}"))?;
                let _ = window.sync();
            }
        }
        self.refresh_window_metrics(true);
        Ok(())
    }

    pub fn close(&mut self) {
        self.closed = true;
        if !self.has_close_event {
            self.has_close_event = true;
            self.events.push(RuntimeEvent::close());
        }
        self.release_pointer_lock();
        self.stop_text_input_internal();
        self.window = None;
    }

    pub fn request_pointer_lock(&mut self) -> Result<bool, String> {
        let Some(window) = self.window.as_mut().and_then(Arc::get_mut) else {
            return Err("Native canvas window is not available for pointer lock.".to_string());
        };
        if !window.set_mouse_grab(true) {
            return Err("Failed to grab SDL3 native canvas mouse input.".to_string());
        }
        let mouse = self._sdl.mouse();
        mouse.capture(true);
        mouse.show_cursor(false);
        mouse.set_relative_mouse_mode(window, true);
        let _ = self.event_pump.relative_mouse_state();
        self.pointer_locked = true;
        self.cursor_position = Some(self.initial_locked_position());
        Ok(true)
    }

    pub fn exit_pointer_lock(&mut self) -> Result<bool, String> {
        self.release_pointer_lock();
        Ok(true)
    }

    pub fn pointer_locked(&self) -> bool {
        self.pointer_locked
    }

    pub fn set_pointer_lock_mode(&mut self, mode: &str) -> Result<(), String> {
        self.pointer_lock_mode = PointerLockMode::parse(mode)?;
        if self.pointer_locked {
            self.cursor_position = Some(
                self.apply_pointer_lock_mode(
                    self.cursor_position
                        .unwrap_or_else(|| self.center_position()),
                ),
            );
        }
        Ok(())
    }

    pub fn pointer_lock_mode(&self) -> &'static str {
        self.pointer_lock_mode.as_str()
    }

    pub fn start_text_input(&mut self) -> Result<bool, String> {
        let Some(window) = self.window.as_ref() else {
            return Err("Native canvas window is not available for text input.".to_string());
        };
        self._video.text_input().start(window);
        self.text_input_active = true;
        Ok(true)
    }

    pub fn stop_text_input(&mut self) -> Result<bool, String> {
        self.stop_text_input_internal();
        Ok(true)
    }

    pub fn text_input_active(&self) -> bool {
        self.text_input_active
    }

    pub fn window(&self) -> Option<Arc<Window>> {
        self.window.as_ref().map(Arc::clone)
    }

    pub fn physical_size(&self) -> (u32, u32) {
        (self.physical_width.max(1), self.physical_height.max(1))
    }

    pub fn resize_recently(&self, within: Duration) -> bool {
        self.last_resize_at
            .map(|instant| instant.elapsed() <= within)
            .unwrap_or(false)
    }

    fn refresh_window_metrics(&mut self, initial: bool) {
        let Some(window) = self.window.as_ref() else {
            return;
        };
        self.pixel_density = f64::from(window.display_scale()).max(1.0);
        let (physical_width, physical_height) = window.size_in_pixels();
        self.physical_width = physical_width.max(1);
        self.physical_height = physical_height.max(1);
        let (logical_width, logical_height) = window.size();
        self.logical_width = i64::from(logical_width.max(1));
        self.logical_height = i64::from(logical_height.max(1));
        if !initial && (physical_width == 0 || physical_height == 0) {
            self.physical_width = 1;
            self.physical_height = 1;
        }
    }

    fn release_pointer_lock(&mut self) {
        let Some(window) = self.window.as_mut().and_then(Arc::get_mut) else {
            self.pointer_locked = false;
            return;
        };
        let mouse = self._sdl.mouse();
        if mouse.relative_mouse_mode(window) {
            mouse.set_relative_mouse_mode(window, false);
        }
        mouse.capture(false);
        mouse.show_cursor(true);
        window.set_mouse_grab(false);
        self.pointer_locked = false;
    }

    fn stop_text_input_internal(&mut self) {
        if self.text_input_active {
            if let Some(window) = self.window.as_ref() {
                self._video.text_input().stop(window);
            }
        }
        self.text_input_active = false;
    }
}

#[derive(Clone)]
struct ClickState {
    button: Option<String>,
    x: f64,
    y: f64,
    when: Instant,
}

pub fn native_window_available() -> bool {
    InteractiveRuntime::native_window_available()
}
