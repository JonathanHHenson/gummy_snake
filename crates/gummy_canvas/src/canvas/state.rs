use crate::runtime::style::*;
use crate::*;

impl Canvas {
    pub(crate) fn set_current_style_impl(&mut self, style: &Bound<'_, PyAny>) -> PyResult<()> {
        let style = parse_style(style)?;
        ensure_supported_style(&style)?;
        self.current_style = style;
        Ok(())
    }

    pub(crate) fn current_style_impl<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("fill", rgba_to_py(self.current_style.fill))?;
        dict.set_item("stroke", rgba_to_py(self.current_style.stroke))?;
        dict.set_item("stroke_weight", self.current_style.stroke_weight)?;
        dict.set_item("image_tint", rgba_to_py(self.current_style.image_tint))?;
        dict.set_item("blend_mode", self.current_style.blend_mode.clone())?;
        dict.set_item("erasing", self.current_style.erasing)?;
        dict.set_item("image_sampling", self.current_style.image_sampling.clone())?;
        dict.set_item("text_font_path", self.current_style.text_font_path.clone())?;
        dict.set_item("text_font_name", self.current_style.text_font_name.clone())?;
        dict.set_item("text_size", self.current_style.text_size)?;
        dict.set_item("text_align_x", self.current_style.text_align_x.clone())?;
        dict.set_item("text_align_y", self.current_style.text_align_y.clone())?;
        dict.set_item("text_leading", self.current_style.text_leading)?;
        Ok(dict)
    }

    pub(crate) fn current_style_payload_impl<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        self.cached_style_key = None;
        self.cached_style = None;
        self.current_style_impl(py)
    }

    pub(crate) fn set_current_matrix_impl(&mut self, matrix: Matrix) {
        self.current_matrix = matrix;
    }

    pub(crate) fn current_matrix_impl(&self) -> Matrix {
        self.current_matrix
    }

    pub(crate) fn push_canvas_state_impl(&mut self) {
        self.style_stack.push(self.current_style.clone());
        self.matrix_stack.push(self.current_matrix);
    }

    pub(crate) fn pop_canvas_state_impl(&mut self) -> PyResult<()> {
        let style = self
            .style_stack
            .pop()
            .ok_or_else(|| PyValueError::new_err("pop() called without matching push()."))?;
        let matrix = self
            .matrix_stack
            .pop()
            .ok_or_else(|| PyValueError::new_err("pop() called without matching push()."))?;
        self.current_style = style;
        self.current_matrix = matrix;
        Ok(())
    }

    pub(crate) fn translate_impl(&mut self, x: f64, y: f64) {
        self.current_matrix = multiply_matrix(self.current_matrix, (1.0, 0.0, 0.0, 1.0, x, y));
    }

    pub(crate) fn rotate_impl(&mut self, angle: f64) {
        let (sine, cosine) = angle.sin_cos();
        self.current_matrix =
            multiply_matrix(self.current_matrix, (cosine, sine, -sine, cosine, 0.0, 0.0));
    }

    pub(crate) fn scale_impl(&mut self, x: f64, y: Option<f64>) {
        self.current_matrix =
            multiply_matrix(self.current_matrix, (x, 0.0, 0.0, y.unwrap_or(x), 0.0, 0.0));
    }

    pub(crate) fn shear_x_impl(&mut self, angle: f64) {
        self.current_matrix =
            multiply_matrix(self.current_matrix, (1.0, 0.0, angle.tan(), 1.0, 0.0, 0.0));
    }

    pub(crate) fn shear_y_impl(&mut self, angle: f64) {
        self.current_matrix =
            multiply_matrix(self.current_matrix, (1.0, angle.tan(), 0.0, 1.0, 0.0, 0.0));
    }

    pub(crate) fn apply_matrix_impl(&mut self, matrix: Matrix) {
        self.current_matrix = multiply_matrix(self.current_matrix, matrix);
    }

    pub(crate) fn reset_matrix_impl(&mut self) {
        self.current_matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0);
    }
}

fn rgba_to_py(rgba: Option<Rgba>) -> Option<(u8, u8, u8, u8)> {
    rgba.map(|value| (value.r, value.g, value.b, value.a))
}

fn multiply_matrix(left: Matrix, right: Matrix) -> Matrix {
    let (a, b, c, d, e, f) = left;
    let (oa, ob, oc, od, oe, of) = right;
    (
        a * oa + c * ob,
        b * oa + d * ob,
        a * oc + c * od,
        b * oc + d * od,
        a * oe + c * of + e,
        b * oe + d * of + f,
    )
}
