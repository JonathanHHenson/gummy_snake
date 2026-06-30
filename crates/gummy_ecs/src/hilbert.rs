use crate::error::{EcsError, Result};
use crate::spatial::{
    Dimensions, SpatialAabb, SpatialCapabilities, SpatialIndexBackend, SpatialMemoryStats,
    SpatialPoint, SpatialRecord,
};

#[derive(Debug, Clone)]
pub struct HilbertIndex {
    bounds: SpatialAabb,
    bits: u8,
    records: Vec<(u64, SpatialRecord)>,
}

impl HilbertIndex {
    pub fn new(bounds: SpatialAabb, bits: u8) -> Result<Self> {
        if bounds.dimensions() != Dimensions::D2 {
            return Err(EcsError::InvalidSpatialInput(
                "Hilbert index currently supports 2D bounds; use Octree for 3D spatial queries"
                    .to_string(),
            ));
        }
        if bits == 0 || bits > 31 {
            return Err(EcsError::InvalidSpatialInput(
                "Hilbert bits must be in the range 1..31".to_string(),
            ));
        }
        Ok(Self {
            bounds,
            bits,
            records: Vec::new(),
        })
    }

    pub fn key(&self, point: &SpatialPoint) -> Result<u64> {
        if point.dimensions() != Dimensions::D2 {
            return Err(EcsError::InvalidSpatialInput(
                "Hilbert point dimensions do not match 2D index bounds".to_string(),
            ));
        }
        let max = (1_u64 << self.bits) - 1;
        let x = self.quantize(point, 0, max)?;
        let y = self.quantize(point, 1, max)?;
        Ok(hilbert_xy_to_index(self.bits, x, y))
    }

    fn quantize(&self, point: &SpatialPoint, axis: usize, max: u64) -> Result<u64> {
        let min = self.bounds.minimum().coord(axis);
        let span = self.bounds.maximum().coord(axis) - min;
        if span <= 0.0 || !span.is_finite() {
            return Err(EcsError::InvalidSpatialInput(
                "Hilbert bounds must have positive finite span".to_string(),
            ));
        }
        let normalized = ((point.coord(axis) - min) / span).clamp(0.0, 1.0);
        Ok((normalized * max as f64).round() as u64)
    }
}

impl SpatialIndexBackend for HilbertIndex {
    fn capabilities(&self) -> SpatialCapabilities {
        SpatialCapabilities {
            dimensions: Dimensions::D2,
            radius_queries: true,
            aabb_queries: true,
            incremental_updates: false,
        }
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        SpatialMemoryStats {
            records_len: self.records.len(),
            records_capacity: self.records.capacity(),
            buckets_len: 0,
            buckets_capacity: 0,
            nodes_len: 0,
            overflow_len: 0,
            overflow_capacity: 0,
        }
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.records.clear();
        for record in records {
            if record.point.dimensions() != Dimensions::D2 {
                return Err(EcsError::InvalidSpatialInput(
                    "Hilbert records must be 2D".to_string(),
                ));
            }
            self.records
                .push((self.key(&record.point)?, record.clone()));
        }
        self.records
            .sort_by_key(|(key, record)| (*key, record.entity.raw()));
        Ok(())
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if origin.dimensions() != Dimensions::D2 {
            return Err(EcsError::InvalidSpatialInput(
                "Hilbert radius queries must be 2D".to_string(),
            ));
        }
        if !radius.is_finite() || radius < 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "query radius must be finite and non-negative".to_string(),
            ));
        }
        let bounds = SpatialAabb::point2(
            origin.coord(0) - radius,
            origin.coord(1) - radius,
            origin.coord(0) + radius,
            origin.coord(1) + radius,
        )?;
        self.query_aabb(&bounds, out)?;
        out.retain(|record| {
            origin
                .distance_squared(&record.point)
                .is_ok_and(|distance_sq| distance_sq <= radius * radius)
        });
        Ok(())
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        if bounds.dimensions() != Dimensions::D2 {
            return Err(EcsError::InvalidSpatialInput(
                "Hilbert AABB queries must be 2D".to_string(),
            ));
        }
        out.clear();
        for (_, record) in &self.records {
            let record_bounds = record.bounds.clone().unwrap_or_else(|| {
                SpatialAabb::new(record.point.clone(), record.point.clone()).unwrap()
            });
            if bounds.overlaps(&record_bounds)? {
                out.push(record.clone());
            }
        }
        out.sort_by_key(|record| record.entity.raw());
        Ok(())
    }
}

