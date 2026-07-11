use gummy_ecs::{EcsValue, ExecutionCanvasCommand, ExecutionCanvasFillRecord, ExecutionReport};
use pyo3::prelude::*;

use crate::canvas_state::Canvas;
use crate::raster::Matrix;

type FillPrimitiveTuple = (u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8);

#[derive(Debug, Clone, Copy, PartialEq)]
pub(super) struct FillPrimitiveRecord {
    kind: u8,
    a: f64,
    b: f64,
    c: f64,
    d: f64,
    e: f64,
    f: f64,
    r: u8,
    g: u8,
    blue: u8,
    alpha: u8,
}

impl FillPrimitiveRecord {
    fn from_execution(record: &ExecutionCanvasFillRecord) -> Self {
        Self {
            kind: record.kind,
            a: record.a,
            b: record.b,
            c: record.c,
            d: record.d,
            e: record.e,
            f: record.f,
            r: record.r,
            g: record.g,
            blue: record.blue,
            alpha: record.alpha,
        }
    }

    fn rect(x: f64, y: f64, width: f64, height: f64, color: [u8; 4]) -> Self {
        Self::rect_like(1, x, y, width, height, color)
    }

    fn ellipse_centered(
        center_x: f64,
        center_y: f64,
        width: f64,
        height: f64,
        color: [u8; 4],
    ) -> Self {
        Self::rect_like(
            3,
            center_x - width / 2.0,
            center_y - height / 2.0,
            width,
            height,
            color,
        )
    }

    fn triangle(first: (f64, f64), second: (f64, f64), third: (f64, f64), color: [u8; 4]) -> Self {
        let [r, g, blue, alpha] = color;
        Self {
            kind: 2,
            a: first.0,
            b: first.1,
            c: second.0,
            d: second.1,
            e: third.0,
            f: third.1,
            r,
            g,
            blue,
            alpha,
        }
    }

    fn rect_like(kind: u8, x: f64, y: f64, width: f64, height: f64, color: [u8; 4]) -> Self {
        let [r, g, blue, alpha] = color;
        Self {
            kind,
            a: x,
            b: y,
            c: width,
            d: height,
            e: 0.0,
            f: 0.0,
            r,
            g,
            blue,
            alpha,
        }
    }

    fn into_tuple(self) -> FillPrimitiveTuple {
        (
            self.kind, self.a, self.b, self.c, self.d, self.e, self.f, self.r, self.g, self.blue,
            self.alpha,
        )
    }
}

fn ecs_value_f64(value: &EcsValue) -> Option<f64> {
    match value {
        EcsValue::F64(value) => Some(*value),
        EcsValue::I64(value) => Some(*value as f64),
        EcsValue::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        _ => None,
    }
}

fn color_channel(value: f64) -> u8 {
    value.clamp(0.0, 255.0).round() as u8
}

fn parse_fill(args: &[EcsValue]) -> Option<(u8, u8, u8, u8)> {
    if !(args.len() == 3 || args.len() == 4) {
        return None;
    }
    let r = color_channel(ecs_value_f64(&args[0])?);
    let g = color_channel(ecs_value_f64(&args[1])?);
    let b = color_channel(ecs_value_f64(&args[2])?);
    let a = if args.len() == 4 {
        color_channel(ecs_value_f64(&args[3])?)
    } else {
        255
    };
    Some((r, g, b, a))
}

fn numeric_args(args: &[EcsValue], expected: usize) -> Option<Vec<f64>> {
    if args.len() != expected {
        return None;
    }
    args.iter().map(ecs_value_f64).collect()
}

fn fill_primitive_record(
    command: &ExecutionCanvasCommand,
    fill: (u8, u8, u8, u8),
) -> Option<FillPrimitiveRecord> {
    let color = [fill.0, fill.1, fill.2, fill.3];
    match command.command.as_str() {
        "rect" => {
            let args = numeric_args(&command.args, 4)?;
            Some(FillPrimitiveRecord::rect(
                args[0], args[1], args[2], args[3], color,
            ))
        }
        "circle" => {
            let args = numeric_args(&command.args, 3)?;
            Some(FillPrimitiveRecord::ellipse_centered(
                args[0], args[1], args[2], args[2], color,
            ))
        }
        "ellipse" => {
            let args = numeric_args(&command.args, command.args.len())?;
            match args.as_slice() {
                [center_x, center_y, width] => Some(FillPrimitiveRecord::ellipse_centered(
                    *center_x, *center_y, *width, *width, color,
                )),
                [center_x, center_y, width, height] => Some(FillPrimitiveRecord::ellipse_centered(
                    *center_x, *center_y, *width, *height, color,
                )),
                _ => None,
            }
        }
        "triangle" => {
            let args = numeric_args(&command.args, 6)?;
            Some(FillPrimitiveRecord::triangle(
                (args[0], args[1]),
                (args[2], args[3]),
                (args[4], args[5]),
                color,
            ))
        }
        _ => None,
    }
}

fn is_style_only_canvas_command(command: &str) -> bool {
    matches!(
        command,
        "fill"
            | "no_fill"
            | "stroke"
            | "no_stroke"
            | "stroke_weight"
            | "stroke_cap"
            | "stroke_join"
            | "color_mode"
            | "rect_mode"
            | "ellipse_mode"
            | "image_mode"
    )
}

