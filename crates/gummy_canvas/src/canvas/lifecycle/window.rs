use super::LIVE_RESIZE_PRESENT_COOLDOWN;
use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn open_window_impl(&mut self) -> PyResult<()> {
        self.mode = INTERACTIVE_MODE.to_string();
        self.window_open = true;
        self.closed = false;
        self.runtime = Some(
            InteractiveRuntime::open(self.width, self.height).map_err(|err| {
                PyValueError::new_err(format!("Failed to open native canvas window: {err}"))
            })?,
        );
        if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .set_pointer_lock_mode(&self.pointer_lock_mode)
                .map_err(PyValueError::new_err)?;
        }
        Ok(())
    }

    pub(crate) fn should_close_impl(&self) -> bool {
        self.closed
            || self
                .runtime
                .as_ref()
                .map(|runtime| runtime.should_close())
                .unwrap_or(false)
    }

    pub(crate) fn pump_native_events_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(self.closed);
        };
        runtime.pump_events().map_err(|err| {
            PyValueError::new_err(format!("Failed to pump native canvas events: {err}"))
        })?;

        let should_close = runtime.should_close();
        let (logical_width, logical_height) = runtime.logical_size();
        let pixel_density = runtime.display_density();

        if should_close {
            self.closed = true;
            return Ok(true);
        }

        if runtime.resize_recently(LIVE_RESIZE_PRESENT_COOLDOWN) {
            return Ok(self.closed);
        }

        if logical_width != self.width
            || logical_height != self.height
            || (pixel_density - self.pixel_density).abs() > f64::EPSILON
        {
            self.resize_canvas_impl(
                logical_width,
                logical_height,
                pixel_density,
                SUPPORTED_RENDERER,
            )?;
        }

        Ok(self.closed)
    }

    pub(crate) fn request_pointer_lock_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Err(PyValueError::new_err(
                "Native canvas window is not available for pointer lock.",
            ));
        };
        runtime.request_pointer_lock().map_err(|err| {
            PyValueError::new_err(format!("Failed to request native pointer lock: {err}"))
        })
    }

    pub(crate) fn exit_pointer_lock_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(false);
        };
        runtime.exit_pointer_lock().map_err(|err| {
            PyValueError::new_err(format!("Failed to exit native pointer lock: {err}"))
        })
    }

    pub(crate) fn pointer_locked_impl(&self) -> bool {
        self.runtime
            .as_ref()
            .map(|runtime| runtime.pointer_locked())
            .unwrap_or(false)
    }

    pub(crate) fn set_pointer_lock_mode_impl(&mut self, mode: &str) -> PyResult<()> {
        let validated = if let Some(runtime) = self.runtime.as_mut() {
            runtime
                .set_pointer_lock_mode(mode)
                .map_err(PyValueError::new_err)?;
            runtime.pointer_lock_mode().to_string()
        } else {
            match mode {
                "unclamped" | "clamped" | "fixed" => mode.to_string(),
                _ => {
                    return Err(PyValueError::new_err(format!(
                        "Pointer lock mode must be 'unclamped', 'clamped', or 'fixed', got {mode:?}."
                    )));
                }
            }
        };
        self.pointer_lock_mode = validated;
        Ok(())
    }

    pub(crate) fn pointer_lock_mode_impl(&self) -> String {
        self.pointer_lock_mode.clone()
    }

    pub(crate) fn start_text_input_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Err(PyValueError::new_err(
                "Native canvas window is not available for text input.",
            ));
        };
        runtime.start_text_input().map_err(|err| {
            PyValueError::new_err(format!("Failed to start native text input: {err}"))
        })
    }

    pub(crate) fn stop_text_input_impl(&mut self) -> PyResult<bool> {
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(false);
        };
        runtime.stop_text_input().map_err(|err| {
            PyValueError::new_err(format!("Failed to stop native text input: {err}"))
        })
    }

    pub(crate) fn text_input_active_impl(&self) -> bool {
        self.runtime
            .as_ref()
            .map(|runtime| runtime.text_input_active())
            .unwrap_or(false)
    }

    pub(crate) fn poll_events_impl(&mut self) -> PyResult<Vec<Py<PyAny>>> {
        self.performance_counters.event_polls += 1;
        let Some(runtime) = self.runtime.as_mut() else {
            return Ok(Vec::new());
        };
        let events = runtime.poll_events().map_err(|err| {
            PyValueError::new_err(format!("Failed to poll native canvas events: {err}"))
        })?;
        if runtime.should_close() {
            self.closed = true;
        }
        Python::with_gil(|py| {
            events
                .into_iter()
                .map(|event| runtime_event_to_pyobject(py, event))
                .collect()
        })
    }
}
