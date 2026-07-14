//! Private canonical names for string-based bridge operations.
//!
//! Bridge DTO strings compile to closed internal domains once per prepared plan.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum UnaryOp {
    Neg,
    Not,
    Abs,
    Sqrt,
    Sin,
    Cos,
    Floor,
    Ceil,
    Unknown,
}

impl UnaryOp {
    pub(crate) fn parse(name: &str) -> Self {
        match name {
            "neg" => Self::Neg,
            "not" => Self::Not,
            "abs" => Self::Abs,
            "sqrt" => Self::Sqrt,
            "sin" => Self::Sin,
            "cos" => Self::Cos,
            "floor" => Self::Floor,
            "ceil" => Self::Ceil,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum BinaryOp {
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
    Unknown,
}

impl BinaryOp {
    pub(crate) fn parse(name: &str) -> Self {
        match name {
            "add" => Self::Add,
            "sub" => Self::Sub,
            "mul" => Self::Mul,
            "truediv" => Self::TrueDiv,
            "floordiv" => Self::FloorDiv,
            "mod" => Self::Mod,
            "pow" => Self::Pow,
            "lt" => Self::Lt,
            "le" => Self::Le,
            "gt" => Self::Gt,
            "ge" => Self::Ge,
            "eq" => Self::Eq,
            "ne" => Self::Ne,
            "min" => Self::Min,
            "max" => Self::Max,
            "and" => Self::And,
            "or" => Self::Or,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum AggregateKind {
    Any,
    Count,
    Sum,
    Min,
    Max,
    Mean,
    Unknown,
}

impl AggregateKind {
    pub(crate) fn parse(name: &str) -> Self {
        match name {
            "any" => Self::Any,
            "count" => Self::Count,
            "sum" => Self::Sum,
            "min" => Self::Min,
            "max" => Self::Max,
            "mean" => Self::Mean,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum PairPolicy {
    All,
    UniqueUnordered,
}

impl PairPolicy {
    pub(crate) fn parse(name: &str) -> Option<Self> {
        match name {
            "all" => Some(Self::All),
            "unique_unordered" => Some(Self::UniqueUnordered),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum SpatialAlgorithmKind {
    HashGrid,
    Quadtree,
    Octree,
    Hilbert,
    Unknown,
}

impl SpatialAlgorithmKind {
    pub(crate) fn parse(name: &str) -> Self {
        match name {
            "hash_grid" => Self::HashGrid,
            "quadtree" => Self::Quadtree,
            "octree" => Self::Octree,
            "hilbert_curve" => Self::Hilbert,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum SpatialMetadataKind {
    Delta,
    Distance,
    DistanceSq,
    Unknown,
}

impl SpatialMetadataKind {
    pub(crate) fn parse(name: &str) -> Self {
        match name {
            "delta" => Self::Delta,
            "distance" => Self::Distance,
            "distance_sq" => Self::DistanceSq,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(crate) enum CanvasCommandKind {
    Rect,
    Ellipse,
    Circle,
    Triangle,
    Line,
    Text,
    Image,
    Other,
}

impl CanvasCommandKind {
    pub(crate) fn parse(name: &str) -> Self {
        match name {
            "rect" => Self::Rect,
            "ellipse" => Self::Ellipse,
            "circle" => Self::Circle,
            "triangle" => Self::Triangle,
            "line" => Self::Line,
            "text" => Self::Text,
            "image" => Self::Image,
            // Canvas commands are intentionally extensible across the bridge.
            // Keep unknown non-empty names executable as before.
            _ => Self::Other,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_operator_names_compile() {
        for (name, expected) in [
            ("neg", UnaryOp::Neg),
            ("not", UnaryOp::Not),
            ("floor", UnaryOp::Floor),
        ] {
            assert_eq!(UnaryOp::parse(name), expected, "{name}");
        }
        for (name, expected) in [
            ("add", BinaryOp::Add),
            ("floordiv", BinaryOp::FloorDiv),
            ("pow", BinaryOp::Pow),
            ("and", BinaryOp::And),
            ("or", BinaryOp::Or),
        ] {
            assert_eq!(BinaryOp::parse(name), expected, "{name}");
        }
        assert_eq!(UnaryOp::parse("invalid"), UnaryOp::Unknown);
        assert_eq!(BinaryOp::parse("invalid"), BinaryOp::Unknown);
    }

    #[test]
    fn canonical_spatial_names_compile() {
        assert_eq!(AggregateKind::parse("mean"), AggregateKind::Mean);
        assert_eq!(AggregateKind::parse("invalid"), AggregateKind::Unknown);
        assert_eq!(PairPolicy::parse("all"), Some(PairPolicy::All));
        assert_eq!(
            PairPolicy::parse("unique_unordered"),
            Some(PairPolicy::UniqueUnordered)
        );
        assert_eq!(PairPolicy::parse("invalid"), None);
        assert_eq!(
            SpatialAlgorithmKind::parse("hilbert_curve"),
            SpatialAlgorithmKind::Hilbert
        );
        assert_eq!(
            SpatialMetadataKind::parse("distance_sq"),
            SpatialMetadataKind::DistanceSq
        );
    }
}
