use std::collections::HashMap;

use crate::error::{EcsError, Result};
use crate::spatial::{
    Dimensions, SpatialAabb, SpatialCapabilities, SpatialIndexBackend, SpatialMemoryStats,
    SpatialPoint, SpatialRecord,
};

const DEFAULT_MAX_DEPTH: usize = 12;

#[derive(Debug, Clone)]
struct TreeNode {
    bounds: SpatialAabb,
    records: Vec<SpatialRecord>,
    children: Vec<TreeNode>,
}

impl TreeNode {
    fn leaf(bounds: SpatialAabb, records: Vec<SpatialRecord>) -> Self {
        Self {
            bounds,
            records,
            children: Vec::new(),
        }
    }

    fn build(
        bounds: SpatialAabb,
        records: Vec<SpatialRecord>,
        dimensions: Dimensions,
        capacity: usize,
        depth: usize,
        max_depth: usize,
    ) -> Result<Self> {
        if records.len() <= capacity || depth >= max_depth {
            return Ok(Self::leaf(bounds, records));
        }
        let child_bounds = subdivide_bounds(&bounds, dimensions)?;
        let mut child_records = vec![Vec::new(); child_bounds.len()];
        let mut retained = Vec::new();
        for record in records {
            let mut matches = Vec::new();
            for (index, child_bound) in child_bounds.iter().enumerate() {
                if record_overlaps(&record, child_bound)? {
                    matches.push(index);
                }
            }
            if matches.is_empty() {
                retained.push(record);
            } else if matches.len() == 1 {
                child_records[matches[0]].push(record);
            } else {
                // Wide AABBs are retained at the parent to avoid excessive duplication.
                retained.push(record);
            }
        }
        let mut children = Vec::new();
        for (bounds, records) in child_bounds.into_iter().zip(child_records) {
            if !records.is_empty() {
                children.push(Self::build(
                    bounds,
                    records,
                    dimensions,
                    capacity,
                    depth + 1,
                    max_depth,
                )?);
            }
        }
        Ok(Self {
            bounds,
            records: retained,
            children,
        })
    }

    fn query_aabb(&self, query: &SpatialAabb, out: &mut HashMap<u64, SpatialRecord>) -> Result<()> {
        if !self.bounds.overlaps(query)? {
            return Ok(());
        }
        for record in &self.records {
            if record_overlaps(record, query)? {
                out.insert(record.entity.raw(), record.clone());
            }
        }
        for child in &self.children {
            child.query_aabb(query, out)?;
        }
        Ok(())
    }

    fn query_aabb_unordered(
        &self,
        query: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if !self.bounds.overlaps(query)? {
            return Ok(());
        }
        for record in &self.records {
            if record_overlaps(record, query)? {
                out.push(record.clone());
            }
        }
        for child in &self.children {
            child.query_aabb_unordered(query, out)?;
        }
        Ok(())
    }

    fn node_count(&self) -> usize {
        1 + self.children.iter().map(Self::node_count).sum::<usize>()
    }
}

#[derive(Debug, Clone)]
struct TreeIndex {
    dimensions: Dimensions,
    bounds: SpatialAabb,
    capacity: usize,
    max_depth: usize,
    root: Option<TreeNode>,
    overflow: Vec<SpatialRecord>,
}

