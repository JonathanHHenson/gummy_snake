//! Rust-owned reusable media frame sink and locally qualified GIF playback.

use std::fs::File;
use std::io::BufReader;
use std::path::Path;

use image::AnimationDecoder;
use pyo3::buffer::PyBuffer;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict};

use crate::assets::CanvasImage;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum MediaPixelFormat {
    Gray,
    Bgr,
    Bgra,
    Rgba,
}

impl MediaPixelFormat {
    fn parse(value: &str) -> PyResult<Self> {
        match value.to_ascii_lowercase().as_str() {
            "gray" | "grey" => Ok(Self::Gray),
            "bgr" => Ok(Self::Bgr),
            "bgra" => Ok(Self::Bgra),
            "rgba" => Ok(Self::Rgba),
            _ => Err(PyValueError::new_err(format!(
                "Unsupported media pixel format {value:?}; expected gray, bgr, bgra, or rgba."
            ))),
        }
    }

    fn channels(self) -> usize {
        match self {
            Self::Gray => 1,
            Self::Bgr => 3,
            Self::Bgra | Self::Rgba => 4,
        }
    }
}

fn converted_rgba(
    source: &[u8],
    width: usize,
    height: usize,
    stride: usize,
    format: MediaPixelFormat,
) -> PyResult<Vec<u8>> {
    if width == 0 || height == 0 {
        return Err(PyValueError::new_err(
            "Media frame dimensions must be positive.",
        ));
    }
    let row_bytes = width
        .checked_mul(format.channels())
        .ok_or_else(|| PyValueError::new_err("Media frame dimensions are too large."))?;
    if stride < row_bytes {
        return Err(PyValueError::new_err(format!(
            "Media frame stride must be at least {row_bytes} bytes, got {stride}."
        )));
    }
    let expected = stride
        .checked_mul(height)
        .ok_or_else(|| PyValueError::new_err("Media frame dimensions are too large."))?;
    if source.len() != expected {
        return Err(PyValueError::new_err(format!(
            "Media frame buffer length must be {expected}, got {}.",
            source.len()
        )));
    }
    let mut rgba = vec![0_u8; width * height * 4];
    for y in 0..height {
        let source_row = &source[y * stride..y * stride + row_bytes];
        let destination_row = &mut rgba[y * width * 4..(y + 1) * width * 4];
        match format {
            MediaPixelFormat::Gray => {
                for (gray, pixel) in source_row.iter().zip(destination_row.chunks_exact_mut(4)) {
                    pixel.copy_from_slice(&[*gray, *gray, *gray, 255]);
                }
            }
            MediaPixelFormat::Bgr => {
                for (source, pixel) in source_row
                    .chunks_exact(3)
                    .zip(destination_row.chunks_exact_mut(4))
                {
                    pixel.copy_from_slice(&[source[2], source[1], source[0], 255]);
                }
            }
            MediaPixelFormat::Bgra => {
                for (source, pixel) in source_row
                    .chunks_exact(4)
                    .zip(destination_row.chunks_exact_mut(4))
                {
                    pixel.copy_from_slice(&[source[2], source[1], source[0], source[3]]);
                }
            }
            MediaPixelFormat::Rgba => destination_row.copy_from_slice(source_row),
        }
    }
    Ok(rgba)
}

fn with_u8_buffer<T>(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
    operation: impl FnOnce(&[u8]) -> PyResult<T>,
) -> PyResult<T> {
    let buffer = PyBuffer::<u8>::get_bound(value).map_err(|_| {
        PyValueError::new_err("Media frames must expose a contiguous unsigned-byte buffer.")
    })?;
    let cells = buffer.as_slice(py).ok_or_else(|| {
        PyValueError::new_err("Media frame buffers must be C-contiguous unsigned bytes.")
    })?;
    let payload = unsafe { std::slice::from_raw_parts(cells.as_ptr() as *const u8, cells.len()) };
    operation(payload)
}

#[pyclass(name = "CanvasMediaFrameSink", unsendable)]
pub(crate) struct CanvasMediaFrameSink {
    image: Py<CanvasImage>,
    frames_written: u64,
    source_bytes: u64,
    converted_bytes: u64,
    reallocations: u64,
}

#[pymethods]
impl CanvasMediaFrameSink {
    #[new]
    fn new(py: Python<'_>, width: usize, height: usize) -> PyResult<Self> {
        if width == 0 || height == 0 {
            return Err(PyValueError::new_err(
                "Media frame sink dimensions must be positive.",
            ));
        }
        let byte_len = width
            .checked_mul(height)
            .and_then(|value| value.checked_mul(4))
            .ok_or_else(|| PyValueError::new_err("Media frame dimensions are too large."))?;
        Ok(Self {
            image: Py::new(
                py,
                CanvasImage::from_pixels(width, height, vec![0; byte_len]),
            )?,
            frames_written: 0,
            source_bytes: 0,
            converted_bytes: 0,
            reallocations: 1,
        })
    }

