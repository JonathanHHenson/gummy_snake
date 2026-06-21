use std::sync::Arc;
use std::time::{Duration, Instant};

use sdl3::event::{Event, WindowEvent};
use sdl3::keyboard::{Keycode, Mod, Scancode};
use sdl3::mouse::{MouseButton, MouseWheelDirection};
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

    pub fn logical_size(&self) -> (i64, i64) {
        (self.logical_width, self.logical_height)
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

    pub(crate) fn pump_events(&mut self) -> Result<(), String> {
        let events: Vec<Event> = self.event_pump.poll_iter().collect();
        for event in events {
            self.handle_event(event);
        }
        Ok(())
    }

    fn handle_event(&mut self, event: Event) {
        match event {
            Event::Quit { .. } => self.push_close(),
            Event::Window {
                window_id,
                win_event,
                ..
            } if window_id == self.window_id => self.handle_window_event(win_event),
            Event::MouseMotion {
                window_id,
                x,
                y,
                xrel,
                yrel,
                ..
            } if window_id == self.window_id => self.push_cursor_event(x, y, xrel, yrel),
            Event::MouseButtonDown {
                window_id,
                mouse_btn,
                clicks,
                x,
                y,
                ..
            } if window_id == self.window_id => {
                let (event_x, event_y) = self.push_mouse_button("mouse_pressed", mouse_btn, x, y);
                if clicks >= 2 {
                    self.events.push(RuntimeEvent::logical_mouse(
                        "mouse_double_clicked",
                        event_x,
                        event_y,
                        0.0,
                        0.0,
                        normalize_mouse_button(mouse_btn),
                        modifiers_mask(self.modifiers),
                    ));
                }
            }
            Event::MouseButtonUp {
                window_id,
                mouse_btn,
                x,
                y,
                ..
            } if window_id == self.window_id => {
                let button = normalize_mouse_button(mouse_btn);
                let (event_x, event_y) = self.push_mouse_button("mouse_released", mouse_btn, x, y);
                self.push_click_events(button, event_x, event_y);
            }
            Event::MouseWheel {
                window_id,
                x,
                y,
                direction,
                mouse_x,
                mouse_y,
                ..
            } if window_id == self.window_id => {
                self.push_mouse_wheel(x, y, direction, mouse_x, mouse_y)
            }
            Event::KeyDown {
                window_id,
                keycode,
                scancode,
                keymod,
                repeat,
                ..
            } if window_id == self.window_id => {
                self.modifiers = keymod;
                if !repeat {
                    self.push_key_event("key_pressed", keycode, scancode);
                }
            }
            Event::KeyUp {
                window_id,
                keycode,
                scancode,
                keymod,
                ..
            } if window_id == self.window_id => {
                self.modifiers = keymod;
                self.push_key_event("key_released", keycode, scancode);
            }
            Event::TextInput {
                window_id, text, ..
            } if window_id == self.window_id && self.text_input_active && !text.is_empty() => {
                self.events.push(RuntimeEvent::key_typed(text));
            }
            Event::FingerDown {
                window_id,
                finger_id,
                x,
                y,
                pressure,
                ..
            } if window_id == self.window_id => {
                self.push_touch_event("touch_started", finger_id, x, y, "started", pressure)
            }
            Event::FingerMotion {
                window_id,
                finger_id,
                x,
                y,
                pressure,
                ..
            } if window_id == self.window_id => {
                self.push_touch_event("touch_moved", finger_id, x, y, "moved", pressure)
            }
            Event::FingerUp {
                window_id,
                finger_id,
                x,
                y,
                pressure,
                ..
            } if window_id == self.window_id => {
                self.push_touch_event("touch_ended", finger_id, x, y, "ended", pressure)
            }
            _ => {}
        }
    }

    fn handle_window_event(&mut self, event: WindowEvent) {
        match event {
            WindowEvent::CloseRequested => self.push_close(),
            WindowEvent::Resized(_, _)
            | WindowEvent::PixelSizeChanged(_, _)
            | WindowEvent::DisplayChanged(_) => self.handle_resize(),
            WindowEvent::FocusLost => {
                self.release_pointer_lock();
                self.set_mouse_inside_window(false);
            }
            WindowEvent::MouseEnter => self.set_mouse_inside_window(true),
            WindowEvent::MouseLeave if !self.pointer_locked => {
                self.cursor_position = None;
                self.set_mouse_inside_window(false);
            }
            WindowEvent::MouseLeave => {}
            _ => {}
        }
    }

    fn handle_resize(&mut self) {
        self.refresh_window_metrics(false);
        self.last_resize_at = Some(Instant::now());
        self.events.retain(|event| event.event_type != "resized");
        self.events.push(RuntimeEvent::resized(
            self.logical_width,
            self.logical_height,
            self.pixel_density,
        ));
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

    fn push_close(&mut self) {
        self.closed = true;
        if !self.has_close_event {
            self.has_close_event = true;
            self.events.push(RuntimeEvent::close());
        }
        self.release_pointer_lock();
        self.stop_text_input_internal();
        self.window = None;
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

    fn set_mouse_inside_window(&mut self, inside_window: bool) {
        self.mouse_inside_window = inside_window;
        self.events
            .push(RuntimeEvent::mouse_window_state(inside_window));
    }

    fn drain_events(&mut self) -> Vec<RuntimeEvent> {
        std::mem::take(&mut self.events)
    }

    fn drain_events_except_resize(&mut self) -> Vec<RuntimeEvent> {
        let mut drained = Vec::new();
        let mut retained = Vec::new();
        for event in self.events.drain(..) {
            if event.event_type == "resized" {
                retained.push(event);
            } else {
                drained.push(event);
            }
        }
        self.events = retained;
        drained
    }

    fn push_cursor_event(&mut self, x: f32, y: f32, xrel: f32, yrel: f32) {
        self.mouse_inside_window = true;
        let (event_x, event_y) = if self.pointer_locked {
            let previous = self
                .cursor_position
                .unwrap_or_else(|| self.initial_locked_position());
            self.apply_pointer_lock_mode((previous.0 + xrel as f64, previous.1 + yrel as f64))
        } else {
            (x as f64, y as f64)
        };
        self.cursor_position = Some((event_x, event_y));
        let event_type = if self.pressed_button.is_some() {
            "mouse_dragged"
        } else {
            "mouse_moved"
        };
        self.events.push(RuntimeEvent::logical_mouse(
            event_type,
            event_x,
            event_y,
            xrel as f64,
            yrel as f64,
            self.pressed_button.clone(),
            modifiers_mask(self.modifiers),
        ));
    }

    fn push_mouse_button(
        &mut self,
        event_type: &'static str,
        button: MouseButton,
        x: f32,
        y: f32,
    ) -> (f64, f64) {
        self.mouse_inside_window = true;
        let (event_x, event_y) = self.mouse_event_position(x, y);
        let button_name = normalize_mouse_button(button);
        if event_type == "mouse_pressed" {
            self.pressed_button = button_name.clone();
        } else if event_type == "mouse_released" {
            self.pressed_button = None;
        }
        self.cursor_position = Some((event_x, event_y));
        self.events.push(RuntimeEvent::logical_mouse(
            event_type,
            event_x,
            event_y,
            0.0,
            0.0,
            button_name,
            modifiers_mask(self.modifiers),
        ));
        (event_x, event_y)
    }

    fn push_mouse_wheel(
        &mut self,
        x: f32,
        y: f32,
        direction: MouseWheelDirection,
        mouse_x: f32,
        mouse_y: f32,
    ) {
        self.mouse_inside_window = true;
        let multiplier = match direction {
            MouseWheelDirection::Flipped => -1.0,
            _ => 1.0,
        };
        let (event_x, event_y) = self.mouse_event_position(mouse_x, mouse_y);
        self.events.push(RuntimeEvent::logical_mouse_wheel(
            event_x,
            event_y,
            x as f64 * multiplier,
            y as f64 * multiplier,
            modifiers_mask(self.modifiers),
        ));
    }

    fn push_click_events(&mut self, button_name: Option<String>, x: f64, y: f64) {
        self.events.push(RuntimeEvent::logical_mouse(
            "mouse_clicked",
            x,
            y,
            0.0,
            0.0,
            button_name.clone(),
            modifiers_mask(self.modifiers),
        ));
        if self.is_double_click(&button_name, x, y) {
            self.events.push(RuntimeEvent::logical_mouse(
                "mouse_double_clicked",
                x,
                y,
                0.0,
                0.0,
                button_name.clone(),
                modifiers_mask(self.modifiers),
            ));
        }
        self.last_click = Some(ClickState {
            button: button_name,
            x,
            y,
            when: Instant::now(),
        });
    }

    fn mouse_event_position(&self, x: f32, y: f32) -> (f64, f64) {
        if self.pointer_locked {
            self.cursor_position
                .unwrap_or_else(|| self.initial_locked_position())
        } else {
            (x as f64, y as f64)
        }
    }

    fn initial_locked_position(&self) -> (f64, f64) {
        match self.pointer_lock_mode {
            PointerLockMode::Fixed => self.center_position(),
            PointerLockMode::Clamped => self
                .cursor_position
                .map(|position| self.clamp_to_window(position))
                .unwrap_or_else(|| self.center_position()),
            PointerLockMode::Unclamped => self
                .cursor_position
                .unwrap_or_else(|| self.center_position()),
        }
    }

    fn apply_pointer_lock_mode(&self, position: (f64, f64)) -> (f64, f64) {
        match self.pointer_lock_mode {
            PointerLockMode::Unclamped => position,
            PointerLockMode::Clamped => self.clamp_to_window(position),
            PointerLockMode::Fixed => self.center_position(),
        }
    }

    fn clamp_to_window(&self, position: (f64, f64)) -> (f64, f64) {
        (
            position.0.clamp(0.0, self.logical_width as f64),
            position.1.clamp(0.0, self.logical_height as f64),
        )
    }

    fn center_position(&self) -> (f64, f64) {
        (
            self.logical_width as f64 / 2.0,
            self.logical_height as f64 / 2.0,
        )
    }

    fn is_double_click(&self, button: &Option<String>, x: f64, y: f64) -> bool {
        let Some(last_click) = self.last_click.as_ref() else {
            return false;
        };
        let Some(button_name) = button.as_ref() else {
            return false;
        };
        if last_click.button.as_deref() != Some(button_name.as_str()) {
            return false;
        }
        if last_click.when.elapsed() > DOUBLE_CLICK_INTERVAL {
            return false;
        }
        let dx = x - last_click.x;
        let dy = y - last_click.y;
        (dx * dx + dy * dy).sqrt() <= DOUBLE_CLICK_DISTANCE
    }

    fn push_key_event(
        &mut self,
        event_type: &'static str,
        keycode: Option<Keycode>,
        scancode: Option<Scancode>,
    ) {
        self.events.push(RuntimeEvent::key(
            event_type,
            keycode.map(normalize_key_name),
            scancode.map(|code| format!("{code:?}")),
            modifiers_mask(self.modifiers),
        ));
    }

    fn push_touch_event(
        &mut self,
        event_type: &'static str,
        touch_id: u64,
        x: f32,
        y: f32,
        phase: &'static str,
        pressure: f32,
    ) {
        let logical_x = x as f64 * self.logical_width as f64;
        let logical_y = y as f64 * self.logical_height as f64;
        self.events.push(RuntimeEvent::logical_touch(
            event_type,
            touch_id,
            logical_x,
            logical_y,
            phase,
            Some(pressure.clamp(0.0, 1.0) as f64),
        ));
    }
}

#[derive(Clone)]
struct ClickState {
    button: Option<String>,
    x: f64,
    y: f64,
    when: Instant,
}

fn normalize_key_name(keycode: Keycode) -> String {
    let text = keycode.to_string();
    if text.chars().count() == 1 {
        text.to_lowercase()
    } else {
        text
    }
}

fn normalize_mouse_button(button: MouseButton) -> Option<String> {
    match button {
        MouseButton::Left => Some("left".to_string()),
        MouseButton::Middle => Some("center".to_string()),
        MouseButton::Right => Some("right".to_string()),
        MouseButton::X1 => Some("4".to_string()),
        MouseButton::X2 => Some("5".to_string()),
        MouseButton::Unknown => None,
    }
}

fn modifiers_mask(modifiers: Mod) -> u32 {
    let mut value = 0_u32;
    if modifiers.intersects(Mod::LSHIFTMOD | Mod::RSHIFTMOD) {
        value |= 1;
    }
    if modifiers.intersects(Mod::LCTRLMOD | Mod::RCTRLMOD) {
        value |= 2;
    }
    if modifiers.intersects(Mod::LALTMOD | Mod::RALTMOD) {
        value |= 4;
    }
    if modifiers.intersects(Mod::LGUIMOD | Mod::RGUIMOD) {
        value |= 8;
    }
    value
}

pub fn native_window_available() -> bool {
    InteractiveRuntime::native_window_available()
}