impl TreeIndex {
    fn new(dimensions: Dimensions, bounds: SpatialAabb, capacity: usize) -> Result<Self> {
        if bounds.dimensions() != dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "tree bounds dimensions do not match index dimensions".to_string(),
            ));
        }
        Ok(Self {
            dimensions,
            bounds,
            capacity: capacity.max(1),
            max_depth: DEFAULT_MAX_DEPTH,
            root: None,
            overflow: Vec::new(),
        })
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        let mut in_bounds = Vec::new();
        self.overflow.clear();
        for record in records {
            if record.point.dimensions() != self.dimensions {
                return Err(EcsError::InvalidSpatialInput(
                    "tree record dimensions do not match index dimensions".to_string(),
                ));
            }
            if record_overlaps(record, &self.bounds)? {
                in_bounds.push(record.clone());
            } else {
                self.overflow.push(record.clone());
            }
        }
        in_bounds.sort_by_key(|record| record.entity.raw());
        self.overflow.sort_by_key(|record| record.entity.raw());
        self.root = Some(TreeNode::build(
            self.bounds.clone(),
            in_bounds,
            self.dimensions,
            self.capacity,
            0,
            self.max_depth,
        )?);
        Ok(())
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        if bounds.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "tree query dimensions do not match index dimensions".to_string(),
            ));
        }
        out.clear();
        let mut seen = HashMap::new();
        if let Some(root) = &self.root {
            root.query_aabb(bounds, &mut seen)?;
        }
        for record in &self.overflow {
            if record_overlaps(record, bounds)? {
                seen.insert(record.entity.raw(), record.clone());
            }
        }
        let mut keys = seen.keys().copied().collect::<Vec<_>>();
        keys.sort_unstable();
        for key in keys {
            out.push(seen.remove(&key).expect("key came from map"));
        }
        Ok(())
    }

    fn query_aabb_unordered(
        &self,
        bounds: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if bounds.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "tree query dimensions do not match index dimensions".to_string(),
            ));
        }
        out.clear();
        if let Some(root) = &self.root {
            root.query_aabb_unordered(bounds, out)?;
        }
        for record in &self.overflow {
            if record_overlaps(record, bounds)? {
                out.push(record.clone());
            }
        }
        Ok(())
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if origin.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "tree radius query dimensions do not match index dimensions".to_string(),
            ));
        }
        if !radius.is_finite() || radius < 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "query radius must be finite and non-negative".to_string(),
            ));
        }
        let bounds = radius_bounds(origin, radius, self.dimensions)?;
        self.query_aabb(&bounds, out)?;
        out.retain(|record| {
            origin
                .distance_squared(&record.point)
                .is_ok_and(|distance_sq| distance_sq <= radius * radius)
        });
        Ok(())
    }

    fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        if origin.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "tree radius query dimensions do not match index dimensions".to_string(),
            ));
        }
        if !radius.is_finite() || radius < 0.0 {
            return Err(EcsError::InvalidSpatialInput(
                "query radius must be finite and non-negative".to_string(),
            ));
        }
        let bounds = radius_bounds(origin, radius, self.dimensions)?;
        self.query_aabb_unordered(&bounds, out)?;
        let radius_sq = radius * radius;
        out.retain(|record| {
            origin
                .distance_squared(&record.point)
                .is_ok_and(|distance_sq| distance_sq <= radius_sq)
        });
        Ok(())
    }

    fn capabilities(&self) -> SpatialCapabilities {
        SpatialCapabilities {
            dimensions: self.dimensions,
            radius_queries: true,
            aabb_queries: true,
            incremental_updates: false,
        }
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        SpatialMemoryStats {
            records_len: 0,
            records_capacity: 0,
            buckets_len: 0,
            buckets_capacity: 0,
            nodes_len: self.root.as_ref().map_or(0, TreeNode::node_count),
            overflow_len: self.overflow.len(),
            overflow_capacity: self.overflow.capacity(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct QuadtreeIndex {
    inner: TreeIndex,
}

impl QuadtreeIndex {
    pub fn new(bounds: SpatialAabb, capacity: usize) -> Result<Self> {
        Ok(Self {
            inner: TreeIndex::new(Dimensions::D2, bounds, capacity)?,
        })
    }

    pub fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius_unordered(origin, radius, out)
    }
}

impl SpatialIndexBackend for QuadtreeIndex {
    fn capabilities(&self) -> SpatialCapabilities {
        self.inner.capabilities()
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        self.inner.memory_stats()
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.inner.build(records)
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius(origin, radius, out)
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        self.inner.query_aabb(bounds, out)
    }
}

#[derive(Debug, Clone)]
pub struct OctreeIndex {
    inner: TreeIndex,
}

impl OctreeIndex {
    pub fn new(bounds: SpatialAabb, capacity: usize) -> Result<Self> {
        Ok(Self {
            inner: TreeIndex::new(Dimensions::D3, bounds, capacity)?,
        })
    }

    pub fn query_radius_unordered(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius_unordered(origin, radius, out)
    }
}

impl SpatialIndexBackend for OctreeIndex {
    fn capabilities(&self) -> SpatialCapabilities {
        self.inner.capabilities()
    }

    fn memory_stats(&self) -> SpatialMemoryStats {
        self.inner.memory_stats()
    }

    fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
        self.inner.build(records)
    }

    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        self.inner.query_radius(origin, radius, out)
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        self.inner.query_aabb(bounds, out)
    }
}