    #[getter]
    fn image(&self, py: Python<'_>) -> Py<CanvasImage> {
        self.image.clone_ref(py)
    }

    #[pyo3(signature = (pixels, width, height, format="rgba", stride=None))]
    fn update(
        &mut self,
        py: Python<'_>,
        pixels: &Bound<'_, PyAny>,
        width: usize,
        height: usize,
        format: &str,
        stride: Option<usize>,
    ) -> PyResult<()> {
        let format = MediaPixelFormat::parse(format)?;
        let row_bytes = width
            .checked_mul(format.channels())
            .ok_or_else(|| PyValueError::new_err("Media frame dimensions are too large."))?;
        let stride = stride.unwrap_or(row_bytes);
        let previous_dimensions = {
            let image = self.image.borrow(py);
            (image.width, image.height)
        };
        let (rgba, source_len) = with_u8_buffer(py, pixels, |source| {
            Ok((
                converted_rgba(source, width, height, stride, format)?,
                source.len(),
            ))
        })?;
        self.image
            .borrow_mut(py)
            .replace_pixels_preserving_identity(width, height, rgba)?;
        self.frames_written += 1;
        self.source_bytes += source_len as u64;
        self.converted_bytes += (width * height * 4) as u64;
        if previous_dimensions != (width, height) {
            self.reallocations += 1;
        }
        Ok(())
    }

    fn diagnostics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let image = self.image.borrow(py);
        let result = PyDict::new_bound(py);
        result.set_item("frames_written", self.frames_written)?;
        result.set_item("source_bytes", self.source_bytes)?;
        result.set_item("converted_bytes", self.converted_bytes)?;
        result.set_item("reallocations", self.reallocations)?;
        result.set_item("image_key", image.key)?;
        result.set_item("image_version", image.version)?;
        Ok(result)
    }
}

struct VideoFrame {
    pixels: Vec<u8>,
    duration_seconds: f64,
}

#[pyclass(name = "CanvasVideo", unsendable)]
pub(crate) struct CanvasVideo {
    path: String,
    width: usize,
    height: usize,
    frames: Vec<VideoFrame>,
    frame_offsets: Vec<f64>,
    duration: f64,
    next_index: usize,
    current_index: Option<usize>,
    playing: bool,
    looping: bool,
    speed: f64,
    closed: bool,
    image: Py<CanvasImage>,
    frames_decoded: u64,
}

#[pymethods]
impl CanvasVideo {
    #[staticmethod]
    fn open(py: Python<'_>, path: &str) -> PyResult<Self> {
        let source = Path::new(path);
        let extension = source
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        if extension != "gif" {
            return Err(PyValueError::new_err(
                "The canonical Rust media runtime currently supports self-contained GIF video files only. No OpenCV or platform decoder fallback is used.",
            ));
        }
        let file = File::open(source).map_err(|error| {
            PyValueError::new_err(format!("Could not open video {path}: {error}"))
        })?;
        let decoder =
            image::codecs::gif::GifDecoder::new(BufReader::new(file)).map_err(|error| {
                PyValueError::new_err(format!("Could not decode GIF video {path}: {error}"))
            })?;
        let decoded = decoder.into_frames().collect_frames().map_err(|error| {
            PyValueError::new_err(format!(
                "Could not decode GIF video frames from {path}: {error}"
            ))
        })?;
        if decoded.is_empty() {
            return Err(PyValueError::new_err(format!(
                "GIF video {path} does not contain any frames."
            )));
        }
        let width = decoded[0].buffer().width() as usize;
        let height = decoded[0].buffer().height() as usize;
        let mut frames = Vec::with_capacity(decoded.len());
        let mut frame_offsets = Vec::with_capacity(decoded.len());
        let mut duration = 0.0;
        for frame in decoded {
            if frame.buffer().width() as usize != width
                || frame.buffer().height() as usize != height
            {
                return Err(PyValueError::new_err(
                    "GIF video frames must have stable decoded dimensions.",
                ));
            }
            let (numerator, denominator) = frame.delay().numer_denom_ms();
            let frame_duration = if denominator == 0 {
                0.1
            } else {
                (f64::from(numerator) / f64::from(denominator) / 1000.0).max(0.001)
            };
            frame_offsets.push(duration);
            duration += frame_duration;
            frames.push(VideoFrame {
                pixels: frame.into_buffer().into_raw(),
                duration_seconds: frame_duration,
            });
        }
        let image = Py::new(
            py,
            CanvasImage::from_pixels(width, height, vec![0; width * height * 4]),
        )?;
        Ok(Self {
            path: path.to_owned(),
            width,
            height,
            frames,
            frame_offsets,
            duration,
            next_index: 0,
            current_index: None,
            playing: false,
            looping: false,
            speed: 1.0,
            closed: false,
            image,
            frames_decoded: 0,
        })
    }

    #[getter]
    fn path(&self) -> &str {
        &self.path
    }