fn hilbert_xy_to_index(bits: u8, x: u64, y: u64) -> u64 {
    let mut x = x as i64;
    let mut y = y as i64;
    let mut index = 0_u64;
    let mut scale = 1_i64 << (bits - 1);
    while scale > 0 {
        let rx = i64::from((x & scale) > 0);
        let ry = i64::from((y & scale) > 0);
        index += (scale * scale * ((3 * rx) ^ ry)) as u64;
        rotate(scale, &mut x, &mut y, rx, ry);
        scale >>= 1;
    }
    index
}

fn rotate(scale: i64, x: &mut i64, y: &mut i64, rx: i64, ry: i64) {
    if ry == 0 {
        if rx == 1 {
            *x = scale - 1 - *x;
            *y = scale - 1 - *y;
        }
        std::mem::swap(x, y);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::entity::Entity;

    #[test]
    fn hilbert_key_matches_known_2x2_curve_order() {
        let bounds = SpatialAabb::point2(0.0, 0.0, 1.0, 1.0).unwrap();
        let index = HilbertIndex::new(bounds, 1).unwrap();
        assert_eq!(
            index.key(&SpatialPoint::point2(0.0, 0.0).unwrap()).unwrap(),
            0
        );
        assert_eq!(
            index.key(&SpatialPoint::point2(0.0, 1.0).unwrap()).unwrap(),
            1
        );
        assert_eq!(
            index.key(&SpatialPoint::point2(1.0, 1.0).unwrap()).unwrap(),
            2
        );
        assert_eq!(
            index.key(&SpatialPoint::point2(1.0, 0.0).unwrap()).unwrap(),
            3
        );
    }

    #[test]
    fn hilbert_index_sorts_and_queries_candidates() {
        let bounds = SpatialAabb::point2(0.0, 0.0, 10.0, 10.0).unwrap();
        let mut index = HilbertIndex::new(bounds, 8).unwrap();
        let records = vec![SpatialRecord {
            entity: Entity {
                index: 0,
                generation: 0,
            },
            point: SpatialPoint::point2(5.0, 5.0).unwrap(),
            bounds: None,
        }];
        index.build(&records).unwrap();
        let mut out = Vec::new();
        index
            .query_aabb(&SpatialAabb::point2(4.0, 4.0, 6.0, 6.0).unwrap(), &mut out)
            .unwrap();
        assert_eq!(out.len(), 1);
        index
            .query_radius(&SpatialPoint::point2(5.0, 5.0).unwrap(), 0.5, &mut out)
            .unwrap();
        assert_eq!(out.len(), 1);
    }

    #[test]
    fn hilbert_reports_capacity_reuse_stats() {
        let bounds = SpatialAabb::point2(0.0, 0.0, 100.0, 100.0).unwrap();
        let mut index = HilbertIndex::new(bounds, 8).unwrap();
        let records = (0..24)
            .map(|index| SpatialRecord {
                entity: Entity {
                    index,
                    generation: 0,
                },
                point: SpatialPoint::point2(index as f64, 1.0).unwrap(),
                bounds: None,
            })
            .collect::<Vec<_>>();
        index.build(&records).unwrap();
        let first = index.memory_stats();
        assert_eq!(first.records_len, records.len());
        assert!(first.records_capacity >= records.len());

        index.build(&records[..3]).unwrap();
        let second = index.memory_stats();
        assert_eq!(second.records_len, 3);
        assert!(second.records_capacity >= first.records_capacity);
    }

    #[test]
    fn hilbert_rejects_3d_bounds() {
        let bounds = SpatialAabb::point3(0.0, 0.0, 0.0, 1.0, 1.0, 1.0).unwrap();
        assert!(HilbertIndex::new(bounds, 8).is_err());
    }
}
