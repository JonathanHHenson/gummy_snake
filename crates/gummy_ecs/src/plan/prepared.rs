use std::collections::{HashMap, HashSet};
use std::hash::{Hash, Hasher};
use std::sync::Arc;

use crate::error::{EcsError, Result};
use crate::execution::TypedExecutorPlan;
use crate::schema::{ComponentId, FieldId, SchemaRegistry, StorageType};

use super::{ActionNode, ExprNode, PhysicalPlan, SpatialRelationNode};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct QuerySlot(pub usize);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct PreparedFieldRef {
    pub query: Option<QuerySlot>,
    pub component: ComponentId,
    pub field: FieldId,
    pub storage_type: StorageType,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutorEligibility {
    Typed,
    ExplicitPythonBoundary,
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PreparedPlanStats {
    pub estimated_bytes: usize,
    pub query_slots: usize,
    pub field_references: usize,
    pub invariant_expressions: usize,
    pub spatial_descriptors: usize,
}

#[derive(Debug, Clone)]
pub struct PreparedPlan {
    plan: Arc<PhysicalPlan>,
    typed_executor: TypedExecutorPlan,
    query_slots: HashMap<String, QuerySlot>,
    field_references: Vec<Option<PreparedFieldRef>>,
    expression_dependencies: Vec<Vec<usize>>,
    invariant_expressions: Vec<bool>,
    spatial_cache_keys: Vec<String>,
    semantic_hash: u64,
    schema_version: u64,
    executor_eligibility: ExecutorEligibility,
    max_loop_slot: Option<usize>,
    stats: PreparedPlanStats,
}

impl PreparedPlan {
    pub fn compile(plan: PhysicalPlan, schemas: &SchemaRegistry) -> Result<Self> {
        let plan = Arc::new(plan);
        let query_slots = plan
            .queries
            .iter()
            .enumerate()
            .map(|(index, query)| (query.name.clone(), QuerySlot(index)))
            .collect::<HashMap<_, _>>();
        let mut field_references = Vec::with_capacity(plan.expressions.len());
        let mut expression_dependencies = Vec::with_capacity(plan.expressions.len());
        let mut invariant_expressions = Vec::with_capacity(plan.expressions.len());
        let resource_writes = plan
            .actions
            .iter()
            .filter_map(|action| match action {
                ActionNode::SetField { target, .. } => match &plan.expressions[*target] {
                    ExprNode::ResourceField { resource, .. } => Some(resource.as_str()),
                    _ => None,
                },
                _ => None,
            })
            .collect::<HashSet<_>>();

        for (index, expression) in plan.expressions.iter().enumerate() {
            field_references.push(resolve_field_reference(expression, schemas, &query_slots)?);
            let dependencies = expression_dependencies_for(expression);
            let invariant =
                expression_is_invariant(expression, &invariant_expressions, &resource_writes);
            if dependencies.iter().any(|dependency| *dependency >= index) {
                return Err(EcsError::InvalidPlan(format!(
                    "expression {index} depends on an expression that is not prepared before it"
                )));
            }
            expression_dependencies.push(dependencies);
            invariant_expressions.push(invariant);
        }

        let spatial_cache_keys = compiled_plan_spatial_cache_keys(&plan);
        let semantic_hash = semantic_plan_hash(&plan);
        let max_loop_slot = plan
            .actions
            .iter()
            .filter_map(|action| match action {
                ActionNode::ForEach { item_slot, .. } => Some(*item_slot),
                _ => None,
            })
            .max();
        let executor_eligibility = if plan
            .actions
            .iter()
            .any(|action| matches!(action, ActionNode::Udf { .. }))
        {
            ExecutorEligibility::ExplicitPythonBoundary
        } else {
            ExecutorEligibility::Typed
        };
        let typed_executor = TypedExecutorPlan::compile(&plan);
        let stats = PreparedPlanStats {
            estimated_bytes: estimate_prepared_bytes(
                &plan,
                &query_slots,
                &expression_dependencies,
                &spatial_cache_keys,
            ),
            query_slots: query_slots.len(),
            field_references: field_references.iter().flatten().count(),
            invariant_expressions: invariant_expressions.iter().filter(|value| **value).count(),
            spatial_descriptors: spatial_cache_keys.len(),
        };
        Ok(Self {
            plan,
            typed_executor,
            query_slots,
            field_references,
            expression_dependencies,
            invariant_expressions,
            spatial_cache_keys,
            semantic_hash,
            schema_version: schemas.version(),
            executor_eligibility,
            max_loop_slot,
            stats,
        })
    }

    pub fn plan(&self) -> &PhysicalPlan {
        &self.plan
    }

    pub fn plan_arc(&self) -> Arc<PhysicalPlan> {
        Arc::clone(&self.plan)
    }

    pub(crate) fn typed_executor(&self) -> &TypedExecutorPlan {
        &self.typed_executor
    }

    pub fn query_slot(&self, name: &str) -> Option<QuerySlot> {
        self.query_slots.get(name).copied()
    }

    pub fn query_slot_count(&self) -> usize {
        self.query_slots.len()
    }

    pub fn field_reference(&self, expression: usize) -> Option<PreparedFieldRef> {
        self.field_references.get(expression).copied().flatten()
    }

    pub fn expression_dependencies(&self, expression: usize) -> Option<&[usize]> {
        self.expression_dependencies
            .get(expression)
            .map(Vec::as_slice)
    }

    pub fn expression_is_invariant(&self, expression: usize) -> bool {
        self.invariant_expressions
            .get(expression)
            .copied()
            .unwrap_or(false)
    }

    pub fn spatial_cache_keys(&self) -> &[String] {
        &self.spatial_cache_keys
    }

    pub fn semantic_hash(&self) -> u64 {
        self.semantic_hash
    }

    pub fn schema_version(&self) -> u64 {
        self.schema_version
    }

    pub fn executor_eligibility(&self) -> ExecutorEligibility {
        self.executor_eligibility
    }

    pub fn loop_slot_count(&self) -> usize {
        self.max_loop_slot.map_or(0, |slot| slot + 1)
    }

    pub fn stats(&self) -> &PreparedPlanStats {
        &self.stats
    }

    pub fn semantically_equivalent(&self, plan: &PhysicalPlan) -> bool {
        self.plan.as_ref() == plan
    }
}

fn resolve_field_reference(
    expression: &ExprNode,
    schemas: &SchemaRegistry,
    query_slots: &HashMap<String, QuerySlot>,
) -> Result<Option<PreparedFieldRef>> {
    let (query, component, field) = match expression {
        ExprNode::Field {
            query,
            component,
            field,
        } => (Some(query.as_str()), component.as_str(), field.as_str()),
        ExprNode::ResourceField { resource, field } => (None, resource.as_str(), field.as_str()),
        _ => return Ok(None),
    };
    let component_id = schemas
        .component_id(component)
        .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
    let field_id = schemas
        .field_id(component, field)
        .ok_or_else(|| EcsError::UnknownField {
            component: component.to_string(),
            field: field.to_string(),
        })?;
    let storage_type = schemas
        .field_schema(field_id)
        .expect("resolved field ID must remain present in the compatible schema")
        .storage_type;
    let query = query
        .map(|name| {
            query_slots.get(name).copied().ok_or_else(|| {
                EcsError::InvalidPlan(format!("query '{name}' is not part of the prepared plan"))
            })
        })
        .transpose()?;
    Ok(Some(PreparedFieldRef {
        query,
        component: component_id,
        field: field_id,
        storage_type,
    }))
}

fn expression_dependencies_for(expression: &ExprNode) -> Vec<usize> {
    match expression {
        ExprNode::Attribute { input, .. } | ExprNode::Unary { input, .. } => vec![*input],
        ExprNode::Binary { left, right, .. } => vec![*left, *right],
        ExprNode::ContextJoin { predicate, .. } | ExprNode::Exists { predicate, .. } => {
            vec![*predicate]
        }
        ExprNode::Aggregate {
            relation,
            value,
            default,
            ..
        } => optional_dependencies(*relation, *value, *default),
        ExprNode::SpatialMetadata { relation, .. } => spatial_relation_dependencies(relation),
        ExprNode::SpatialAggregate {
            relation,
            value,
            default,
            ..
        } => {
            let mut dependencies = spatial_relation_dependencies(relation);
            dependencies.extend(value.iter().copied());
            dependencies.extend(default.iter().copied());
            dependencies.sort_unstable();
            dependencies.dedup();
            dependencies
        }
        ExprNode::LiteralF64(_)
        | ExprNode::LiteralI64(_)
        | ExprNode::LiteralBool(_)
        | ExprNode::LiteralString(_)
        | ExprNode::LiteralValue(_)
        | ExprNode::Field { .. }
        | ExprNode::ResourceField { .. }
        | ExprNode::EventStream { .. }
        | ExprNode::InputState { .. }
        | ExprNode::ForEachItem { .. } => Vec::new(),
    }
}

fn optional_dependencies(root: usize, value: Option<usize>, default: Option<usize>) -> Vec<usize> {
    let mut dependencies = vec![root];
    dependencies.extend(value);
    dependencies.extend(default);
    dependencies.sort_unstable();
    dependencies.dedup();
    dependencies
}

fn spatial_relation_dependencies(relation: &SpatialRelationNode) -> Vec<usize> {
    let mut dependencies = relation
        .origin_position
        .iter()
        .chain(&relation.target_position)
        .copied()
        .collect::<Vec<_>>();
    dependencies.extend(relation.radius);
    for bounds in relation
        .origin_bounds
        .iter()
        .chain(relation.target_bounds.iter())
    {
        dependencies.extend(bounds.minimum.iter().copied());
        dependencies.extend(bounds.maximum.iter().copied());
    }
    dependencies.extend(relation.exact_filter);
    dependencies.sort_unstable();
    dependencies.dedup();
    dependencies
}

fn expression_is_invariant(
    expression: &ExprNode,
    prepared_invariants: &[bool],
    resource_writes: &HashSet<&str>,
) -> bool {
    match expression {
        ExprNode::LiteralF64(_)
        | ExprNode::LiteralI64(_)
        | ExprNode::LiteralBool(_)
        | ExprNode::LiteralString(_)
        | ExprNode::LiteralValue(_) => true,
        ExprNode::ResourceField { resource, .. } => !resource_writes.contains(resource.as_str()),
        ExprNode::Unary { input, .. } | ExprNode::Attribute { input, .. } => {
            prepared_invariants.get(*input).copied().unwrap_or(false)
        }
        ExprNode::Binary { left, right, .. } => {
            prepared_invariants.get(*left).copied().unwrap_or(false)
                && prepared_invariants.get(*right).copied().unwrap_or(false)
        }
        ExprNode::Field { .. }
        | ExprNode::EventStream { .. }
        | ExprNode::InputState { .. }
        | ExprNode::ForEachItem { .. }
        | ExprNode::ContextJoin { .. }
        | ExprNode::Exists { .. }
        | ExprNode::Aggregate { .. }
        | ExprNode::SpatialMetadata { .. }
        | ExprNode::SpatialAggregate { .. } => false,
    }
}

fn compiled_plan_spatial_cache_keys(plan: &PhysicalPlan) -> Vec<String> {
    let mut keys = plan
        .expressions
        .iter()
        .filter_map(|expression| match expression {
            ExprNode::SpatialMetadata { relation, .. }
            | ExprNode::SpatialAggregate { relation, .. } => {
                Some(spatial_index_cache_key(plan, relation))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    keys.sort();
    keys.dedup();
    keys
}

fn spatial_index_cache_key(plan: &PhysicalPlan, relation: &SpatialRelationNode) -> String {
    format!(
        "{}|item={};target_pos={:?};target_bounds={:?};algorithm={:?};item_query_fingerprint={}",
        relation.index_id,
        relation.item_query,
        relation.target_position,
        relation.target_bounds,
        relation.algorithm,
        query_fingerprint(plan, &relation.item_query),
    )
}

fn query_fingerprint(plan: &PhysicalPlan, query_name: &str) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    query_name.hash(&mut hasher);
    if let Some(query) = plan.queries.iter().find(|query| query.name == query_name) {
        query.filter.hash(&mut hasher);
    }
    hasher.finish()
}

fn semantic_plan_hash(plan: &PhysicalPlan) -> u64 {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    format!("{plan:?}").hash(&mut hasher);
    hasher.finish()
}

fn estimate_prepared_bytes(
    plan: &PhysicalPlan,
    query_slots: &HashMap<String, QuerySlot>,
    dependencies: &[Vec<usize>],
    spatial_keys: &[String],
) -> usize {
    std::mem::size_of::<PreparedPlan>()
        + std::mem::size_of_val(plan.queries.as_slice())
        + std::mem::size_of_val(plan.expressions.as_slice())
        + std::mem::size_of_val(plan.actions.as_slice())
        + query_slots.keys().map(String::len).sum::<usize>()
        + dependencies
            .iter()
            .map(|items| items.capacity() * std::mem::size_of::<usize>())
            .sum::<usize>()
        + spatial_keys.iter().map(String::len).sum::<usize>()
}
