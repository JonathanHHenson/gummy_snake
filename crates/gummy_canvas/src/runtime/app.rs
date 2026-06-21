mod handler;

use std::sync::Arc;
use std::time::{Duration, Instant};

use winit::dpi::{LogicalSize, PhysicalPosition, PhysicalSize, Size};
use winit::event::{ElementState, MouseButton, TouchPhase};
use winit::keyboard::ModifiersState;
use winit::window::{Window, WindowId};

use crate::runtime::event::RuntimeEvent;
use crate::runtime::input::{
    modifiers_mask, normalize_mouse_button, touch_phase_name, touch_pressure,
};

const DOUBLE_CLICK_INTERVAL: Duration = Duration::from_millis(500);
const DOUBLE_CLICK_DISTANCE: f64 = 6.0;
pub(super) struct RuntimeApp {
    pub(super) logical_width: i64,
    pub(super) logical_height: i64,
    pub(super) pixel_density: f64,
    pub(super) physical_width: u32,
    pub(super) physical_height: u32,
    pub(super) window_id: Option<WindowId>,
    pub(super) window: Option<Arc<Window>>,
    pub(super) events: Vec<RuntimeEvent>,
    pub(super) cursor_position: Option<PhysicalPosition<f64>>,
    pub(super) modifiers: ModifiersState,
    pub(super) pressed_button: Option<String>,
    pub(super) last_click: Option<ClickState>,
    pub(super) active_touches: Vec<u64>,
    pub(super) closed: bool,
    pub(super) has_close_event: bool,
    pub(super) last_resize_at: Option<Instant>,
}

impl RuntimeApp {
    pub(super) fn new(logical_width: i64, logical_height: i64) -> Self {
        Self {
            logical_width,
            logical_height,
            pixel_density: 1.0,
            physical_width: logical_width.max(1) as u32,
            physical_height: logical_height.max(1) as u32,
            window_id: None,
            window: None,
            events: Vec::new(),
            cursor_position: None,
            modifiers: ModifiersState::default(),
            pressed_button: None,
            last_click: None,
            active_touches: Vec::new(),
            closed: false,
            has_close_event: false,
            last_resize_at: None,
        }
    }

    pub(super) fn drain_events(&mut self) -> Vec<RuntimeEvent> {
        std::mem::take(&mut self.events)
    }

    pub(super) fn drain_events_except_resize(&mut self) -> Vec<RuntimeEvent> {
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

    pub(super) fn request_resize(
        &mut self,
        logical_width: i64,
        logical_height: i64,
        pixel_density: f64,
    ) -> Result<(), String> {
        self.logical_width = logical_width;
        self.logical_height = logical_height;
        self.pixel_density = pixel_density;
        if let Some(window) = self.window.as_ref() {
            let current_size = window.inner_size();
            let expected_width = (logical_width as f64 * pixel_density).round().max(1.0) as u32;
            let expected_height = (logical_height as f64 * pixel_density).round().max(1.0) as u32;
            if current_size.width != expected_width || current_size.height != expected_height {
                let requested = window.request_inner_size(Size::Logical(LogicalSize::new(
                    logical_width as f64,
                    logical_height as f64,
                )));
                if let Some(size) = requested {
                    self.handle_resize(size)?;
                }
            }
        }
        Ok(())
    }

    pub(super) fn handle_resize(&mut self, size: PhysicalSize<u32>) -> Result<(), String> {
        if size.width == 0 || size.height == 0 {
            return Ok(());
        }
        self.physical_width = size.width;
        self.physical_height = size.height;
        self.last_resize_at = Some(Instant::now());
        if let Some(window) = self.window.as_ref() {
            self.pixel_density = window.scale_factor().max(1.0);
            let logical_size = size.to_logical::<f64>(self.pixel_density);
            self.logical_width = logical_size.width.round().max(1.0) as i64;
            self.logical_height = logical_size.height.round().max(1.0) as i64;
        }
        self.push_resize_event();
        Ok(())
    }

    fn push_resize_event(&mut self) {
        self.events.retain(|event| event.event_type != "resized");
        self.events.push(RuntimeEvent::resized(
            self.logical_width,
            self.logical_height,
            self.pixel_density,
        ));
    }

    pub(super) fn push_cursor_event(&mut self, position: PhysicalPosition<f64>) {
        let previous = self.cursor_position.unwrap_or(position);
        self.cursor_position = Some(position);
        let event_type = if self.pressed_button.is_some() {
            "mouse_dragged"
        } else {
            "mouse_moved"
        };
        self.events.push(RuntimeEvent::mouse(
            event_type,
            position.x,
            position.y,
            position.x - previous.x,
            position.y - previous.y,
            self.pressed_button.clone(),
            modifiers_mask(self.modifiers),
        ));
    }

    pub(super) fn push_mouse_button(&mut self, button: MouseButton, state: ElementState) {
        let button_name = normalize_mouse_button(button);
        let position = self
            .cursor_position
            .unwrap_or(PhysicalPosition::new(0.0, 0.0));
        let event_type = match state {
            ElementState::Pressed => {
                self.pressed_button = button_name.clone();
                "mouse_pressed"
            }
            ElementState::Released => {
                self.pressed_button = None;
                "mouse_released"
            }
        };
        self.events.push(RuntimeEvent::mouse(
            event_type,
            position.x,
            position.y,
            0.0,
            0.0,
            button_name.clone(),
            modifiers_mask(self.modifiers),
        ));
        if state == ElementState::Released {
            self.push_click_events(button_name, position);
        }
    }

    fn push_click_events(&mut self, button_name: Option<String>, position: PhysicalPosition<f64>) {
        self.events.push(RuntimeEvent::mouse(
            "mouse_clicked",
            position.x,
            position.y,
            0.0,
            0.0,
            button_name.clone(),
            modifiers_mask(self.modifiers),
        ));
        if self.is_double_click(&button_name, position) {
            self.events.push(RuntimeEvent::mouse(
                "mouse_double_clicked",
                position.x,
                position.y,
                0.0,
                0.0,
                button_name.clone(),
                modifiers_mask(self.modifiers),
            ));
        }
        self.last_click = Some(ClickState {
            button: button_name,
            position,
            when: Instant::now(),
        });
    }

    pub(super) fn push_touch_event(&mut self, touch: winit::event::Touch) {
        let phase = touch_phase_name(touch.phase);
        let event_type = match touch.phase {
            TouchPhase::Started => "touch_started",
            TouchPhase::Moved => "touch_moved",
            TouchPhase::Ended => "touch_ended",
            TouchPhase::Cancelled => "touch_cancelled",
        };
        let pressure = touch.force.map(touch_pressure);
        match touch.phase {
            TouchPhase::Started | TouchPhase::Moved => {
                if !self.active_touches.contains(&touch.id) {
                    self.active_touches.push(touch.id);
                }
            }
            TouchPhase::Ended | TouchPhase::Cancelled => {
                self.active_touches.retain(|existing| *existing != touch.id);
            }
        }
        self.events.push(RuntimeEvent::touch(
            event_type,
            touch.id,
            touch.location.x,
            touch.location.y,
            phase,
            pressure,
        ));
    }

    fn is_double_click(&self, button: &Option<String>, position: PhysicalPosition<f64>) -> bool {
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
        let dx = position.x - last_click.position.x;
        let dy = position.y - last_click.position.y;
        (dx * dx + dy * dy).sqrt() <= DOUBLE_CLICK_DISTANCE
    }
}

#[derive(Clone)]
pub(super) struct ClickState {
    pub(super) button: Option<String>,
    pub(super) position: PhysicalPosition<f64>,
    pub(super) when: Instant,
}
