use super::*;
use crate::entity::Entity;
use crate::spatial::{SpatialAabb, SpatialIndexBackend, SpatialPoint, SpatialRecord};

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