    #[getter]
    fn width(&self) -> usize {
        self.width
    }

    #[getter]
    fn height(&self) -> usize {
        self.height
    }

    #[getter]
    fn frame_count(&self) -> usize {
        self.frames.len()
    }

    #[getter]
    fn duration(&self) -> f64 {
        self.duration
    }

    #[getter]
    fn fps(&self) -> f64 {
        self.frames.len() as f64 / self.duration
    }

    #[getter]
    fn is_playing(&self) -> bool {
        self.playing && !self.closed
    }

    fn play(&mut self) -> PyResult<()> {
        self.ensure_open()?;
        self.playing = true;
        Ok(())
    }

    fn pause(&mut self) -> PyResult<()> {
        self.ensure_open()?;
        self.playing = false;
        Ok(())
    }

    fn stop(&mut self) -> PyResult<()> {
        self.ensure_open()?;
        self.playing = false;
        self.seek(0.0)
    }

    #[pyo3(signature = (value=None))]
    fn looping(&mut self, value: Option<bool>) -> PyResult<bool> {
        self.ensure_open()?;
        if let Some(value) = value {
            self.looping = value;
        }
        Ok(self.looping)
    }

    #[pyo3(name = "loop")]
    fn loop_video(&mut self) -> PyResult<()> {
        self.ensure_open()?;
        self.looping = true;
        self.playing = true;
        Ok(())
    }

    fn no_loop(&mut self) -> PyResult<()> {
        self.ensure_open()?;
        self.looping = false;
        Ok(())
    }

    #[pyo3(signature = (value=None))]
    fn speed(&mut self, value: Option<f64>) -> PyResult<f64> {
        self.ensure_open()?;
        if let Some(value) = value {
            if !value.is_finite() || value <= 0.0 {
                return Err(PyValueError::new_err(
                    "Video speed must be positive and finite.",
                ));
            }
            self.speed = value;
        }
        Ok(self.speed)
    }

    fn time(&self) -> PyResult<f64> {
        self.ensure_open()?;
        Ok(self
            .current_index
            .and_then(|index| self.frame_offsets.get(index).copied())
            .unwrap_or_else(|| {
                self.frame_offsets
                    .get(self.next_index)
                    .copied()
                    .unwrap_or(self.duration)
            }))
    }

    fn seek(&mut self, seconds: f64) -> PyResult<()> {
        self.ensure_open()?;
        if !seconds.is_finite() || seconds < 0.0 || seconds > self.duration {
            return Err(PyValueError::new_err(format!(
                "Video seek time must be finite and between 0 and {:.6} seconds.",
                self.duration
            )));
        }
        self.next_index = self
            .frame_offsets
            .iter()
            .position(|offset| *offset >= seconds)
            .unwrap_or(self.frames.len());
        self.current_index = None;
        Ok(())
    }

    fn read(&mut self, py: Python<'_>) -> PyResult<Option<Py<CanvasImage>>> {
        self.ensure_open()?;
        if !self.playing && self.current_index.is_some() {
            return Ok(Some(self.image.clone_ref(py)));
        }
        if self.next_index >= self.frames.len() {
            if self.looping {
                self.next_index = 0;
            } else {
                self.playing = false;
                return Ok(None);
            }
        }
        let index = self.next_index;
        let frame = &self.frames[index];
        self.image
            .borrow_mut(py)
            .replace_pixels_preserving_identity(self.width, self.height, frame.pixels.clone())?;
        self.current_index = Some(index);
        self.next_index += 1;
        self.frames_decoded += 1;
        Ok(Some(self.image.clone_ref(py)))
    }

    fn current_frame(&self, py: Python<'_>) -> PyResult<Option<Py<CanvasImage>>> {
        self.ensure_open()?;
        Ok(self.current_index.map(|_| self.image.clone_ref(py)))
    }

    fn close(&mut self) {
        self.closed = true;
        self.playing = false;
        self.frames.clear();
        self.frame_offsets.clear();
    }

    fn diagnostics<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let image = self.image.borrow(py);
        let result = PyDict::new_bound(py);
        result.set_item("decoder", "rust-image-gif")?;
        result.set_item("queued_frames", self.frames.len())?;
        result.set_item("frames_decoded", self.frames_decoded)?;
        result.set_item("image_key", image.key)?;
        result.set_item("image_version", image.version)?;
        result.set_item(
            "resident_frame_bytes",
            self.frames
                .iter()
                .map(|frame| frame.pixels.len())
                .sum::<usize>(),
        )?;
        result.set_item(
            "timeline_duration_seconds",
            self.frames
                .iter()
                .map(|frame| frame.duration_seconds)
                .sum::<f64>(),
        )?;
        Ok(result)
    }
}

impl CanvasVideo {
    fn ensure_open(&self) -> PyResult<()> {
        if self.closed {
            Err(PyRuntimeError::new_err(
                "This video has already been closed.",
            ))
        } else {
            Ok(())
        }
    }
}
