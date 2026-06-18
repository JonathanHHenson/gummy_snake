use std::sync::Arc;
use std::time::{Duration, Instant};

#[cfg(any(target_os = "macos", target_os = "linux", target_os = "windows"))]
mod desktop {
    use super::*;
    use winit::application::ApplicationHandler;
    use winit::dpi::{LogicalSize, PhysicalPosition, PhysicalSize, Size};
    use winit::event::{
        ElementState, Force, Ime, MouseButton, MouseScrollDelta, TouchPhase, WindowEvent,
    };
    use winit::event_loop::{ActiveEventLoop, EventLoop};
    use winit::keyboard::{Key, ModifiersState, NamedKey};
    use winit::platform::pump_events::{EventLoopExtPumpEvents, PumpStatus};
    use winit::window::{Window, WindowId};

    const DOUBLE_CLICK_INTERVAL: Duration = Duration::from_millis(500);
    const DOUBLE_CLICK_DISTANCE: f64 = 6.0;
    const WINDOW_TITLE: &str = "p5 canvas";

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
        fn new(event_type: &'static str) -> Self {
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

        fn close() -> Self {
            Self::new("close")
        }

        fn resized(width: i64, height: i64, pixel_density: f64) -> Self {
            let mut event = Self::new("resized");
            event.width = Some(width);
            event.height = Some(height);
            event.pixel_density = Some(pixel_density);
            event
        }

        fn mouse(
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

        fn mouse_wheel(x: f64, y: f64, scroll_x: f64, scroll_y: f64, modifiers: u32) -> Self {
            let mut event = Self::new("mouse_wheel");
            event.x = Some(x);
            event.y = Some(y);
            event.scroll_x = Some(scroll_x);
            event.scroll_y = Some(scroll_y);
            event.modifiers = Some(modifiers);
            event
        }

        fn key(
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

        fn key_typed(text: String) -> Self {
            let mut event = Self::new("key_typed");
            event.text = Some(text);
            event
        }

        fn touch(
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

    pub struct InteractiveRuntime {
        event_loop: EventLoop<()>,
        app: RuntimeApp,
    }

    impl InteractiveRuntime {
        pub fn open(width: i64, height: i64) -> Result<Self, String> {
            let event_loop = EventLoop::new().map_err(|err| err.to_string())?;
            let mut runtime = Self {
                event_loop,
                app: RuntimeApp::new(width, height),
            };
            runtime.pump_events()?;
            if runtime.app.window.is_none() {
                return Err("Failed to create native canvas window.".to_string());
            }
            Ok(runtime)
        }

        pub fn native_window_available() -> bool {
            true
        }

        pub fn display_density(&self) -> f64 {
            self.app.pixel_density.max(1.0)
        }

        pub fn should_close(&self) -> bool {
            self.app.closed
        }

        pub fn poll_events(&mut self) -> Result<Vec<RuntimeEvent>, String> {
            self.pump_events()?;
            Ok(self.app.drain_events())
        }

        pub fn request_resize(
            &mut self,
            logical_width: i64,
            logical_height: i64,
            pixel_density: f64,
        ) -> Result<(), String> {
            self.app
                .request_resize(logical_width, logical_height, pixel_density)
        }

        pub fn close(&mut self) {
            self.app.closed = true;
            self.app.events.push(RuntimeEvent::close());
            self.app.window = None;
        }

        pub fn window(&self) -> Option<Arc<Window>> {
            self.app.window.as_ref().map(Arc::clone)
        }

        pub fn physical_size(&self) -> (u32, u32) {
            (
                self.app.physical_width.max(1),
                self.app.physical_height.max(1),
            )
        }

        fn pump_events(&mut self) -> Result<(), String> {
            match self
                .event_loop
                .pump_app_events(Some(Duration::ZERO), &mut self.app)
            {
                PumpStatus::Continue => Ok(()),
                PumpStatus::Exit(_code) => {
                    self.app.closed = true;
                    if !self.app.has_close_event {
                        self.app.has_close_event = true;
                        self.app.events.push(RuntimeEvent::close());
                    }
                    Ok(())
                }
            }
        }
    }

    struct RuntimeApp {
        logical_width: i64,
        logical_height: i64,
        pixel_density: f64,
        physical_width: u32,
        physical_height: u32,
        window_id: Option<WindowId>,
        window: Option<Arc<Window>>,
        events: Vec<RuntimeEvent>,
        cursor_position: Option<PhysicalPosition<f64>>,
        modifiers: ModifiersState,
        pressed_button: Option<String>,
        last_click: Option<ClickState>,
        active_touches: Vec<u64>,
        closed: bool,
        has_close_event: bool,
    }

    impl RuntimeApp {
        fn new(logical_width: i64, logical_height: i64) -> Self {
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
            }
        }

        fn drain_events(&mut self) -> Vec<RuntimeEvent> {
            std::mem::take(&mut self.events)
        }

        fn request_resize(
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
                let expected_height =
                    (logical_height as f64 * pixel_density).round().max(1.0) as u32;
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

        fn handle_resize(&mut self, size: PhysicalSize<u32>) -> Result<(), String> {
            if size.width == 0 || size.height == 0 {
                return Ok(());
            }
            self.physical_width = size.width;
            self.physical_height = size.height;
            if let Some(window) = self.window.as_ref() {
                self.pixel_density = window.scale_factor().max(1.0);
                let logical_size = size.to_logical::<f64>(self.pixel_density);
                self.logical_width = logical_size.width.round().max(1.0) as i64;
                self.logical_height = logical_size.height.round().max(1.0) as i64;
            }
            self.events.push(RuntimeEvent::resized(
                self.logical_width,
                self.logical_height,
                self.pixel_density,
            ));
            Ok(())
        }

        fn push_cursor_event(&mut self, position: PhysicalPosition<f64>) {
            let previous = self.cursor_position.unwrap_or(position);
            self.cursor_position = Some(position);
            let dx = position.x - previous.x;
            let dy = position.y - previous.y;
            let event_type = if self.pressed_button.is_some() {
                "mouse_dragged"
            } else {
                "mouse_moved"
            };
            self.events.push(RuntimeEvent::mouse(
                event_type,
                position.x,
                position.y,
                dx,
                dy,
                self.pressed_button.clone(),
                modifiers_mask(self.modifiers),
            ));
        }

        fn push_mouse_button(&mut self, button: MouseButton, state: ElementState) {
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
        }

        fn push_touch_event(&mut self, touch: winit::event::Touch) {
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

        fn is_double_click(
            &self,
            button: &Option<String>,
            position: PhysicalPosition<f64>,
        ) -> bool {
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
                WindowEvent::CloseRequested => {
                    self.closed = true;
                    if !self.has_close_event {
                        self.has_close_event = true;
                        self.events.push(RuntimeEvent::close());
                    }
                    self.window = None;
                    event_loop.exit();
                }
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
                WindowEvent::CursorLeft { .. } => {
                    self.cursor_position = None;
                }
                WindowEvent::MouseInput { state, button, .. } => {
                    self.push_mouse_button(button, state);
                }
                WindowEvent::MouseWheel { delta, .. } => {
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
                WindowEvent::ModifiersChanged(modifiers) => {
                    self.modifiers = modifiers.state();
                }
                WindowEvent::KeyboardInput {
                    event,
                    is_synthetic,
                    ..
                } => {
                    if !is_synthetic {
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
                WindowEvent::Ime(Ime::Commit(text)) => {
                    if !text.is_empty() {
                        self.events.push(RuntimeEvent::key_typed(text));
                    }
                }
                WindowEvent::RedrawRequested
                | WindowEvent::Focused(_)
                | WindowEvent::ThemeChanged(_)
                | WindowEvent::Occluded(_)
                | WindowEvent::ActivationTokenDone { .. }
                | WindowEvent::Destroyed
                | WindowEvent::HoveredFile(_)
                | WindowEvent::DroppedFile(_)
                | WindowEvent::HoveredFileCancelled
                | WindowEvent::CursorEntered { .. }
                | WindowEvent::AxisMotion { .. }
                | WindowEvent::Ime(_)
                | WindowEvent::PinchGesture { .. }
                | WindowEvent::PanGesture { .. }
                | WindowEvent::RotationGesture { .. }
                | WindowEvent::DoubleTapGesture { .. }
                | WindowEvent::TouchpadPressure { .. }
                | WindowEvent::Moved(_) => {}
                WindowEvent::Touch(touch) => self.push_touch_event(touch),
            }
        }
    }

    #[derive(Clone)]
    struct ClickState {
        button: Option<String>,
        position: PhysicalPosition<f64>,
        when: Instant,
    }

    fn touch_phase_name(phase: TouchPhase) -> &'static str {
        match phase {
            TouchPhase::Started => "started",
            TouchPhase::Moved => "moved",
            TouchPhase::Ended => "ended",
            TouchPhase::Cancelled => "cancelled",
        }
    }

    fn touch_pressure(force: Force) -> f64 {
        match force {
            Force::Calibrated {
                force,
                max_possible_force,
                ..
            } => {
                if max_possible_force > 0.0 {
                    (force / max_possible_force).clamp(0.0, 1.0)
                } else {
                    force.max(0.0)
                }
            }
            Force::Normalized(value) => value.clamp(0.0, 1.0),
        }
    }

    fn normalize_mouse_button(button: MouseButton) -> Option<String> {
        match button {
            MouseButton::Left => Some("left".to_string()),
            MouseButton::Middle => Some("center".to_string()),
            MouseButton::Right => Some("right".to_string()),
            MouseButton::Back => Some("4".to_string()),
            MouseButton::Forward => Some("5".to_string()),
            MouseButton::Other(value) => Some(value.to_string()),
        }
    }

    fn normalize_key(key: &Key) -> Option<String> {
        match key {
            Key::Character(text) => Some(text.to_string()),
            Key::Named(named) => Some(named_key_name(*named).to_string()),
            _ => None,
        }
    }

    fn normalize_code(key: &Key) -> Option<String> {
        match key {
            Key::Named(named) => Some(named_key_code(*named).to_string()),
            _ => None,
        }
    }

    fn named_key_name(named: NamedKey) -> &'static str {
        match named {
            NamedKey::Space => " ",
            NamedKey::Enter => "Enter",
            NamedKey::Tab => "Tab",
            NamedKey::Backspace => "Backspace",
            NamedKey::Escape => "Escape",
            NamedKey::Shift => "Shift",
            NamedKey::Control => "Control",
            NamedKey::Alt => "Alt",
            NamedKey::ArrowUp => "ArrowUp",
            NamedKey::ArrowDown => "ArrowDown",
            NamedKey::ArrowLeft => "ArrowLeft",
            NamedKey::ArrowRight => "ArrowRight",
            _ => "",
        }
    }

    fn named_key_code(named: NamedKey) -> &'static str {
        match named {
            NamedKey::Enter => "Enter",
            NamedKey::Tab => "Tab",
            NamedKey::Backspace => "Backspace",
            NamedKey::Escape => "Escape",
            NamedKey::Shift => "Shift",
            NamedKey::Control => "Control",
            NamedKey::Alt => "Alt",
            NamedKey::ArrowUp => "ArrowUp",
            NamedKey::ArrowDown => "ArrowDown",
            NamedKey::ArrowLeft => "ArrowLeft",
            NamedKey::ArrowRight => "ArrowRight",
            _ => "",
        }
    }

    fn modifiers_mask(modifiers: ModifiersState) -> u32 {
        let mut value = 0_u32;
        if modifiers.shift_key() {
            value |= 1;
        }
        if modifiers.control_key() {
            value |= 2;
        }
        if modifiers.alt_key() {
            value |= 4;
        }
        if modifiers.super_key() {
            value |= 8;
        }
        value
    }

    pub fn native_window_available() -> bool {
        InteractiveRuntime::native_window_available()
    }
}

#[cfg(not(any(target_os = "macos", target_os = "linux", target_os = "windows")))]
mod desktop {
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
}

pub use desktop::{native_window_available, InteractiveRuntime, RuntimeEvent};