fn record_overlaps(record: &SpatialRecord, bounds: &SpatialAabb) -> Result<bool> {
    match &record.bounds {
        Some(record_bounds) => bounds.overlaps(record_bounds),
        None => point_in_aabb(&record.point, bounds),
    }
}

fn point_in_aabb(point: &SpatialPoint, bounds: &SpatialAabb) -> Result<bool> {
    if point.dimensions() != bounds.dimensions() {
        return Err(EcsError::InvalidSpatialInput(
            "point dimensions do not match bounds dimensions".to_string(),
        ));
    }
    Ok((0..point.dimensions().len()).all(|axis| {
        bounds.minimum().coord(axis) <= point.coord(axis)
            && point.coord(axis) <= bounds.maximum().coord(axis)
    }))
}

fn radius_bounds(
    origin: &SpatialPoint,
    radius: f64,
    dimensions: Dimensions,
) -> Result<SpatialAabb> {
    match dimensions {
        Dimensions::D2 => SpatialAabb::point2(
            origin.coord(0) - radius,
            origin.coord(1) - radius,
            origin.coord(0) + radius,
            origin.coord(1) + radius,
        ),
        Dimensions::D3 => SpatialAabb::point3(
            origin.coord(0) - radius,
            origin.coord(1) - radius,
            origin.coord(2) - radius,
            origin.coord(0) + radius,
            origin.coord(1) + radius,
            origin.coord(2) + radius,
        ),
    }
}

fn subdivide_bounds(bounds: &SpatialAabb, dimensions: Dimensions) -> Result<Vec<SpatialAabb>> {
    let mid_x = midpoint(bounds, 0);
    let mid_y = midpoint(bounds, 1);
    if dimensions == Dimensions::D2 {
        return Ok(vec![
            SpatialAabb::point2(
                bounds.minimum().coord(0),
                bounds.minimum().coord(1),
                mid_x,
                mid_y,
            )?,
            SpatialAabb::point2(
                mid_x,
                bounds.minimum().coord(1),
                bounds.maximum().coord(0),
                mid_y,
            )?,
            SpatialAabb::point2(
                bounds.minimum().coord(0),
                mid_y,
                mid_x,
                bounds.maximum().coord(1),
            )?,
            SpatialAabb::point2(
                mid_x,
                mid_y,
                bounds.maximum().coord(0),
                bounds.maximum().coord(1),
            )?,
        ]);
    }
    let mid_z = midpoint(bounds, 2);
    let mut children = Vec::new();
    for min_x in [bounds.minimum().coord(0), mid_x] {
        let max_x = if min_x == bounds.minimum().coord(0) {
            mid_x
        } else {
            bounds.maximum().coord(0)
        };
        for min_y in [bounds.minimum().coord(1), mid_y] {
            let max_y = if min_y == bounds.minimum().coord(1) {
                mid_y
            } else {
                bounds.maximum().coord(1)
            };
            for min_z in [bounds.minimum().coord(2), mid_z] {
                let max_z = if min_z == bounds.minimum().coord(2) {
                    mid_z
                } else {
                    bounds.maximum().coord(2)
                };
                children.push(SpatialAabb::point3(
                    min_x, min_y, min_z, max_x, max_y, max_z,
                )?);
            }
        }
    }
    Ok(children)
}

