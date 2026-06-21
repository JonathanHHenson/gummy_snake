use std::sync::Arc;

use winit::application::ApplicationHandler;
use winit::dpi::{LogicalSize, PhysicalPosition, Size};
use winit::event::{ElementState, Ime, MouseScrollDelta, WindowEvent};
use winit::event_loop::ActiveEventLoop;
use winit::window::{Window, WindowId};

use crate::runtime::app::RuntimeApp;
use crate::runtime::event::RuntimeEvent;
use crate::runtime::input::{modifiers_mask, normalize_code, normalize_key};

const WINDOW_TITLE: &str = "Gummy Snake";

impl ApplicationHandler for RuntimeApp {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        if self.window.is_some() {
            return;
        }
        let attributes = Window::default_attributes()
            .with_title(WINDOW_TITLE)
            .with_inner_size(Size::Logical(LogicalSize::new(
                self.logical_width as f64,
                self.logical_height as f64,
            )));
        let Ok(window) = event_loop.create_window(attributes) else {
            self.closed = true;
            self.has_close_event = true;
            self.events.push(RuntimeEvent::close());
            event_loop.exit();
            return;
        };
        let window = Arc::new(window);
        window.set_ime_allowed(true);
        self.pixel_density = window.scale_factor().max(1.0);
        self.window_id = Some(window.id());
        let size = window.inner_size();
        self.physical_width = size.width.max(1);
        self.physical_height = size.height.max(1);
        let logical_size = size.to_logical::<f64>(self.pixel_density);
        self.logical_width = logical_size.width.round().max(1.0) as i64;
        self.logical_height = logical_size.height.round().max(1.0) as i64;
        self.window = Some(window);
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        window_id: WindowId,
        event: WindowEvent,
    ) {
        if Some(window_id) != self.window_id {
            return;
        }
        match event {
            WindowEvent::CloseRequested => self.handle_close_requested(event_loop),
            WindowEvent::Resized(size) => {
                let _ = self.handle_resize(size);
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                self.pixel_density = scale_factor.max(1.0);
                if let Some(window) = self.window.as_ref() {
                    let _ = self.handle_resize(window.inner_size());
                }
            }
            WindowEvent::CursorMoved { position, .. } => self.push_cursor_event(position),
            WindowEvent::CursorLeft { .. } => self.cursor_position = None,
            WindowEvent::MouseInput { state, button, .. } => self.push_mouse_button(button, state),
            WindowEvent::MouseWheel { delta, .. } => self.push_mouse_wheel(delta),
            WindowEvent::ModifiersChanged(modifiers) => self.modifiers = modifiers.state(),
            WindowEvent::KeyboardInput {
                event,
                is_synthetic,
                ..
            } => self.push_keyboard_input(event, is_synthetic),
            WindowEvent::Ime(Ime::Commit(text)) => {
                if !text.is_empty() {
                    self.events.push(RuntimeEvent::key_typed(text));
                }
            }
            WindowEvent::Touch(touch) => self.push_touch_event(touch),
            _ => {}
        }
    }
}

impl RuntimeApp {
    fn handle_close_requested(&mut self, event_loop: &ActiveEventLoop) {
        self.closed = true;
        if !self.has_close_event {
            self.has_close_event = true;
            self.events.push(RuntimeEvent::close());
        }
        self.window = None;
        event_loop.exit();
    }

    fn push_mouse_wheel(&mut self, delta: MouseScrollDelta) {
        let position = self
            .cursor_position
            .unwrap_or(PhysicalPosition::new(0.0, 0.0));
        let (scroll_x, scroll_y) = match delta {
            MouseScrollDelta::LineDelta(x, y) => (x as f64, y as f64),
            MouseScrollDelta::PixelDelta(delta) => (delta.x, delta.y),
        };
        self.events.push(RuntimeEvent::mouse_wheel(
            position.x,
            position.y,
            scroll_x,
            scroll_y,
            modifiers_mask(self.modifiers),
        ));
    }

    fn push_keyboard_input(&mut self, event: winit::event::KeyEvent, is_synthetic: bool) {
        if is_synthetic {
            return;
        }
        let event_type = match event.state {
            ElementState::Pressed => "key_pressed",
            ElementState::Released => "key_released",
        };
        self.events.push(RuntimeEvent::key(
            event_type,
            normalize_key(&event.logical_key),
            normalize_code(&event.logical_key),
            modifiers_mask(self.modifiers),
        ));
    }
}
