use crate::prelude::*;
use pyo3::types::{PyAny, PyList, PyTuple};
use std::collections::HashMap;
use std::sync::Arc;

pub(crate) const IMAGE_ATLAS_MAX_UNIQUE_IMAGES: usize = 128;
const MOTION_SPRITE_RECORD_SIZE: usize = 16;

pub(crate) struct BatchCanvasImage {
    pub(crate) unique_index: usize,
    pub(crate) dx: f64,
    pub(crate) dy: f64,
    pub(crate) dw: f64,
    pub(crate) dh: f64,
    pub(crate) source: Option<(i64, i64, i64, i64)>,
    pub(crate) matrix: Matrix,
}

pub(crate) struct BatchUniqueImage {
    pub(crate) key: u64,
    pub(crate) version: u64,
    pub(crate) width: usize,
    pub(crate) height: usize,
    pub(crate) pixels: Arc<Vec<u8>>,
}

pub(crate) struct ImageBatchBuilder {
    unique_images: Vec<BatchUniqueImage>,
    unique_indices: HashMap<(u64, u64), usize>,
    records: Vec<BatchCanvasImage>,
}

impl ImageBatchBuilder {
    pub(crate) fn with_record_capacity(capacity: usize) -> Self {
        Self {
            unique_images: Vec::new(),
            unique_indices: HashMap::new(),
            records: Vec::with_capacity(capacity),
        }
    }

    pub(crate) fn parse_canvas_records(
        records: &Bound<'_, PyAny>,
        matrix: Matrix,
    ) -> PyResult<Self> {
        let sequence = records.downcast::<PyList>()?;
        let mut builder = Self::with_record_capacity(sequence.len());
        for item in sequence.iter() {
            let record = item.downcast::<PyTuple>()?;
            if record.len() != 6 {
                return Err(PyValueError::new_err(
                    "Image batch records must contain image, dx, dy, dw, dh, and source.",
                ));
            }
            let image = record.get_item(0)?.extract::<PyRef<'_, CanvasImage>>()?;
            let dx = record.get_item(1)?.extract::<f64>()?;
            let dy = record.get_item(2)?.extract::<f64>()?;
            let dw = record.get_item(3)?.extract::<f64>()?;
            let dh = record.get_item(4)?.extract::<f64>()?;
            let source = record
                .get_item(5)?
                .extract::<Option<(i64, i64, i64, i64)>>()?;
            builder.push_canvas_image(&image, dx, dy, dw, dh, source, matrix);
        }
        Ok(builder)
    }

    pub(crate) fn parse_transformed_canvas_records(records: &Bound<'_, PyAny>) -> PyResult<Self> {
        let sequence = records.downcast::<PyList>()?;
        let mut builder = Self::with_record_capacity(sequence.len());
        for item in sequence.iter() {
            let record = item.downcast::<PyTuple>()?;
            if record.len() != 7 {
                return Err(PyValueError::new_err(
                    "Transformed image batch records must contain image, dx, dy, dw, dh, source, and matrix.",
                ));
            }
            let image = record.get_item(0)?.extract::<PyRef<'_, CanvasImage>>()?;
            let dx = record.get_item(1)?.extract::<f64>()?;
            let dy = record.get_item(2)?.extract::<f64>()?;
            let dw = record.get_item(3)?.extract::<f64>()?;
            let dh = record.get_item(4)?.extract::<f64>()?;
            let source = record
                .get_item(5)?
                .extract::<Option<(i64, i64, i64, i64)>>()?;
            let matrix = record.get_item(6)?.extract::<Matrix>()?;
            builder.push_canvas_image(&image, dx, dy, dw, dh, source, matrix);
        }
        Ok(builder)
    }

