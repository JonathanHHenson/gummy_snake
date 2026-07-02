use crate::{
    BLEND_MODE_ADD, BLEND_MODE_BLEND, BLEND_MODE_DARKEST, BLEND_MODE_DIFFERENCE,
    BLEND_MODE_EXCLUSION, BLEND_MODE_LIGHTEST, BLEND_MODE_MULTIPLY, BLEND_MODE_REPLACE,
    BLEND_MODE_SCREEN,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub(crate) enum BlendMode {
    Blend,
    Add,
    Darkest,
    Lightest,
    Difference,
    Exclusion,
    Multiply,
    Replace,
    Screen,
}

impl BlendMode {
    pub(crate) fn parse(mode: &str) -> Option<Self> {
        match mode {
            BLEND_MODE_BLEND => Some(Self::Blend),
            BLEND_MODE_ADD => Some(Self::Add),
            BLEND_MODE_DARKEST => Some(Self::Darkest),
            BLEND_MODE_LIGHTEST => Some(Self::Lightest),
            BLEND_MODE_DIFFERENCE => Some(Self::Difference),
            BLEND_MODE_EXCLUSION => Some(Self::Exclusion),
            BLEND_MODE_MULTIPLY => Some(Self::Multiply),
            BLEND_MODE_REPLACE => Some(Self::Replace),
            BLEND_MODE_SCREEN => Some(Self::Screen),
            _ => None,
        }
    }

    pub(crate) fn gpu_fixed_function_supported(self) -> bool {
        matches!(self, Self::Blend | Self::Add | Self::Replace)
    }
}

#[pyclass(name = "Matrix2D", frozen, unsendable)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Matrix2D {
    #[pyo3(get)]
    a: f64,
    #[pyo3(get)]
    b: f64,
    #[pyo3(get)]
    c: f64,
    #[pyo3(get)]
    d: f64,
    #[pyo3(get)]
    e: f64,
    #[pyo3(get)]
    f: f64,
}

impl Default for Matrix2D {
    fn default() -> Self {
        Self::new(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    }
}

#[pymethods]
impl Matrix2D {
    #[new]
    #[pyo3(signature = (a=1.0, b=0.0, c=0.0, d=1.0, e=0.0, f=0.0))]
    fn new(a: f64, b: f64, c: f64, d: f64, e: f64, f: f64) -> Self {
        Self { a, b, c, d, e, f }
    }

    #[staticmethod]
    fn identity() -> Self {
        Self::new(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    }

    #[staticmethod]
    fn translation(x: f64, y: f64) -> Self {
        Self::new(1.0, 0.0, 0.0, 1.0, x, y)
    }

    #[staticmethod]
    fn rotation(angle: f64) -> Self {
        let (sine, cosine) = angle.sin_cos();
        Self::new(cosine, sine, -sine, cosine, 0.0, 0.0)
    }

    #[staticmethod]
    #[pyo3(signature = (x, y=None))]
    fn scaling(x: f64, y: Option<f64>) -> Self {
        Self::new(x, 0.0, 0.0, y.unwrap_or(x), 0.0, 0.0)
    }

    #[staticmethod]
    fn shear_x(angle: f64) -> Self {
        Self::new(1.0, 0.0, angle.tan(), 1.0, 0.0, 0.0)
    }

    #[staticmethod]
    fn shear_y(angle: f64) -> Self {
        Self::new(1.0, angle.tan(), 0.0, 1.0, 0.0, 0.0)
    }

    fn multiply(&self, other: PyRef<'_, Self>) -> Self {
        Self::new(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )
    }

    fn transform_point(&self, x: f64, y: f64) -> (f64, f64) {
        (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )
    }

    fn inverse(&self) -> PyResult<Self> {
        let determinant = self.a * self.d - self.b * self.c;
        if determinant.abs() < 1e-12 {
            return Err(PyValueError::new_err("Matrix is not invertible."));
        }
        Ok(Self::new(
            self.d / determinant,
            -self.b / determinant,
            -self.c / determinant,
            self.a / determinant,
            (self.c * self.f - self.d * self.e) / determinant,
            (self.b * self.e - self.a * self.f) / determinant,
        ))
    }

    fn as_tuple<'py>(&self, py: Python<'py>) -> Bound<'py, PyTuple> {
        PyTuple::new_bound(py, [self.a, self.b, self.c, self.d, self.e, self.f])
    }

    fn __repr__(&self) -> String {
        format!(
            "Matrix2D(a={}, b={}, c={}, d={}, e={}, f={})",
            self.a, self.b, self.c, self.d, self.e, self.f
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Rgba {
    pub(crate) r: u8,
    pub(crate) g: u8,
    pub(crate) b: u8,
    pub(crate) a: u8,
}

impl Rgba {
    pub(crate) fn from_tuple(tuple: (u8, u8, u8, u8)) -> Self {
        Self {
            r: tuple.0,
            g: tuple.1,
            b: tuple.2,
            a: tuple.3,
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct Style {
    pub(crate) fill: Option<Rgba>,
    pub(crate) stroke: Option<Rgba>,
    pub(crate) stroke_weight: f64,
    pub(crate) image_tint: Option<Rgba>,
    pub(crate) blend_mode: String,
    pub(crate) blend_mode_kind: BlendMode,
    pub(crate) erasing: bool,
    pub(crate) image_sampling: String,
    pub(crate) text_font_path: Option<String>,
    pub(crate) text_font_name: String,
    pub(crate) text_size: f64,
    pub(crate) text_align_x: String,
    pub(crate) text_align_y: String,
    pub(crate) text_leading: f64,
}

impl Default for Style {
    fn default() -> Self {
        Self {
            fill: Some(Rgba {
                r: 255,
                g: 255,
                b: 255,
                a: 255,
            }),
            stroke: Some(Rgba {
                r: 0,
                g: 0,
                b: 0,
                a: 255,
            }),
            stroke_weight: 1.0,
            image_tint: None,
            blend_mode: BLEND_MODE_BLEND.to_string(),
            blend_mode_kind: BlendMode::Blend,
            erasing: false,
            image_sampling: "linear".to_string(),
            text_font_path: None,
            text_font_name: "default".to_string(),
            text_size: 12.0,
            text_align_x: "left".to_string(),
            text_align_y: "baseline".to_string(),
            text_leading: 14.0,
        }
    }
}
