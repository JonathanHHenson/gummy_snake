//! Row-local fast paths for numeric actions and canvas command collection.
//!
//! Eligibility analysis, action compilation, generic canvas collection, compact
//! fill batching, and numeric execution are kept separate while sharing the
//! executor state and preserving dispatch behavior.

mod analysis;
mod canvas;
mod compact_fill;
mod compiler;
mod numeric;