    pub(crate) fn parse_motion_records(
        records: &[u8],
        images: &[PyRef<'_, CanvasImage>],
        frame: u64,
        matrix: Matrix,
    ) -> PyResult<Self> {
        if records.len() % MOTION_SPRITE_RECORD_SIZE != 0 {
            return Err(PyValueError::new_err(
                "Compact sprite records must be 16-byte little-endian records.",
            ));
        }
        let unique_images = images
            .iter()
            .map(|image| BatchUniqueImage::from_canvas_image(image))
            .collect::<Vec<_>>();
        let mut builder = Self {
            unique_images,
            unique_indices: HashMap::new(),
            records: Vec::with_capacity(records.len() / MOTION_SPRITE_RECORD_SIZE),
        };
        for record in records.chunks_exact(MOTION_SPRITE_RECORD_SIZE) {
            let image_index =
                u32::from_le_bytes([record[0], record[1], record[2], record[3]]) as usize;
            if image_index >= builder.unique_images.len() {
                return Err(PyValueError::new_err(
                    "Compact sprite record references an out-of-range image index.",
                ));
            }
            let base_x = f32::from_le_bytes([record[4], record[5], record[6], record[7]]) as f64;
            let y = f32::from_le_bytes([record[8], record[9], record[10], record[11]]) as f64;
            let size = f32::from_le_bytes([record[12], record[13], record[14], record[15]]) as f64;
            if size <= 0.0 {
                continue;
            }
            let x = 10.0 + (base_x + frame as f64).rem_euclid(700.0) - size / 2.0;
            builder.records.push(BatchCanvasImage {
                unique_index: image_index,
                dx: x,
                dy: y - size / 2.0,
                dw: size,
                dh: size,
                source: None,
                matrix,
            });
        }
        Ok(builder)
    }

    pub(crate) fn push_canvas_image(
        &mut self,
        image: &CanvasImage,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        source: Option<(i64, i64, i64, i64)>,
        matrix: Matrix,
    ) {
        let unique_index = self.unique_index_for(
            image.key,
            image.version,
            image.width,
            image.height,
            Arc::clone(&image.pixels),
        );
        self.records.push(BatchCanvasImage {
            unique_index,
            dx,
            dy,
            dw,
            dh,
            source,
            matrix,
        });
    }

    pub(crate) fn push_cached_text_image(
        &mut self,
        cached: &CachedText,
        dx: f64,
        dy: f64,
        dw: f64,
        dh: f64,
        matrix: Matrix,
    ) {
        let unique_index = self.unique_index_for(
            cached.texture_key,
            cached.image.version,
            cached.image.width,
            cached.image.height,
            Arc::clone(&cached.image.pixels),
        );
        self.records.push(BatchCanvasImage {
            unique_index,
            dx,
            dy,
            dw,
            dh,
            source: None,
            matrix,
        });
    }

    pub(crate) fn contains_unique(&self, key: (u64, u64)) -> bool {
        self.unique_indices.contains_key(&key)
    }

    pub(crate) fn unique_len(&self) -> usize {
        self.unique_images.len()
    }

    pub(crate) fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    pub(crate) fn clear(&mut self) {
        self.unique_images.clear();
        self.unique_indices.clear();
        self.records.clear();
    }

    pub(crate) fn unique_images(&self) -> &[BatchUniqueImage] {
        &self.unique_images
    }

    pub(crate) fn records(&self) -> &[BatchCanvasImage] {
        &self.records
    }

    pub(crate) fn into_parts(self) -> (Vec<BatchUniqueImage>, Vec<BatchCanvasImage>) {
        (self.unique_images, self.records)
    }

    fn unique_index_for(
        &mut self,
        key: u64,
        version: u64,
        width: usize,
        height: usize,
        pixels: Arc<Vec<u8>>,
    ) -> usize {
        let unique_key = (key, version);
        if let Some(index) = self.unique_indices.get(&unique_key) {
            return *index;
        }
        let index = self.unique_images.len();
        self.unique_images.push(BatchUniqueImage {
            key,
            version,
            width,
            height,
            pixels,
        });
        self.unique_indices.insert(unique_key, index);
        index
    }
}

impl BatchUniqueImage {
    fn from_canvas_image(image: &CanvasImage) -> Self {
        Self {
            key: image.key,
            version: image.version,
            width: image.width,
            height: image.height,
            pixels: Arc::clone(&image.pixels),
        }
    }
}
