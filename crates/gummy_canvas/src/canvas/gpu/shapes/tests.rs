use super::records::stroke_path_records;
use crate::Rgba;

#[test]
fn stroke_path_records_carry_matrix_style_and_logical_points() {
    let records = stroke_path_records(
        &[(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)],
        true,
        (2.0, 0.5, 0.25, 3.0, 5.0, 7.0),
        2.0,
        6.0,
        Rgba {
            r: 255,
            g: 0,
            b: 0,
            a: 128,
        },
    );

    assert_eq!(records[0], [2.0, 0.5, 0.25, 3.0]);
    assert_eq!(records[1], [5.0, 7.0, 2.0, 6.0]);
    assert_eq!(records[2], [1.0, 0.0, 0.0, 128.0 / 255.0]);
    assert_eq!(records[3], [3.0, 1.0, 0.0, 0.0]);
    assert_eq!(records[4], [1.0, 2.0, 0.0, 0.0]);
    assert_eq!(records[5], [3.0, 4.0, 0.0, 0.0]);
    assert_eq!(records[6], [5.0, 6.0, 0.0, 0.0]);
}
