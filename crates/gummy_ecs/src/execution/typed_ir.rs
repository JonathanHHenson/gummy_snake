//! Executor-private compilation of source-compatible bridge DTOs.
//!
//! `PhysicalPlan` intentionally remains a public, directly constructible DTO.
//! This module owns the closed typed view used by execution; it never changes
//! plan summaries, fingerprints, or wire representation.

use crate::plan::typed_ir::{
    AggregateKind, BinaryOp, CanvasCommandKind, PairPolicy, SpatialAlgorithmKind,
    SpatialMetadataKind, UnaryOp,
};
use crate::plan::{ActionNode, ExprNode, PhysicalPlan, SpatialRelationNode};

#[derive(Debug, Clone, Copy)]
pub(in crate::execution) struct TypedSpatialRelation {
    pub(in crate::execution) algorithm: SpatialAlgorithmKind,
    pub(in crate::execution) pair_policy: PairPolicy,
}

#[derive(Debug, Clone, Copy)]
pub(in crate::execution) enum TypedExpr {
    Other,
    Unary(UnaryOp),
    Binary(BinaryOp),
    Aggregate(AggregateKind),
    SpatialMetadata(TypedSpatialRelation, SpatialMetadataKind),
    SpatialAggregate(TypedSpatialRelation, AggregateKind),
}

#[derive(Debug, Clone)]
pub(in crate::execution) enum TypedAction {
    Other,
    CanvasCommand(CanvasCommandKind),
}

#[derive(Debug, Clone)]
pub(in crate::execution) struct TypedExecutorPlan {
    expressions: Vec<TypedExpr>,
    actions: Vec<TypedAction>,
}

impl TypedExecutorPlan {
    pub(in crate::execution) fn compile(plan: &PhysicalPlan) -> Self {
        Self {
            expressions: plan.expressions.iter().map(TypedExpr::compile).collect(),
            actions: plan.actions.iter().map(TypedAction::compile).collect(),
        }
    }

    pub(in crate::execution) fn expression(&self, index: usize) -> TypedExpr {
        self.expressions[index]
    }

    pub(in crate::execution) fn action(&self, index: usize) -> &TypedAction {
        &self.actions[index]
    }

    pub(in crate::execution) fn spatial_relation(
        &self,
        plan: &PhysicalPlan,
        relation: &SpatialRelationNode,
    ) -> TypedSpatialRelation {
        // Relations are private execution metadata nested in public DTOs. The
        // caller may hold a cloned DTO while evaluating recursively, so use
        // structural identity rather than pointer identity. This lookup occurs
        // at relation setup, never in per-record spatial loops.
        plan.expressions
            .iter()
            .zip(&self.expressions)
            .find_map(|(expr, typed)| match (expr, typed) {
                (
                    ExprNode::SpatialMetadata {
                        relation: candidate,
                        ..
                    },
                    TypedExpr::SpatialMetadata(typed, _),
                )
                | (
                    ExprNode::SpatialAggregate {
                        relation: candidate,
                        ..
                    },
                    TypedExpr::SpatialAggregate(typed, _),
                ) if candidate == relation => Some(*typed),
                _ => None,
            })
            .expect("typed executor plan must contain every spatial relation")
    }
}

impl TypedExpr {
    fn compile(expr: &ExprNode) -> Self {
        match expr {
            ExprNode::Unary { op, .. } => Self::Unary(UnaryOp::parse(op)),
            ExprNode::Binary { op, .. } => Self::Binary(BinaryOp::parse(op)),
            ExprNode::Aggregate { kind, .. } => Self::Aggregate(AggregateKind::parse(kind)),
            ExprNode::SpatialMetadata { relation, kind, .. } => Self::SpatialMetadata(
                TypedSpatialRelation::compile(relation),
                SpatialMetadataKind::parse(kind),
            ),
            ExprNode::SpatialAggregate { relation, kind, .. } => Self::SpatialAggregate(
                TypedSpatialRelation::compile(relation),
                AggregateKind::parse(kind),
            ),
            _ => Self::Other,
        }
    }
}

impl TypedSpatialRelation {
    fn compile(relation: &SpatialRelationNode) -> Self {
        Self {
            algorithm: SpatialAlgorithmKind::parse(&relation.algorithm.kind),
            pair_policy: PairPolicy::parse(&relation.pair_policy),
        }
    }
}

impl TypedAction {
    fn compile(action: &ActionNode) -> Self {
        match action {
            ActionNode::CanvasCommand(command) => {
                Self::CanvasCommand(CanvasCommandKind::parse(&command.command))
            }
            _ => Self::Other,
        }
    }
}
