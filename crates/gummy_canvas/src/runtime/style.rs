use crate::runtime::RuntimeEvent;
use crate::{
    BlendMode, Rgba, Style, INTERACTIVE_MODE, SUPPORTED_MODE, SUPPORTED_RENDERER,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict};

pub(crate) fn runtime_event_to_pyobject(
    py: Python<'_>,
    event: RuntimeEvent,
) -> PyResult<Py<PyAny>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("type", event.event_type)?;
    if let Some(x) = event.x {
        dict.set_item("x", x)?;
    }
    if let Some(y) = event.y {
        dict.set_item("y", y)?;
    }
    if let Some(dx) = event.dx {
        dict.set_item("dx", dx)?;
    }
    if let Some(dy) = event.dy {
        dict.set_item("dy", dy)?;
    }
    if let Some(button) = event.button {
        dict.set_item("button", button)?;
    }
    if let Some(scroll_x) = event.scroll_x {
        dict.set_item("scroll_x", scroll_x)?;
    }
    if let Some(scroll_y) = event.scroll_y {
        dict.set_item("scroll_y", scroll_y)?;
    }
    if let Some(modifiers) = event.modifiers {
        dict.set_item("modifiers", modifiers)?;
    }
    if let Some(inside_window) = event.inside_window {
        dict.set_item("inside_window", inside_window)?;
    }
    if let Some(key) = event.key {
        if !key.is_empty() {
            dict.set_item("key", key)?;
        }
    }
    if let Some(code) = event.code {
        if !code.is_empty() {
            dict.set_item("code", code)?;
        }
    }
    if let Some(text) = event.text {
        dict.set_item("text", text)?;
    }
    if let Some(width) = event.width {
        dict.set_item("width", width)?;
    }
    if let Some(height) = event.height {
        dict.set_item("height", height)?;
    }
    if let Some(pixel_density) = event.pixel_density {
        dict.set_item("pixel_density", pixel_density)?;
    }
    if let Some(coordinates) = event.coordinates {
        dict.set_item("coordinates", coordinates)?;
    }
    if let Some(touch_id) = event.touch_id {
        dict.set_item("id", touch_id)?;
    }
    if let Some(phase) = event.phase {
        dict.set_item("phase", phase)?;
    }
    if let Some(pressure) = event.pressure {
        dict.set_item("pressure", pressure)?;
    }
    if let Some(timestamp) = event.timestamp {
        dict.set_item("timestamp", timestamp)?;
    }
    if let Some(device) = event.device {
        dict.set_item("device", device)?;
    }
    Ok(dict.into_any().unbind())
}

pub(crate) fn validate_mode_and_renderer(mode: &str, renderer: &str) -> PyResult<()> {
    if mode != SUPPORTED_MODE && mode != INTERACTIVE_MODE {
        return Err(PyValueError::new_err(format!(
            "Unsupported canvas mode {mode:?}; supported modes are {SUPPORTED_MODE:?} and {INTERACTIVE_MODE:?}."
        )));
    }
    validate_renderer(renderer)
}

pub(crate) fn validate_renderer(renderer: &str) -> PyResult<()> {
    if renderer != SUPPORTED_RENDERER {
        return Err(PyValueError::new_err(format!(
            "Unsupported renderer {renderer:?}; only {SUPPORTED_RENDERER:?} is implemented."
        )));
    }
    Ok(())
}

pub(crate) fn physical_dimensions(
    width: i64,
    height: i64,
    pixel_density: f64,
) -> PyResult<(usize, usize)> {
    if width <= 0 || height <= 0 {
        return Err(PyValueError::new_err(
            "Canvas width and height must be positive.",
        ));
    }
    if pixel_density <= 0.0 || !pixel_density.is_finite() {
        return Err(PyValueError::new_err("Pixel density must be positive."));
    }
    let physical_width = ((width as f64 * pixel_density).round() as i64).max(1) as usize;
    let physical_height = ((height as f64 * pixel_density).round() as i64).max(1) as usize;
    Ok((physical_width, physical_height))
}

