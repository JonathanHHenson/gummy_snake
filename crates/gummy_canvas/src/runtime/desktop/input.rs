use super::events::push_coalesced_event;
use super::{
    ClickState, InteractiveRuntime, PointerLockMode, DOUBLE_CLICK_DISTANCE, DOUBLE_CLICK_INTERVAL,
};
use crate::runtime::event::RuntimeEvent;
use sdl3::keyboard::{Keycode, Mod, Scancode};
use sdl3::mouse::{MouseButton, MouseWheelDirection};
use std::time::Instant;

impl InteractiveRuntime {
    pub(super) fn push_cursor_event(&mut self, x: f32, y: f32, xrel: f32, yrel: f32) {
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
        push_coalesced_event(
            &mut self.events,
            RuntimeEvent::logical_mouse(
                event_type,
                event_x,
                event_y,
                xrel as f64,
                yrel as f64,
                self.pressed_button.clone(),
                modifiers_mask(self.modifiers),
            ),
        );
    }

    pub(super) fn push_mouse_button(
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

    pub(super) fn push_mouse_wheel(
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
        push_coalesced_event(
            &mut self.events,
            RuntimeEvent::logical_mouse_wheel(
                event_x,
                event_y,
                x as f64 * multiplier,
                y as f64 * multiplier,
                modifiers_mask(self.modifiers),
            ),
        );
    }

    pub(super) fn push_click_events(&mut self, button_name: Option<String>, x: f64, y: f64) {
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

    pub(super) fn initial_locked_position(&self) -> (f64, f64) {
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

    pub(super) fn apply_pointer_lock_mode(&self, position: (f64, f64)) -> (f64, f64) {
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

    pub(super) fn center_position(&self) -> (f64, f64) {
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

    pub(super) fn push_key_event(
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

    pub(super) fn push_touch_event(
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

fn normalize_key_name(keycode: Keycode) -> String {
    let text = keycode.to_string();
    if text.chars().count() == 1 {
        text.to_lowercase()
    } else {
        text
    }
}

pub(super) fn normalize_mouse_button(button: MouseButton) -> Option<String> {
    match button {
        MouseButton::Left => Some("left".to_string()),
        MouseButton::Middle => Some("center".to_string()),
        MouseButton::Right => Some("right".to_string()),
        MouseButton::X1 => Some("4".to_string()),
        MouseButton::X2 => Some("5".to_string()),
        MouseButton::Unknown => None,
    }
}

pub(super) fn modifiers_mask(modifiers: Mod) -> u32 {
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
