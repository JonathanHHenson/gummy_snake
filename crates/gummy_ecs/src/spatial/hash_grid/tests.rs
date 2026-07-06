use super::*;
use crate::entity::Entity;
use crate::spatial::{Dimensions, SpatialAabb, SpatialIndexBackend, SpatialPoint, SpatialRecord};

fn entity(index: u32) -> Entity {
    Entity {
        index,
        generation: 0,
    }
}

#[test]
fn hash_grid_returns_radius_matches_in_entity_order() {
    let records = vec![
        SpatialRecord {
            entity: entity(2),
            point: SpatialPoint::point2(10.0, 0.0).unwrap(),
            bounds: None,
        },
        SpatialRecord {
            entity: entity(0),
            point: SpatialPoint::point2(0.0, 0.0).unwrap(),
            bounds: None,
        },
        SpatialRecord {
            entity: entity(1),
            point: SpatialPoint::point2(3.0, 4.0).unwrap(),
            bounds: None,
        },
    ];
    let mut index = HashGridIndex::new(Dimensions::D2, 5.0).unwrap();
    index.build(&records).unwrap();
    let mut out = Vec::new();
    index
        .query_radius(&SpatialPoint::point2(0.0, 0.0).unwrap(), 5.0, &mut out)
        .unwrap();
    assert_eq!(
        out.iter()
            .map(|record| record.entity.index)
            .collect::<Vec<_>>(),
        vec![0, 1]
    );
}

#[test]
fn hash_grid_handles_negative_3d_cells_deterministically() {
    let records = vec![
        SpatialRecord {
            entity: entity(1),
            point: SpatialPoint::point3(-2.0, -2.0, -2.0).unwrap(),
            bounds: None,
        },
        SpatialRecord {
            entity: entity(0),
            point: SpatialPoint::point3(-1.0, -1.0, -1.0).unwrap(),
            bounds: None,
        },
    ];
    let mut index = HashGridIndex::new(Dimensions::D3, 2.0).unwrap();
    index.build(&records).unwrap();
    let mut out = Vec::new();
    index
        .query_radius(
            &SpatialPoint::point3(-1.0, -1.0, -1.0).unwrap(),
            2.0,
            &mut out,
        )
        .unwrap();
    assert_eq!(
        out.iter()
            .map(|record| record.entity.index)
            .collect::<Vec<_>>(),
        vec![0, 1]
    );
}

#[test]
fn hash_grid_reports_capacity_reuse_stats() {
    let records = (0..32)
        .map(|index| SpatialRecord {
            entity: entity(index),
            point: SpatialPoint::point2(index as f64, 0.0).unwrap(),
            bounds: None,
        })
        .collect::<Vec<_>>();
    let mut index = HashGridIndex::new(Dimensions::D2, 2.0).unwrap();
    index.build(&records).unwrap();
    let first = index.memory_stats();
    assert_eq!(first.records_len, records.len());
    assert!(first.records_capacity >= records.len());
    assert!(first.buckets_len > 0);
    assert!(first.buckets_capacity >= first.buckets_len);

    index.build(&records[..4]).unwrap();
    let second = index.memory_stats();
    assert_eq!(second.records_len, 4);
    assert!(second.records_capacity >= first.records_capacity);
    assert!(second.buckets_capacity >= first.buckets_capacity);
}

#[test]
fn hash_grid_incremental_update_matches_full_rebuild() {
    let initial = (0..16)
        .map(|index| SpatialRecord {
            entity: entity(index),
            point: SpatialPoint::point2(index as f64, 0.0).unwrap(),
            bounds: None,
        })
        .collect::<Vec<_>>();
    let updated = (4..20)
        .map(|index| SpatialRecord {
            entity: entity(index),
            point: SpatialPoint::point2((index % 5) as f64, (index / 5) as f64).unwrap(),
            bounds: None,
        })
        .collect::<Vec<_>>();
    let mut incremental = HashGridIndex::new(Dimensions::D2, 2.0).unwrap();
    let mut rebuilt = HashGridIndex::new(Dimensions::D2, 2.0).unwrap();
    incremental.build(&initial).unwrap();
    assert!(incremental.update_incremental(&updated).unwrap());
    rebuilt.build(&updated).unwrap();

    let origin = SpatialPoint::point2(2.0, 2.0).unwrap();
    let mut incremental_rows = Vec::new();
    let mut rebuilt_rows = Vec::new();
    incremental
        .query_radius(&origin, 4.0, &mut incremental_rows)
        .unwrap();
    rebuilt
        .query_radius(&origin, 4.0, &mut rebuilt_rows)
        .unwrap();
    assert_eq!(
        incremental_rows
            .iter()
            .map(|record| record.entity.raw())
            .collect::<Vec<_>>(),
        rebuilt_rows
            .iter()
            .map(|record| record.entity.raw())
            .collect::<Vec<_>>()
    );
}

#[test]
fn hash_grid_incremental_falls_back_for_bounds_records() {
    let records = vec![SpatialRecord {
        entity: entity(0),
        point: SpatialPoint::point2(0.0, 0.0).unwrap(),
        bounds: Some(SpatialAabb::point2(-1.0, -1.0, 1.0, 1.0).unwrap()),
    }];
    let mut index = HashGridIndex::new(Dimensions::D2, 2.0).unwrap();
    index.build(&[]).unwrap();
    assert!(!index.update_incremental(&records).unwrap());
    let mut out = Vec::new();
    index
        .query_aabb(
            &SpatialAabb::point2(-0.5, -0.5, 0.5, 0.5).unwrap(),
            &mut out,
        )
        .unwrap();
    assert_eq!(out.len(), 1);
}

#[test]
fn hash_grid_returns_aabb_matches_in_entity_order() {
    let records = vec![
        SpatialRecord {
            entity: entity(2),
            point: SpatialPoint::point2(20.0, 0.0).unwrap(),
            bounds: Some(SpatialAabb::point2(19.0, -1.0, 21.0, 1.0).unwrap()),
        },
        SpatialRecord {
            entity: entity(0),
            point: SpatialPoint::point2(0.0, 0.0).unwrap(),
            bounds: Some(SpatialAabb::point2(-2.0, -2.0, 2.0, 2.0).unwrap()),
        },
        SpatialRecord {
            entity: entity(1),
            point: SpatialPoint::point2(3.0, 0.0).unwrap(),
            bounds: Some(SpatialAabb::point2(1.0, -1.0, 4.0, 1.0).unwrap()),
        },
    ];
    let mut index = HashGridIndex::new(Dimensions::D2, 4.0).unwrap();
    index.build(&records).unwrap();
    let mut out = Vec::new();
    index
        .query_aabb(
            &SpatialAabb::point2(-1.0, -1.0, 2.5, 1.0).unwrap(),
            &mut out,
        )
        .unwrap();
    assert_eq!(
        out.iter()
            .map(|record| record.entity.index)
            .collect::<Vec<_>>(),
        vec![0, 1]
    );
}

#[test]
fn hash_grid_rejects_pathological_cell_spans() {
    let mut index = HashGridIndex::new(Dimensions::D2, 1.0).unwrap();
    index.build(&[]).unwrap();
    let mut out = Vec::new();
    let err = index
        .query_aabb(
            &SpatialAabb::point2(0.0, 0.0, 2_000.0, 2_000.0).unwrap(),
            &mut out,
        )
        .unwrap_err();
    assert!(err.to_string().contains("maximum"));
}
