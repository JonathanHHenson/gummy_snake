use std::fmt;

pub type Result<T> = std::result::Result<T, EcsError>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EcsError {
    StaleEntity {
        index: u32,
        generation: u32,
    },
    DuplicateSchema(String),
    UnknownSchema(String),
    UnknownStorageType(String),
    UnknownField {
        component: String,
        field: String,
    },
    DuplicateComponent(String),
    MissingComponent(String),
    MissingResource(String),
    ColumnTypeMismatch {
        expected: &'static str,
        got: &'static str,
    },
    RowOutOfBounds,
    InvalidEventType,
    InvalidPlan(String),
    InvalidSchedule(String),
    InvalidSpatialInput(String),
    EmptySchemaName,
    EmptyFieldName,
}

impl fmt::Display for EcsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::StaleEntity { index, generation } => {
                write!(f, "stale ECS entity {index}:{generation}")
            }
            Self::DuplicateSchema(name) => write!(f, "duplicate ECS component schema {name}"),
            Self::UnknownSchema(name) => write!(f, "unknown ECS component schema {name}"),
            Self::UnknownStorageType(name) => write!(f, "unknown ECS storage type {name}"),
            Self::UnknownField { component, field } => {
                write!(f, "unknown ECS component field {component}.{field}")
            }
            Self::DuplicateComponent(name) => write!(f, "entity already has ECS component {name}"),
            Self::MissingComponent(name) => write!(f, "entity is missing ECS component {name}"),
            Self::MissingResource(name) => write!(f, "ECS resource {name} is not present"),
            Self::ColumnTypeMismatch { expected, got } => {
                write!(f, "ECS column expected {expected} value, got {got}")
            }
            Self::RowOutOfBounds => write!(f, "ECS row index is out of bounds"),
            Self::InvalidEventType => write!(f, "ECS event type name cannot be empty"),
            Self::InvalidPlan(message) => write!(f, "invalid ECS system plan: {message}"),
            Self::InvalidSchedule(message) => write!(f, "invalid ECS schedule: {message}"),
            Self::InvalidSpatialInput(message) => write!(f, "invalid ECS spatial input: {message}"),
            Self::EmptySchemaName => write!(f, "ECS component schema name cannot be empty"),
            Self::EmptyFieldName => write!(f, "ECS component field name cannot be empty"),
        }
    }
}

impl std::error::Error for EcsError {}
