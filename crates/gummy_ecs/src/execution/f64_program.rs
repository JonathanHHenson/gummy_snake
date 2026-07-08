use std::collections::HashMap;

mod compiler;
mod ops;
mod readonly;
mod row_local;

pub(super) use compiler::{
    compile_f64_readonly_program, compiled_f64_eval_order, compiled_field_f64_value,
    eval_compiled_f64_linear_order,
};
pub(super) use ops::{eval_binary_f64, eval_unary_f64};
pub(super) use readonly::eval_compiled_f64_readonly;
pub(super) use row_local::{
    build_row_local_field_dependents, execute_row_local_f64_action, invalidate_row_local_f64_cache,
};

#[derive(Debug, Clone)]
pub(super) struct RowLocalTarget {
    pub(super) component: String,
    pub(super) field: String,
}

#[derive(Debug, Clone)]
pub(super) enum RowLocalAction {
    Noop,
    SetField {
        field_slot: usize,
        target_slot: usize,
        value_expr: usize,
    },
    ForEachListField {
        component: String,
        field: String,
        item_slot: usize,
        action: Box<RowLocalAction>,
    },
    EmitConstEvent {
        event_type: String,
        payload: crate::column::EcsValue,
    },
    Sequence(Vec<RowLocalAction>),
    When {
        condition_expr: usize,
        then_action: Box<RowLocalAction>,
        otherwise_action: Option<Box<RowLocalAction>>,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum F64UnaryOp {
    Neg,
    Not,
    Abs,
    Sqrt,
    Sin,
    Cos,
    Floor,
    Ceil,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum F64BinaryOp {
    Add,
    Sub,
    Mul,
    TrueDiv,
    FloorDiv,
    Mod,
    Pow,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
    Min,
    Max,
    And,
    Or,
}

#[derive(Debug, Clone)]
enum CompiledF64Expr {
    Literal(f64),
    Field(usize),
    SpatialAggregate(usize),
    ForEachItem(usize),
    ResourceField {
        resource: String,
        field: String,
    },
    InputState {
        name: String,
        code: Option<i64>,
    },
    Unary {
        op: F64UnaryOp,
        input: usize,
    },
    Binary {
        op: F64BinaryOp,
        left: usize,
        right: usize,
    },
    Passthrough(usize),
    Unsupported(String),
}

pub(super) struct CompiledF64ReadOnlyProgram<'a> {
    expressions: Vec<CompiledF64Expr>,
    pub(super) aliases: Vec<usize>,
    pub(super) initial_values: Vec<(usize, f64)>,
    pub(super) field_arrays: Vec<CompiledF64Array<'a>>,
    pub(super) field_slot_by_key: HashMap<(String, String), usize>,
    spatial_arrays: Vec<CompiledSpatialF64Array<'a>>,
}

#[derive(Clone, Copy)]
pub(super) enum CompiledF64Array<'a> {
    SparseEntity(&'a [Option<(u32, f64)>]),
    QueryRows(&'a [f64]),
}

#[derive(Clone, Copy)]
enum CompiledSpatialF64Array<'a> {
    SparseEntity(&'a [Option<(u32, f64)>]),
    QueryRows(&'a [f64]),
    QueryRowsOptional(&'a [Option<f64>]),
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum CompiledF64ExprKey {
    Literal(u64),
    Field(usize),
    SpatialAggregate(usize),
    ForEachItem(usize),
    ResourceField(String, String),
    InputState(String, Option<i64>),
    Unary(F64UnaryOp, usize),
    Binary(F64BinaryOp, usize, usize),
    Passthrough(usize),
}