pub(crate) fn parse_style(style: &Bound<'_, PyAny>) -> PyResult<Style> {
    let dict = style.downcast::<PyDict>()?;
    let fill = parse_optional_rgba(dict, "fill")?;
    let stroke = parse_optional_rgba(dict, "stroke")?;
    let image_tint = parse_optional_rgba_if_present(dict, "image_tint")?;
    let stroke_weight = dict
        .get_item("stroke_weight")?
        .ok_or_else(|| PyValueError::new_err("Style payload missing 'stroke_weight'."))?
        .extract::<f64>()?;
    let blend_mode = dict
        .get_item("blend_mode")?
        .ok_or_else(|| PyValueError::new_err("Style payload missing 'blend_mode'."))?
        .extract::<String>()?;
    let blend_mode_kind = parse_blend_mode(&blend_mode)?;
    let erasing = dict
        .get_item("erasing")?
        .ok_or_else(|| PyValueError::new_err("Style payload missing 'erasing'."))?
        .extract::<bool>()?;
    let image_sampling = dict
        .get_item("image_sampling")?
        .map(|value| value.extract::<String>())
        .transpose()?
        .unwrap_or_else(|| "linear".to_string());
    let text_font_path = match dict.get_item("text_font_path")? {
        Some(value) if !value.is_none() => Some(value.extract::<String>()?),
        _ => None,
    };
    let text_font_name = dict
        .get_item("text_font_name")?
        .map(|value| value.extract::<String>())
        .transpose()?
        .unwrap_or_else(|| "default".to_string());
    let text_size = dict
        .get_item("text_size")?
        .map(|value| value.extract::<f64>())
        .transpose()?
        .unwrap_or(12.0);
    let text_align_x = dict
        .get_item("text_align_x")?
        .map(|value| value.extract::<String>())
        .transpose()?
        .unwrap_or_else(|| "left".to_string());
    let text_align_y = dict
        .get_item("text_align_y")?
        .map(|value| value.extract::<String>())
        .transpose()?
        .unwrap_or_else(|| "baseline".to_string());
    let text_leading = dict
        .get_item("text_leading")?
        .map(|value| value.extract::<f64>())
        .transpose()?
        .unwrap_or(14.0);
    Ok(Style {
        fill,
        stroke,
        stroke_weight,
        image_tint,
        blend_mode,
        blend_mode_kind,
        erasing,
        image_sampling,
        text_font_path,
        text_font_name,
        text_size,
        text_align_x,
        text_align_y,
        text_leading,
    })
}

fn parse_optional_rgba_if_present(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Rgba>> {
    let Some(value) = dict.get_item(key)? else {
        return Ok(None);
    };
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(Rgba::from_tuple(value.extract::<(u8, u8, u8, u8)>()?)))
    }
}

pub(crate) fn parse_optional_rgba(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Rgba>> {
    let Some(value) = dict.get_item(key)? else {
        return Err(PyValueError::new_err(format!(
            "Style payload missing {key:?}."
        )));
    };
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(Rgba::from_tuple(value.extract::<(u8, u8, u8, u8)>()?)))
    }
}

pub(crate) fn ensure_supported_style(style: &Style) -> PyResult<()> {
    if style.stroke_weight < 0.0 || !style.stroke_weight.is_finite() {
        return Err(PyValueError::new_err("stroke_weight cannot be negative."));
    }
    ensure_supported_blend_mode(&style.blend_mode)
}

pub(crate) fn ensure_supported_blend_mode(mode: &str) -> PyResult<()> {
    parse_blend_mode(mode).map(|_| ())
}

pub(crate) fn parse_blend_mode(mode: &str) -> PyResult<BlendMode> {
    BlendMode::parse(mode).ok_or_else(|| {
        PyValueError::new_err(format!(
            "Unsupported blend mode {mode:?} for gummy_canvas."
        ))
    })
}
