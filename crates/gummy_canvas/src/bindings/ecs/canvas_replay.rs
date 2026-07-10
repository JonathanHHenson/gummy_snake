use gummy_ecs::{EcsValue, ExecutionCanvasCommand, ExecutionCanvasFillRecord, ExecutionReport};
use pyo3::prelude::*;

use crate::{Canvas, Matrix};

pub(super) type FillPrimitiveRecord = (u8, f64, f64, f64, f64, f64, f64, u8, u8, u8, u8);

const PRIMITIVE_BATCH_RECT: u8 = 1;
const PRIMITIVE_BATCH_TRIANGLE: u8 = 2;
const PRIMITIVE_BATCH_ELLIPSE: u8 = 3;

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
    let (r, g, b, a) = fill;
    match command.command.as_str() {
        "rect" => {
            let args = numeric_args(&command.args, 4)?;
            Some((
                PRIMITIVE_BATCH_RECT,
                args[0],
                args[1],
                args[2],
                args[3],
                0.0,
                0.0,
                r,
                g,
                b,
                a,
            ))
        }
        "circle" => {
            let args = numeric_args(&command.args, 3)?;
            let diameter = args[2];
            Some((
                PRIMITIVE_BATCH_ELLIPSE,
                args[0] - diameter / 2.0,
                args[1] - diameter / 2.0,
                diameter,
                diameter,
                0.0,
                0.0,
                r,
                g,
                b,
                a,
            ))
        }
        "ellipse" => {
            let args = if command.args.len() == 3 {
                let args = numeric_args(&command.args, 3)?;
                vec![args[0], args[1], args[2], args[2]]
            } else {
                numeric_args(&command.args, 4)?
            };
            Some((
                PRIMITIVE_BATCH_ELLIPSE,
                args[0] - args[2] / 2.0,
                args[1] - args[3] / 2.0,
                args[2],
                args[3],
                0.0,
                0.0,
                r,
                g,
                b,
                a,
            ))
        }
        "triangle" => {
            let args = numeric_args(&command.args, 6)?;
            Some((
                PRIMITIVE_BATCH_TRIANGLE,
                args[0],
                args[1],
                args[2],
                args[3],
                args[4],
                args[5],
                r,
                g,
                b,
                a,
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

fn fill_record_tuple(record: &ExecutionCanvasFillRecord) -> FillPrimitiveRecord {
    (
        record.kind,
        record.a,
        record.b,
        record.c,
        record.d,
        record.e,
        record.f,
        record.r,
        record.g,
        record.blue,
        record.alpha,
    )
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
        let records = batch
            .records
            .iter()
            .map(fill_record_tuple)
            .collect::<Vec<_>>();
        canvas.batch_fill_primitives_impl(records, matrix)?;
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
        records.extend(batch.records.iter().map(fill_record_tuple));
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
    canvas.batch_fill_primitives_impl(pending, matrix)
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
    canvas.batch_fill_primitives_impl(records, matrix)?;
    report.canvas_commands = vec![final_fill_command];
    Ok(record_count)
}