fn fill_record(record: &ExecutionCanvasFillRecord) -> FillPrimitiveRecord {
    FillPrimitiveRecord::from_execution(record)
}

fn fill_record_tuples(records: Vec<FillPrimitiveRecord>) -> Vec<FillPrimitiveTuple> {
    records
        .into_iter()
        .map(FillPrimitiveRecord::into_tuple)
        .collect()
}

pub(super) fn replay_fill_batches_to_canvas(
    report: &mut ExecutionReport,
    canvas: &mut Canvas,
    matrix: Matrix,
) -> PyResult<usize> {
    let batches = std::mem::take(&mut report.canvas_fill_batches);
    let mut record_count = 0;
    for batch in batches {
        if batch.records.is_empty() {
            continue;
        }
        record_count += batch.records.len();
        let records = batch.records.iter().map(fill_record).collect::<Vec<_>>();
        canvas.batch_fill_primitives_impl(fill_record_tuples(records), matrix)?;
    }
    Ok(record_count)
}

pub(super) fn append_fill_batches_to_records(
    report: &mut ExecutionReport,
    records: &mut Vec<FillPrimitiveRecord>,
) -> usize {
    let batches = std::mem::take(&mut report.canvas_fill_batches);
    let mut record_count = 0;
    for batch in batches {
        record_count += batch.records.len();
        records.extend(batch.records.iter().map(fill_record));
    }
    record_count
}

pub(super) fn flush_fill_records_to_canvas(
    records: &mut Vec<FillPrimitiveRecord>,
    canvas: &mut Canvas,
    matrix: Matrix,
) -> PyResult<()> {
    if records.is_empty() {
        return Ok(());
    }
    let pending = std::mem::take(records);
    canvas.batch_fill_primitives_impl(fill_record_tuples(pending), matrix)
}

pub(super) fn report_has_only_style_canvas_commands(report: &ExecutionReport) -> bool {
    report
        .canvas_commands
        .iter()
        .all(|command| is_style_only_canvas_command(&command.command))
}

pub(super) fn replay_convertible_fill_primitives_to_canvas(
    report: &mut ExecutionReport,
    canvas: &mut Canvas,
    matrix: Matrix,
    direct_fill_allowed: bool,
) -> PyResult<usize> {
    if !direct_fill_allowed || report.canvas_commands.is_empty() {
        return Ok(0);
    }

    let mut fill: Option<(u8, u8, u8, u8)> = None;
    let mut final_fill_command: Option<ExecutionCanvasCommand> = None;
    let mut records = Vec::new();

    for command in &report.canvas_commands {
        match command.command.as_str() {
            "fill" => {
                fill = parse_fill(&command.args);
                if fill.is_none() {
                    return Ok(0);
                }
                final_fill_command = Some(command.clone());
            }
            command_name if is_style_only_canvas_command(command_name) => {
                // Direct primitive replay cannot safely infer the renderer-state effects of
                // other style commands. Keep the whole report on the ordered Python path.
                // Consecutive fill updates are safe: native records retain each color and
                // Python only needs the final one for subsequent commands.
                return Ok(0);
            }
            _ => {
                let Some(current_fill) = fill else {
                    return Ok(0);
                };
                let Some(record) = fill_primitive_record(command, current_fill) else {
                    return Ok(0);
                };
                records.push(record);
            }
        }
    }

    let Some(final_fill_command) = final_fill_command else {
        return Ok(0);
    };
    if records.is_empty() {
        return Ok(0);
    }

    let record_count = records.len();
    canvas.batch_fill_primitives_impl(fill_record_tuples(records), matrix)?;
    report.canvas_commands = vec![final_fill_command];
    Ok(record_count)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn command(command: &str, args: Vec<f64>) -> ExecutionCanvasCommand {
        ExecutionCanvasCommand {
            command: command.to_string(),
            args: args.into_iter().map(EcsValue::F64).collect(),
        }
    }

    #[test]
    fn direct_fill_records_keep_centered_ellipse_and_clamped_colors() {
        let fill = parse_fill(&[
            EcsValue::F64(12.4),
            EcsValue::F64(100.6),
            EcsValue::F64(260.0),
            EcsValue::F64(-3.0),
        ])
        .expect("valid fill");
        assert_eq!(fill, (12, 101, 255, 0));

        let circle = fill_primitive_record(&command("circle", vec![2.0, 3.0, 6.0]), fill)
            .expect("circle converts");
        assert_eq!(
            circle,
            FillPrimitiveRecord {
                kind: 3,
                a: -1.0,
                b: 0.0,
                c: 6.0,
                d: 6.0,
                e: 0.0,
                f: 0.0,
                r: 12,
                g: 101,
                blue: 255,
                alpha: 0,
            }
        );

        let ellipse = fill_primitive_record(&command("ellipse", vec![8.0, 9.0, 4.0]), fill)
            .expect("three-argument ellipse converts");
        assert_eq!(ellipse.a, 6.0);
        assert_eq!(ellipse.b, 7.0);
        assert_eq!(ellipse.c, 4.0);
        assert_eq!(ellipse.d, 4.0);
    }

    #[test]
    fn execution_record_tuple_conversion_preserves_protocol_layout() {
        let record =
            ExecutionCanvasFillRecord::triangle((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), [7, 8, 9, 10]);
        assert_eq!(
            fill_record(&record).into_tuple(),
            (2, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7, 8, 9, 10)
        );
    }
}
