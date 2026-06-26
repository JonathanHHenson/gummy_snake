use super::{add_unique, SketchContextState, TouchSnapshot};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};

impl SketchContextState {
    pub(super) fn update_mouse_impl(&mut self, x: f64, y: f64, dx: Option<f64>, dy: Option<f64>) {
        self.previous_mouse_x = self.mouse_x;
        self.previous_mouse_y = self.mouse_y;
        self.mouse_x = x;
        self.mouse_y = y;
        self.moved_x = dx.unwrap_or(self.mouse_x - self.previous_mouse_x);
        self.moved_y = dy.unwrap_or(self.mouse_y - self.previous_mouse_y);
    }

    pub(super) fn key_is_down_impl(&self, key_code: i64) -> bool {
        self.pressed_keys.contains(&key_code)
    }

    pub(super) fn code_is_down_impl(&self, code: &str) -> bool {
        self.pressed_codes.iter().any(|value| value == code)
    }

    pub(super) fn set_key_down_impl(&mut self, key_code: i64, pressed: bool) {
        if pressed {
            add_unique(&mut self.pressed_keys, key_code);
        } else {
            self.pressed_keys.retain(|value| *value != key_code);
        }
    }

    pub(super) fn set_code_down_impl(&mut self, code: String, pressed: bool) {
        if pressed {
            add_unique(&mut self.pressed_codes, code);
        } else {
            self.pressed_codes.retain(|value| value != &code);
        }
    }

    pub(super) fn update_touches_impl(&mut self, touches: &Bound<'_, PyAny>) -> PyResult<()> {
        let old = self.touches.clone();
        let mut updated = Vec::new();
        for item in touches.iter()? {
            let touch = item?;
            let id: i64 = touch.getattr("id")?.extract()?;
            let x: f64 = touch.getattr("x")?.extract()?;
            let y: f64 = touch.getattr("y")?.extract()?;
            let previous = old.iter().find(|existing| existing.id == id);
            let previous_x = touch
                .getattr("previous_x")?
                .extract::<Option<f64>>()?
                .or_else(|| previous.map(|existing| existing.x));
            let previous_y = touch
                .getattr("previous_y")?
                .extract::<Option<f64>>()?
                .or_else(|| previous.map(|existing| existing.y));
            updated.push(TouchSnapshot {
                id,
                x,
                y,
                previous_x,
                previous_y,
                pressure: touch.getattr("pressure")?.extract()?,
                phase: touch.getattr("phase")?.extract()?,
                timestamp: touch.getattr("timestamp")?.extract()?,
                device: touch.getattr("device")?.extract()?,
            });
        }
        self.touches = updated;
        Ok(())
    }

    pub(super) fn touch_payload_impl<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let result = PyList::empty_bound(py);
        for touch in &self.touches {
            let item = PyDict::new_bound(py);
            item.set_item("id", touch.id)?;
            item.set_item("x", touch.x)?;
            item.set_item("y", touch.y)?;
            item.set_item("previous_x", touch.previous_x)?;
            item.set_item("previous_y", touch.previous_y)?;
            item.set_item("pressure", touch.pressure)?;
            item.set_item("phase", touch.phase.clone())?;
            item.set_item("timestamp", touch.timestamp)?;
            item.set_item("device", touch.device.clone())?;
            result.append(item)?;
        }
        Ok(result)
    }
}
