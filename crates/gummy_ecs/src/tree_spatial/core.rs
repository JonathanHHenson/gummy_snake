use std::collections::HashMap;

use crate::error::{EcsError, Result};
use crate::spatial::{
    Dimensions, SpatialAabb, SpatialCapabilities, SpatialMemoryStats, SpatialPoint, SpatialRecord,
};

use super::geometry::{radius_bounds, record_overlaps, subdivide_bounds};

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

    pub(super) fn build(
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

    pub(super) fn query_aabb(
        &self,
        query: &SpatialAabb,
        out: &mut HashMap<u64, SpatialRecord>,
    ) -> Result<()> {
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

    pub(super) fn visit_aabb_unordered<F>(&self, query: &SpatialAabb, visit: &mut F) -> Result<()>
    where
        F: FnMut(&SpatialRecord) -> Result<()>,
    {
        if !self.bounds.overlaps(query)? {
            return Ok(());
        }
        for record in &self.records {
            if record_overlaps(record, query)? {
                visit(record)?;
            }
        }
        for child in &self.children {
            child.visit_aabb_unordered(query, visit)?;
        }
        Ok(())
    }

    fn node_count(&self) -> usize {
        1 + self.children.iter().map(Self::node_count).sum::<usize>()
    }
}

#[derive(Debug, Clone)]
pub(super) struct TreeIndex {
    dimensions: Dimensions,
    bounds: SpatialAabb,
    capacity: usize,
    max_depth: usize,
    root: Option<TreeNode>,
    overflow: Vec<SpatialRecord>,
}

impl TreeIndex {
    pub(super) fn new(
        dimensions: Dimensions,
        bounds: SpatialAabb,
        capacity: usize,
    ) -> Result<Self> {
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

    pub(super) fn build(&mut self, records: &[SpatialRecord]) -> Result<()> {
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

    pub(super) fn query_aabb(
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

    pub(super) fn query_aabb_unordered(
        &self,
        bounds: &SpatialAabb,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        out.clear();
        self.visit_aabb_unordered(bounds, &mut |record: &SpatialRecord| {
            out.push(record.clone());
            Ok(())
        })
    }

    pub(super) fn visit_aabb_unordered<F>(&self, bounds: &SpatialAabb, visit: &mut F) -> Result<()>
    where
        F: FnMut(&SpatialRecord) -> Result<()>,
    {
        if bounds.dimensions() != self.dimensions {
            return Err(EcsError::InvalidSpatialInput(
                "tree query dimensions do not match index dimensions".to_string(),
            ));
        }
        if let Some(root) = &self.root {
            root.visit_aabb_unordered(bounds, visit)?;
        }
        for record in &self.overflow {
            if record_overlaps(record, bounds)? {
                visit(record)?;
            }
        }
        Ok(())
    }

    pub(super) fn query_radius(
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

    pub(super) fn query_radius_unordered(
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

    pub(super) fn capabilities(&self) -> SpatialCapabilities {
        SpatialCapabilities {
            dimensions: self.dimensions,
            radius_queries: true,
            aabb_queries: true,
            incremental_updates: false,
        }
    }

    pub(super) fn memory_stats(&self) -> SpatialMemoryStats {
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