fn midpoint(bounds: &SpatialAabb, axis: usize) -> f64 {
    (bounds.minimum().coord(axis) + bounds.maximum().coord(axis)) * 0.5
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::entity::Entity;

    fn entity(index: u32) -> Entity {
        Entity {
            index,
            generation: 0,
        }
    }

    #[test]
    fn quadtree_returns_aabb_and_radius_matches() {
        let bounds = SpatialAabb::point2(-10.0, -10.0, 10.0, 10.0).unwrap();
        let mut tree = QuadtreeIndex::new(bounds, 1).unwrap();
        let records = vec![
            SpatialRecord {
                entity: entity(0),
                point: SpatialPoint::point2(0.0, 0.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(1),
                point: SpatialPoint::point2(8.0, 8.0).unwrap(),
                bounds: None,
            },
        ];
        tree.build(&records).unwrap();
        let mut out = Vec::new();
        tree.query_aabb(
            &SpatialAabb::point2(-1.0, -1.0, 1.0, 1.0).unwrap(),
            &mut out,
        )
        .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![0]
        );
        tree.query_radius(&SpatialPoint::point2(0.0, 0.0).unwrap(), 2.0, &mut out)
            .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![0]
        );
    }

    #[test]
    fn quadtree_scans_out_of_bounds_overflow_deterministically() {
        let bounds = SpatialAabb::point2(0.0, 0.0, 10.0, 10.0).unwrap();
        let mut tree = QuadtreeIndex::new(bounds, 1).unwrap();
        let records = vec![
            SpatialRecord {
                entity: entity(5),
                point: SpatialPoint::point2(50.0, 50.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(4),
                point: SpatialPoint::point2(5.0, 5.0).unwrap(),
                bounds: None,
            },
        ];
        tree.build(&records).unwrap();
        let mut out = Vec::new();
        tree.query_aabb(
            &SpatialAabb::point2(49.0, 49.0, 51.0, 51.0).unwrap(),
            &mut out,
        )
        .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![5]
        );
    }

    #[test]
    fn tree_backends_report_node_and_overflow_stats() {
        let bounds = SpatialAabb::point2(0.0, 0.0, 10.0, 10.0).unwrap();
        let mut index = QuadtreeIndex::new(bounds, 1).unwrap();
        let records = vec![
            SpatialRecord {
                entity: entity(0),
                point: SpatialPoint::point2(1.0, 1.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(1),
                point: SpatialPoint::point2(9.0, 9.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(2),
                point: SpatialPoint::point2(20.0, 20.0).unwrap(),
                bounds: None,
            },
        ];
        index.build(&records).unwrap();
        let stats = index.memory_stats();
        assert!(stats.nodes_len >= 1);
        assert_eq!(stats.overflow_len, 1);
        assert!(stats.overflow_capacity >= 1);
    }

    #[test]
    fn octree_returns_3d_radius_matches() {
        let bounds = SpatialAabb::point3(-10.0, -10.0, -10.0, 10.0, 10.0, 10.0).unwrap();
        let mut tree = OctreeIndex::new(bounds, 1).unwrap();
        let records = vec![
            SpatialRecord {
                entity: entity(2),
                point: SpatialPoint::point3(0.0, 0.0, 0.0).unwrap(),
                bounds: None,
            },
            SpatialRecord {
                entity: entity(3),
                point: SpatialPoint::point3(5.0, 5.0, 5.0).unwrap(),
                bounds: None,
            },
        ];
        tree.build(&records).unwrap();
        let mut out = Vec::new();
        tree.query_radius(&SpatialPoint::point3(0.0, 0.0, 0.0).unwrap(), 1.0, &mut out)
            .unwrap();
        assert_eq!(
            out.iter()
                .map(|record| record.entity.index)
                .collect::<Vec<_>>(),
            vec![2]
        );
    }
}
