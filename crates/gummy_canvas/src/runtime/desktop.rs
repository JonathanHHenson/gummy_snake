use std::sync::Arc;
use std::time::Duration;

use winit::event_loop::EventLoop;
use winit::platform::pump_events::{EventLoopExtPumpEvents, PumpStatus};
use winit::window::Window;

use crate::runtime::app::RuntimeApp;
use crate::runtime::event::RuntimeEvent;

const LIVE_RESIZE_EVENT_COOLDOWN: Duration = Duration::from_millis(80);

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

    pub fn logical_size(&self) -> (i64, i64) {
        (self.app.logical_width, self.app.logical_height)
    }

    pub fn should_close(&self) -> bool {
        self.app.closed
    }

    pub fn poll_events(&mut self) -> Result<Vec<RuntimeEvent>, String> {
        self.pump_events()?;
        if self.resize_recently(LIVE_RESIZE_EVENT_COOLDOWN) {
            return Ok(self.app.drain_events_except_resize());
        }
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

    pub fn resize_recently(&self, within: Duration) -> bool {
        self.app
            .last_resize_at
            .map(|instant| instant.elapsed() <= within)
            .unwrap_or(false)
    }

    pub(crate) fn pump_events(&mut self) -> Result<(), String> {
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

pub fn native_window_available() -> bool {
    InteractiveRuntime::native_window_available()
}
