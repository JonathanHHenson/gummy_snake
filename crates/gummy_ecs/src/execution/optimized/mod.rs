//! Specialized numeric and parallel physical execution paths.

use super::spatial::support::SpatialF64RowArray;
use super::{bool_f64, default_input_state_value, numeric_f64, truthy_f64};

pub(super) mod direct_f64_actions;
pub(super) mod f64_program;
pub(super) mod parallel_actions;
