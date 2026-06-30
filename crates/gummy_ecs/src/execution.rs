use std::collections::{BTreeSet, HashMap, HashSet};

use crate::column::EcsValue;
use crate::entity::Entity;
use crate::error::{EcsError, Result};
use crate::hilbert::HilbertIndex;
use crate::plan::{
    ActionNode, BridgePlanPayload, ExprNode, PhysicalPlan, PhysicalPlanHandle,
    SpatialBoundsExprNode, SpatialRelationNode,
};
use crate::schema::StorageType;
use crate::spatial::{
    Dimensions, HashGridIndex, SpatialAabb, SpatialIndexBackend, SpatialPoint, SpatialRecord,
};
use crate::tree_spatial::{OctreeIndex, QuadtreeIndex};
use crate::world::World;

#[derive(Debug, Clone, PartialEq)]
pub enum ExecutionWrite {
    ComponentField {
        entity: Entity,
        component: String,
        field: String,
        value: EcsValue,
    },
    ResourceField {
        resource: String,
        field: String,
        value: EcsValue,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionEvent {
    pub event_type: String,
    pub payload: EcsValue,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ExecutionReport {
    pub rows_scanned: usize,
    pub fields_written: usize,
    pub resource_fields_written: usize,
    pub events_emitted: usize,
    pub duplicate_writes: usize,
    pub spatial_indexes_built: usize,
    pub spatial_candidate_rows: usize,
    pub spatial_exact_rows: usize,
    pub spatial_false_positive_rows: usize,
    pub spatial_deduplicated_pairs: usize,
    pub spatial_algorithm_hash_grid: usize,
    pub spatial_algorithm_quadtree: usize,
    pub spatial_algorithm_octree: usize,
    pub spatial_algorithm_hilbert_curve: usize,
    pub writes: Vec<ExecutionWrite>,
    pub events: Vec<ExecutionEvent>,
}

#[derive(Debug, Clone, Default)]
struct EvalContext {
    bindings: HashMap<String, Entity>,
    loop_items: HashMap<usize, EcsValue>,
}

impl EvalContext {
    fn with_binding(&self, query: String, entity: Entity) -> Self {
        let mut next = self.clone();
        next.bindings.insert(query, entity);
        next
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum WriteKey {
    Component {
        entity: Entity,
        component: String,
        field: String,
    },
    Resource {
        resource: String,
        field: String,
    },
}

#[derive(Debug, Clone)]
enum BuiltSpatialIndex {
    HashGrid(HashGridIndex),
    Quadtree(QuadtreeIndex),
    Octree(OctreeIndex),
    Hilbert(HilbertIndex),
}

impl BuiltSpatialIndex {
    fn query_radius(
        &self,
        origin: &SpatialPoint,
        radius: f64,
        out: &mut Vec<SpatialRecord>,
    ) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.query_radius(origin, radius, out),
            Self::Quadtree(index) => index.query_radius(origin, radius, out),
            Self::Octree(index) => index.query_radius(origin, radius, out),
            Self::Hilbert(index) => index.query_radius(origin, radius, out),
        }
    }

    fn query_aabb(&self, bounds: &SpatialAabb, out: &mut Vec<SpatialRecord>) -> Result<()> {
        match self {
            Self::HashGrid(index) => index.query_aabb(bounds, out),
            Self::Quadtree(index) => index.query_aabb(bounds, out),
            Self::Octree(index) => index.query_aabb(bounds, out),
            Self::Hilbert(index) => index.query_aabb(bounds, out),
        }
    }
}

struct PlanExecutor<'a> {
    world: &'a mut World,
    plan: &'a PhysicalPlan,
    query_rows: HashMap<String, Vec<Entity>>,
    report: ExecutionReport,
    spatial_indexes: HashMap<String, BuiltSpatialIndex>,
    spatial_relation_cache:
        HashMap<(String, Option<usize>, Option<usize>, bool, String, u64), Vec<SpatialRecord>>,
    expr_cache: HashMap<(usize, Vec<(String, u64)>), EcsValue>,
}

impl World {
    pub fn execute_bridge_plan(&mut self, payload: BridgePlanPayload) -> Result<ExecutionReport> {
        let plan = self.compile_bridge_plan(payload)?;
        self.execute_plan(&plan)
    }

    pub fn execute_compiled_plan(&mut self, handle: PhysicalPlanHandle) -> Result<ExecutionReport> {
        let plan = self.compiled_plan(handle).ok_or_else(|| {
            EcsError::InvalidPlan(format!("unknown compiled ECS plan handle {handle}"))
        })?;
        let current_schema_fingerprint = self.schema_fingerprint();
        if plan.schema_fingerprint != current_schema_fingerprint {
            return Err(EcsError::InvalidPlan(format!(
                "compiled ECS plan handle {handle} was built for schema fingerprint {}, \
                 but the world schema fingerprint is {}; recompile the plan",
                plan.schema_fingerprint, current_schema_fingerprint
            )));
        }
        self.execute_plan(plan.as_ref())
    }

    pub fn execute_plan(&mut self, plan: &PhysicalPlan) -> Result<ExecutionReport> {
        let mut query_rows = HashMap::new();
        for query in &plan.queries {
            let mut rows = self.query_filter(query.filter.clone())?;
            if let Some(allowed) = &query.allowed_entities {
                let allowed = allowed
                    .iter()
                    .map(|entity| entity.raw())
                    .collect::<HashSet<_>>();
                rows.retain(|entity| allowed.contains(&entity.raw()));
            }
            query_rows.insert(query.name.clone(), rows);
        }
        let mut executor = PlanExecutor {
            world: self,
            plan,
            query_rows,
            report: ExecutionReport::default(),
            spatial_indexes: HashMap::new(),
            spatial_relation_cache: HashMap::new(),
            expr_cache: HashMap::new(),
        };
        executor.execute_action(plan.root_action, &[EvalContext::default()])?;
        Ok(executor.report)
    }

    pub fn storage_type_for_field(&self, component: &str, field: &str) -> Result<StorageType> {
        let schema = self
            .schema(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        schema
            .fields
            .iter()
            .find(|candidate| candidate.name == field)
            .map(|candidate| candidate.storage_type)
            .ok_or_else(|| EcsError::UnknownField {
                component: component.to_string(),
                field: field.to_string(),
            })
    }

    pub fn coerce_value_for_component_field(
        &self,
        component: &str,
        field: &str,
        value: EcsValue,
    ) -> Result<EcsValue> {
        let storage_type = self.storage_type_for_field(component, field)?;
        coerce_value_for_storage(storage_type, value)
    }

    pub fn coerce_component_row(
        &self,
        component: &str,
        row: HashMap<String, EcsValue>,
    ) -> Result<HashMap<String, EcsValue>> {
        let schema = self
            .schema(component)
            .ok_or_else(|| EcsError::UnknownSchema(component.to_string()))?;
        let mut coerced = HashMap::with_capacity(row.len());
        for field in &schema.fields {
            let value = row
                .get(&field.name)
                .cloned()
                .ok_or_else(|| EcsError::UnknownField {
                    component: component.to_string(),
                    field: field.name.clone(),
                })?;
            coerced.insert(
                field.name.clone(),
                coerce_value_for_storage(field.storage_type, value)?,
            );
        }
        for field in row.keys() {
            if !schema
                .fields
                .iter()
                .any(|candidate| &candidate.name == field)
            {
                return Err(EcsError::UnknownField {
                    component: component.to_string(),
                    field: field.clone(),
                });
            }
        }
        Ok(coerced)
    }
}

impl<'a> PlanExecutor<'a> {
    fn execute_action(&mut self, action_index: usize, contexts: &[EvalContext]) -> Result<()> {
        match &self.plan.actions[action_index] {
            ActionNode::Noop => Ok(()),
            ActionNode::Sequence(children) => {
                for child in children {
                    self.expr_cache.clear();
                    self.spatial_indexes.clear();
                    self.spatial_relation_cache.clear();
                    self.execute_action(*child, contexts)?;
                }
                Ok(())
            }
            ActionNode::Parallel(children) => self.execute_parallel(children, contexts),
            ActionNode::SetField { target, value } => self.execute_set(*target, *value, contexts),
            ActionNode::When {
                condition,
                then_action,
                otherwise_action,
            } => self.execute_when(*condition, *then_action, *otherwise_action, contexts),
            ActionNode::ForEach {
                source,
                item_slot,
                action,
            } => self.execute_for_each(*source, *item_slot, *action, contexts),
            ActionNode::EmitEvent { event_type, value } => {
                for ctx in contexts {
                    let payload = self.eval_expr(*value, ctx)?;
                    self.world.emit_event(event_type, payload.clone())?;
                    self.report.events_emitted += 1;
                    self.report.events.push(ExecutionEvent {
                        event_type: event_type.clone(),
                        payload,
                    });
                }
                Ok(())
            }
            ActionNode::Udf { descriptor, .. } => Err(EcsError::InvalidPlan(format!(
                "physical execution cannot call Python UDF '{descriptor}'"
            ))),
        }
    }

    fn execute_for_each(
        &mut self,
        source: usize,
        item_slot: usize,
        action: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        for ctx in contexts {
            let value = self.eval_expr(source, ctx)?;
            let items = match value {
                EcsValue::List(values) => values,
                other => {
                    return Err(EcsError::InvalidPlan(format!(
                        "for_each source must evaluate to a list, got {}",
                        other.kind_name()
                    )))
                }
            };
            for item in items {
                let mut loop_ctx = ctx.clone();
                loop_ctx.loop_items.insert(item_slot, item);
                self.execute_action(action, &[loop_ctx])?;
            }
        }
        Ok(())
    }

    fn execute_parallel(&mut self, children: &[usize], contexts: &[EvalContext]) -> Result<()> {
        let snapshot = self.world.clone();
        let mut targets_seen = HashSet::new();
        let mut shared_spatial_indexes = HashMap::new();
        let mut shared_spatial_relation_cache = HashMap::new();
        let mut shared_expr_cache = HashMap::new();
        for child in children {
            let share_expr_cache_after_child = matches!(
                self.plan.actions[*child],
                ActionNode::SetField { .. } | ActionNode::When { .. }
            );
            let mut child_world = snapshot.clone();
            let mut child_executor = PlanExecutor {
                world: &mut child_world,
                plan: self.plan,
                query_rows: self.query_rows.clone(),
                report: ExecutionReport::default(),
                spatial_indexes: shared_spatial_indexes,
                spatial_relation_cache: shared_spatial_relation_cache,
                expr_cache: shared_expr_cache,
            };
            child_executor.execute_action(*child, contexts)?;
            shared_spatial_indexes = child_executor.spatial_indexes;
            shared_spatial_relation_cache = child_executor.spatial_relation_cache;
            shared_expr_cache = if share_expr_cache_after_child {
                child_executor.expr_cache
            } else {
                HashMap::new()
            };
            self.merge_parallel_report(child_executor.report, &mut targets_seen)?;
        }
        Ok(())
    }

    fn merge_parallel_report(
        &mut self,
        child_report: ExecutionReport,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        self.report.rows_scanned += child_report.rows_scanned;
        self.report.events_emitted += child_report.events_emitted;
        self.report.duplicate_writes += child_report.duplicate_writes;
        self.report.spatial_indexes_built += child_report.spatial_indexes_built;
        self.report.spatial_candidate_rows += child_report.spatial_candidate_rows;
        self.report.spatial_exact_rows += child_report.spatial_exact_rows;
        self.report.spatial_false_positive_rows += child_report.spatial_false_positive_rows;
        self.report.spatial_deduplicated_pairs += child_report.spatial_deduplicated_pairs;
        self.report.spatial_algorithm_hash_grid += child_report.spatial_algorithm_hash_grid;
        self.report.spatial_algorithm_quadtree += child_report.spatial_algorithm_quadtree;
        self.report.spatial_algorithm_octree += child_report.spatial_algorithm_octree;
        self.report.spatial_algorithm_hilbert_curve += child_report.spatial_algorithm_hilbert_curve;
        self.report.events.extend(child_report.events);
        for write in child_report.writes {
            match &write {
                ExecutionWrite::ComponentField {
                    entity,
                    component,
                    field,
                    value,
                } => {
                    let key = WriteKey::Component {
                        entity: *entity,
                        component: component.clone(),
                        field: field.clone(),
                    };
                    if !targets_seen.insert(key) {
                        self.report.duplicate_writes += 1;
                    }
                    self.world
                        .set_field(*entity, component, field, value.clone())?;
                    self.report.fields_written += 1;
                }
                ExecutionWrite::ResourceField {
                    resource,
                    field,
                    value,
                } => {
                    let key = WriteKey::Resource {
                        resource: resource.clone(),
                        field: field.clone(),
                    };
                    if !targets_seen.insert(key) {
                        self.report.duplicate_writes += 1;
                    }
                    self.world
                        .set_resource_field(resource, field, value.clone())?;
                    self.report.resource_fields_written += 1;
                }
            }
            self.report.writes.push(write);
        }
        Ok(())
    }

    fn execute_set(
        &mut self,
        target_index: usize,
        value_index: usize,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(value_index, &mut query_names)?;
        match &self.plan.expressions[target_index] {
            ExprNode::Field { query, .. } => {
                query_names.insert(query.clone());
            }
            ExprNode::ResourceField { .. } => {}
            other => {
                return Err(EcsError::InvalidPlan(format!(
                    "set target must be a field or resource field, got {other:?}"
                )))
            }
        }

        let mut targets_seen = HashSet::new();
        for base_ctx in contexts {
            let joined = self.expand_context_for_queries(base_ctx, &query_names)?;
            self.report.rows_scanned += joined.len();
            for ctx in joined {
                let value = self.eval_expr(value_index, &ctx)?;
                self.write_target(target_index, value, &ctx, &mut targets_seen)?;
            }
        }
        Ok(())
    }

    fn execute_when(
        &mut self,
        condition_index: usize,
        then_action: usize,
        otherwise_action: Option<usize>,
        contexts: &[EvalContext],
    ) -> Result<()> {
        let mut condition_queries = BTreeSet::new();
        self.collect_expr_queries(condition_index, &mut condition_queries)?;
        let mut matched = Vec::new();
        let mut remaining = Vec::new();
        for base_ctx in contexts {
            let expanded = self.expand_context_for_queries(base_ctx, &condition_queries)?;
            self.report.rows_scanned += expanded.len();
            let mut branch_matches = Vec::new();
            for ctx in expanded {
                if truthy(&self.eval_expr(condition_index, &ctx)?)? {
                    branch_matches.push(ctx);
                }
            }
            if branch_matches.is_empty() {
                remaining.push(base_ctx.clone());
            } else {
                matched.extend(branch_matches);
            }
        }
        if !matched.is_empty() {
            self.execute_action(then_action, &matched)?;
        }
        if let Some(otherwise_action) = otherwise_action {
            if !remaining.is_empty() {
                self.execute_action(otherwise_action, &remaining)?;
            }
        }
        Ok(())
    }

    fn write_target(
        &mut self,
        target_index: usize,
        value: EcsValue,
        ctx: &EvalContext,
        targets_seen: &mut HashSet<WriteKey>,
    ) -> Result<()> {
        match &self.plan.expressions[target_index] {
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = *ctx.bindings.get(query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound for set target"))
                })?;
                let value = self
                    .world
                    .coerce_value_for_component_field(component, field, value)?;
                let key = WriteKey::Component {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_field(entity, component, field, value.clone())?;
                self.report.fields_written += 1;
                self.report.writes.push(ExecutionWrite::ComponentField {
                    entity,
                    component: component.clone(),
                    field: field.clone(),
                    value,
                });
                Ok(())
            }
            ExprNode::ResourceField { resource, field } => {
                let value = self
                    .world
                    .coerce_value_for_component_field(resource, field, value)?;
                let key = WriteKey::Resource {
                    resource: resource.clone(),
                    field: field.clone(),
                };
                if !targets_seen.insert(key) {
                    self.report.duplicate_writes += 1;
                }
                self.world
                    .set_resource_field(resource, field, value.clone())?;
                self.report.resource_fields_written += 1;
                self.report.writes.push(ExecutionWrite::ResourceField {
                    resource: resource.clone(),
                    field: field.clone(),
                    value,
                });
                Ok(())
            }
            other => Err(EcsError::InvalidPlan(format!(
                "set target must be a field or resource field, got {other:?}"
            ))),
        }
    }

    fn expand_context_for_queries(
        &self,
        base_ctx: &EvalContext,
        query_names: &BTreeSet<String>,
    ) -> Result<Vec<EvalContext>> {
        let missing = query_names
            .iter()
            .filter(|name| !base_ctx.bindings.contains_key(*name))
            .cloned()
            .collect::<Vec<_>>();
        if missing.is_empty() {
            return Ok(vec![base_ctx.clone()]);
        }
        let mut out = Vec::new();
        self.expand_query_recursive(base_ctx, &missing, 0, &mut out)?;
        Ok(out)
    }

    fn expand_query_recursive(
        &self,
        ctx: &EvalContext,
        missing: &[String],
        index: usize,
        out: &mut Vec<EvalContext>,
    ) -> Result<()> {
        if index == missing.len() {
            out.push(ctx.clone());
            return Ok(());
        }
        let query_name = &missing[index];
        let rows = self.query_rows.get(query_name).ok_or_else(|| {
            EcsError::InvalidPlan(format!("query '{query_name}' is not part of the plan"))
        })?;
        for entity in rows {
            let next = ctx.with_binding(query_name.clone(), *entity);
            self.expand_query_recursive(&next, missing, index + 1, out)?;
        }
        Ok(())
    }

    fn eval_expr(&mut self, expr_index: usize, ctx: &EvalContext) -> Result<EcsValue> {
        let cache_key = self.expr_cache_key(expr_index, ctx);
        if let Some(key) = &cache_key {
            if let Some(value) = self.expr_cache.get(key) {
                return Ok(value.clone());
            }
        }
        let expr = self.plan.expressions[expr_index].clone();
        let result = match expr {
            ExprNode::LiteralF64(value) => Ok(EcsValue::F64(value)),
            ExprNode::LiteralI64(value) => Ok(EcsValue::I64(value)),
            ExprNode::LiteralBool(value) => Ok(EcsValue::Bool(value)),
            ExprNode::LiteralString(value) => Ok(EcsValue::String(value)),
            ExprNode::LiteralValue(value) => Ok(value),
            ExprNode::Field {
                query,
                component,
                field,
            } => {
                let entity = ctx.bindings.get(&query).ok_or_else(|| {
                    EcsError::InvalidPlan(format!("query '{query}' is not bound"))
                })?;
                self.world.get_field(*entity, &component, &field)
            }
            ExprNode::ResourceField { resource, field } => {
                self.world.resource_field(&resource, &field)
            }
            ExprNode::Attribute { input, attribute } => {
                let value = self.eval_expr(input, ctx)?;
                match value {
                    EcsValue::Struct(fields) => fields.get(&attribute).cloned().ok_or_else(|| {
                        EcsError::InvalidPlan(format!(
                            "struct value has no attribute '{attribute}'"
                        ))
                    }),
                    other => Err(EcsError::InvalidPlan(format!(
                        "attribute access expects a struct value, got {}",
                        other.kind_name()
                    ))),
                }
            }
            ExprNode::EventStream { event_type } => Ok(EcsValue::List(
                self.world
                    .read_events(&event_type)?
                    .into_iter()
                    .map(|event| event.payload)
                    .collect(),
            )),
            ExprNode::ForEachItem { slot } => ctx.loop_items.get(&slot).cloned().ok_or_else(|| {
                EcsError::InvalidPlan(format!("for_each item slot {slot} is not bound"))
            }),
            ExprNode::Unary { op, input } => {
                let input = self.eval_expr(input, ctx)?;
                eval_unary(&op, input)
            }
            ExprNode::Binary { op, left, right } => {
                if matches!(op.as_str(), "and" | "&&") {
                    let left = self.eval_expr(left, ctx)?;
                    if !truthy(&left)? {
                        return Ok(EcsValue::Bool(false));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                if matches!(op.as_str(), "or" | "||") {
                    let left = self.eval_expr(left, ctx)?;
                    if truthy(&left)? {
                        return Ok(EcsValue::Bool(true));
                    }
                    let right = self.eval_expr(right, ctx)?;
                    return Ok(EcsValue::Bool(truthy(&right)?));
                }
                let left = self.eval_expr(left, ctx)?;
                let right = self.eval_expr(right, ctx)?;
                eval_binary(&op, left, right)
            }
            ExprNode::InputState { name, code } => Ok(self
                .world
                .input_state(&name, code)
                .unwrap_or_else(|| default_input_state_value(&name))),
            ExprNode::ContextJoin { predicate, .. } => self.eval_expr(predicate, ctx),
            ExprNode::Exists { query, predicate } => self.eval_exists(&query, predicate, ctx),
            ExprNode::Aggregate {
                kind,
                relation,
                group_query,
                value,
                default,
            } => self.eval_grouped_aggregate(
                &kind,
                relation,
                group_query.as_deref(),
                value,
                default,
                ctx,
            ),
            ExprNode::SpatialMetadata {
                relation,
                kind,
                axis,
            } => self.eval_spatial_metadata(&relation, &kind, axis, ctx),
            ExprNode::SpatialAggregate {
                kind,
                relation,
                value,
                default,
            } => self.eval_spatial_aggregate(&kind, &relation, value, default, ctx),
        };
        if let (Some(key), Ok(value)) = (cache_key, &result) {
            self.expr_cache.insert(key, value.clone());
        }
        result
    }

    fn expr_cache_key(
        &self,
        expr_index: usize,
        ctx: &EvalContext,
    ) -> Option<(usize, Vec<(String, u64)>)> {
        if !ctx.loop_items.is_empty() {
            return None;
        }
        let mut bindings = ctx
            .bindings
            .iter()
            .map(|(query, entity)| (query.clone(), entity.raw()))
            .collect::<Vec<_>>();
        bindings.sort_by(|left, right| left.0.cmp(&right.0));
        Some((expr_index, bindings))
    }

    fn eval_exists(
        &mut self,
        query: &str,
        predicate: usize,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let mut query_names = BTreeSet::new();
        query_names.insert(query.to_string());
        self.collect_expr_queries(predicate, &mut query_names)?;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            self.report.rows_scanned += 1;
            if truthy(&self.eval_expr(predicate, &joined)?)? {
                return Ok(EcsValue::Bool(true));
            }
        }
        Ok(EcsValue::Bool(false))
    }

    fn eval_grouped_aggregate(
        &mut self,
        kind: &str,
        relation: usize,
        group_query: Option<&str>,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let Some(group_query) = group_query else {
            return Err(EcsError::InvalidPlan(
                "aggregate expressions need a group query".to_string(),
            ));
        };
        let Some(target_entity) = ctx.bindings.get(group_query).copied() else {
            return aggregate_empty(kind, default, self, ctx);
        };
        let mut query_names = BTreeSet::new();
        self.collect_expr_queries(relation, &mut query_names)?;
        if let Some(value) = value {
            self.collect_expr_queries(value, &mut query_names)?;
        }
        let mut values = Vec::new();
        let mut count = 0usize;
        for joined in self.expand_context_for_queries(ctx, &query_names)? {
            if joined.bindings.get(group_query).copied() != Some(target_entity) {
                continue;
            }
            self.report.rows_scanned += 1;
            if !truthy(&self.eval_expr(relation, &joined)?)? {
                continue;
            }
            count += 1;
            if kind == "any" {
                return Ok(EcsValue::Bool(true));
            }
            if let Some(value_expr) = value {
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
    }

    fn eval_spatial_metadata(
        &mut self,
        relation: &SpatialRelationNode,
        kind: &str,
        axis: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let origin = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let item = self.eval_spatial_point(&relation.target_position, ctx)?;
        let mut delta = [0.0_f64; 3];
        for (axis, slot) in delta
            .iter_mut()
            .enumerate()
            .take(dimensions_len(relation.algorithm.dimensions)?)
        {
            *slot = item.coord(axis) - origin.coord(axis);
        }
        if kind == "delta" {
            let axis = axis.ok_or_else(|| {
                EcsError::InvalidPlan("spatial delta metadata requires an axis".to_string())
            })?;
            return Ok(EcsValue::F64(delta[axis]));
        }
        let distance_sq = delta.iter().map(|value| value * value).sum::<f64>();
        match kind {
            "distance_sq" => Ok(EcsValue::F64(distance_sq)),
            "distance" => Ok(EcsValue::F64(distance_sq.sqrt())),
            other => Err(EcsError::InvalidPlan(format!(
                "unsupported spatial metadata kind '{other}'"
            ))),
        }
    }

    fn eval_spatial_aggregate(
        &mut self,
        kind: &str,
        relation: &SpatialRelationNode,
        value: Option<usize>,
        default: Option<usize>,
        ctx: &EvalContext,
    ) -> Result<EcsValue> {
        let records = self.spatial_relation_records(relation, ctx)?;
        let count = records.len();
        if kind == "any" {
            return Ok(EcsValue::Bool(count > 0));
        }
        let mut values = Vec::new();
        if let Some(value_expr) = value {
            values.reserve(records.len());
            for record in records {
                let mut joined = ctx.clone();
                joined
                    .bindings
                    .insert(relation.item_query.clone(), record.entity);
                values.push(self.eval_expr(value_expr, &joined)?);
            }
        }
        aggregate_finish(kind, count, values, default, self, ctx)
    }

    fn spatial_relation_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Vec<SpatialRecord>> {
        let origin_entity = ctx
            .bindings
            .get(&relation.origin_query)
            .copied()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial origin query '{}' is not bound",
                    relation.origin_query
                ))
            })?;
        let cache_key = (
            relation.id.clone(),
            relation.radius,
            relation.exact_filter,
            relation.include_self,
            relation.pair_policy.clone(),
            origin_entity.raw(),
        );
        if let Some(records) = self.spatial_relation_cache.get(&cache_key) {
            return Ok(records.clone());
        }

        let origin_point = self.eval_spatial_point(&relation.origin_position, ctx)?;
        let origin_bounds = relation
            .origin_bounds
            .as_ref()
            .map(|bounds| self.eval_spatial_bounds(bounds, ctx))
            .transpose()?;
        let radius = relation
            .radius
            .map(|expr| {
                self.eval_expr(expr, ctx)
                    .and_then(|value| numeric_f64(&value))
            })
            .transpose()?;
        let mut candidates = Vec::new();
        let index = self.ensure_spatial_index(relation, ctx)?;
        if let Some(bounds) = &origin_bounds {
            index.query_aabb(bounds, &mut candidates)?;
        } else if let Some(radius) = radius {
            index.query_radius(&origin_point, radius, &mut candidates)?;
        } else {
            let bounds = point_bounds(&origin_point)?;
            index.query_aabb(&bounds, &mut candidates)?;
        }
        self.report.spatial_candidate_rows += candidates.len();
        let mut records = Vec::new();
        for record in candidates {
            if !relation.include_self && record.entity == origin_entity {
                continue;
            }
            if relation.pair_policy == "unique_unordered"
                && record.entity.raw() <= origin_entity.raw()
            {
                self.report.spatial_deduplicated_pairs += 1;
                continue;
            }
            if let Some(radius) = radius {
                if origin_point.distance_squared(&record.point)? > radius * radius {
                    self.report.spatial_false_positive_rows += 1;
                    continue;
                }
            }
            if let Some(bounds) = &origin_bounds {
                let record_bounds = record
                    .bounds
                    .clone()
                    .unwrap_or_else(|| point_bounds(&record.point).expect("point bounds"));
                if !bounds.overlaps(&record_bounds)? {
                    self.report.spatial_false_positive_rows += 1;
                    continue;
                }
            }
            let mut joined = ctx.clone();
            joined
                .bindings
                .insert(relation.item_query.clone(), record.entity);
            if let Some(exact_filter) = relation.exact_filter {
                if !truthy(&self.eval_expr(exact_filter, &joined)?)? {
                    continue;
                }
            }
            self.report.rows_scanned += 1;
            self.report.spatial_exact_rows += 1;
            records.push(record);
        }
        self.spatial_relation_cache
            .insert(cache_key, records.clone());
        Ok(records)
    }

    fn ensure_spatial_index(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<&BuiltSpatialIndex> {
        if !self.spatial_indexes.contains_key(&relation.index_id) {
            let records = self.build_spatial_records(relation, ctx)?;
            let mut index = build_spatial_index(&relation.algorithm)?;
            match &mut index {
                BuiltSpatialIndex::HashGrid(index) => {
                    self.report.spatial_algorithm_hash_grid += 1;
                    index.build(&records)?;
                }
                BuiltSpatialIndex::Quadtree(index) => {
                    self.report.spatial_algorithm_quadtree += 1;
                    index.build(&records)?;
                }
                BuiltSpatialIndex::Octree(index) => {
                    self.report.spatial_algorithm_octree += 1;
                    index.build(&records)?;
                }
                BuiltSpatialIndex::Hilbert(index) => {
                    self.report.spatial_algorithm_hilbert_curve += 1;
                    index.build(&records)?;
                }
            }
            self.report.spatial_indexes_built += 1;
            self.spatial_indexes
                .insert(relation.index_id.clone(), index);
        }
        self.spatial_indexes.get(&relation.index_id).ok_or_else(|| {
            EcsError::InvalidPlan(format!(
                "spatial index '{}' was not built",
                relation.index_id
            ))
        })
    }

    fn build_spatial_records(
        &mut self,
        relation: &SpatialRelationNode,
        ctx: &EvalContext,
    ) -> Result<Vec<SpatialRecord>> {
        let rows = self
            .query_rows
            .get(&relation.item_query)
            .cloned()
            .ok_or_else(|| {
                EcsError::InvalidPlan(format!(
                    "spatial item query '{}' is not part of the plan",
                    relation.item_query
                ))
            })?;
        let mut records = Vec::with_capacity(rows.len());
        for entity in rows {
            let mut item_ctx = ctx.clone();
            item_ctx
                .bindings
                .insert(relation.item_query.clone(), entity);
            let point = self.eval_spatial_point(&relation.target_position, &item_ctx)?;
            let bounds = relation
                .target_bounds
                .as_ref()
                .map(|bounds| self.eval_spatial_bounds(bounds, &item_ctx))
                .transpose()?;
            records.push(SpatialRecord {
                entity,
                point,
                bounds,
            });
        }
        Ok(records)
    }

    fn eval_spatial_point(&mut self, coords: &[usize], ctx: &EvalContext) -> Result<SpatialPoint> {
        let values = coords
            .iter()
            .map(|expr| {
                self.eval_expr(*expr, ctx)
                    .and_then(|value| numeric_f64(&value))
            })
            .collect::<Result<Vec<_>>>()?;
        match values.as_slice() {
            [x, y] => SpatialPoint::point2(*x, *y),
            [x, y, z] => SpatialPoint::point3(*x, *y, *z),
            _ => Err(EcsError::InvalidPlan(
                "spatial points must have 2 or 3 coordinates".to_string(),
            )),
        }
    }

    fn eval_spatial_bounds(
        &mut self,
        bounds: &SpatialBoundsExprNode,
        ctx: &EvalContext,
    ) -> Result<SpatialAabb> {
        let minimum = self.eval_spatial_point(&bounds.minimum, ctx)?;
        let maximum = self.eval_spatial_point(&bounds.maximum, ctx)?;
        SpatialAabb::new(minimum, maximum)
    }

    fn collect_expr_queries(&self, expr_index: usize, out: &mut BTreeSet<String>) -> Result<()> {
        match &self.plan.expressions[expr_index] {
            ExprNode::Field { query, .. } => {
                out.insert(query.clone());
            }
            ExprNode::Unary { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Attribute { input, .. } => self.collect_expr_queries(*input, out)?,
            ExprNode::Binary { left, right, .. } => {
                self.collect_expr_queries(*left, out)?;
                self.collect_expr_queries(*right, out)?;
            }
            ExprNode::ContextJoin {
                left_query,
                right_query,
                predicate,
            } => {
                out.insert(left_query.clone());
                out.insert(right_query.clone());
                self.collect_expr_queries(*predicate, out)?;
            }
            ExprNode::Exists { query, predicate } => {
                let mut inner = BTreeSet::new();
                self.collect_expr_queries(*predicate, &mut inner)?;
                inner.remove(query);
                out.extend(inner);
            }
            ExprNode::Aggregate { group_query, .. } => {
                if let Some(query) = group_query {
                    out.insert(query.clone());
                }
            }
            ExprNode::SpatialMetadata { relation, .. } => {
                out.insert(relation.origin_query.clone());
                out.insert(relation.item_query.clone());
            }
            ExprNode::SpatialAggregate { relation, .. } => {
                out.insert(relation.origin_query.clone());
            }
            ExprNode::LiteralF64(_)
            | ExprNode::LiteralI64(_)
            | ExprNode::LiteralBool(_)
            | ExprNode::LiteralString(_)
            | ExprNode::LiteralValue(_)
            | ExprNode::ResourceField { .. }
            | ExprNode::InputState { .. }
            | ExprNode::EventStream { .. }
            | ExprNode::ForEachItem { .. } => {}
        }
        Ok(())
    }
}

fn aggregate_empty(
    kind: &str,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if let Some(default_expr) = default {
        return executor.eval_expr(default_expr, ctx);
    }
    match kind {
        "any" => Ok(EcsValue::Bool(false)),
        "count" => Ok(EcsValue::I64(0)),
        "sum" => Ok(EcsValue::F64(0.0)),
        "min" | "max" | "mean" => Err(EcsError::InvalidPlan(format!(
            "{kind} aggregate is empty and no default was provided"
        ))),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{other}'"
        ))),
    }
}

fn aggregate_finish(
    kind: &str,
    count: usize,
    values: Vec<EcsValue>,
    default: Option<usize>,
    executor: &mut PlanExecutor<'_>,
    ctx: &EvalContext,
) -> Result<EcsValue> {
    if count == 0 && matches!(kind, "min" | "max" | "mean") {
        return aggregate_empty(kind, default, executor, ctx);
    }
    match kind {
        "any" => Ok(EcsValue::Bool(count > 0)),
        "count" => Ok(EcsValue::I64(count as i64)),
        "sum" => Ok(EcsValue::F64(
            values
                .iter()
                .map(numeric_f64)
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .sum(),
        )),
        "min" => {
            let mut iter = values.iter().map(numeric_f64);
            let mut best = iter
                .next()
                .transpose()?
                .ok_or_else(|| EcsError::InvalidPlan("min aggregate has no values".to_string()))?;
            for value in iter {
                best = best.min(value?);
            }
            Ok(EcsValue::F64(best))
        }
        "max" => {
            let mut iter = values.iter().map(numeric_f64);
            let mut best = iter
                .next()
                .transpose()?
                .ok_or_else(|| EcsError::InvalidPlan("max aggregate has no values".to_string()))?;
            for value in iter {
                best = best.max(value?);
            }
            Ok(EcsValue::F64(best))
        }
        "mean" => {
            if values.is_empty() {
                return aggregate_empty(kind, default, executor, ctx);
            }
            let sum = values
                .iter()
                .map(numeric_f64)
                .collect::<Result<Vec<_>>>()?
                .into_iter()
                .sum::<f64>();
            Ok(EcsValue::F64(sum / values.len() as f64))
        }
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported aggregate kind '{other}'"
        ))),
    }
}

fn dimensions_from_u8(dimensions: u8) -> Result<Dimensions> {
    match dimensions {
        2 => Ok(Dimensions::D2),
        3 => Ok(Dimensions::D3),
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

fn dimensions_len(dimensions: u8) -> Result<usize> {
    Ok(dimensions_from_u8(dimensions)?.len())
}

fn point_bounds(point: &SpatialPoint) -> Result<SpatialAabb> {
    SpatialAabb::new(point.clone(), point.clone())
}

fn bounds_from_values(dimensions: u8, values: &[f64]) -> Result<SpatialAabb> {
    match dimensions {
        2 => {
            if values.len() != 4 {
                return Err(EcsError::InvalidPlan(
                    "2D spatial bounds require four values".to_string(),
                ));
            }
            SpatialAabb::point2(values[0], values[1], values[2], values[3])
        }
        3 => {
            if values.len() != 6 {
                return Err(EcsError::InvalidPlan(
                    "3D spatial bounds require six values".to_string(),
                ));
            }
            SpatialAabb::point3(
                values[0], values[1], values[2], values[3], values[4], values[5],
            )
        }
        other => Err(EcsError::InvalidPlan(format!(
            "spatial dimensions must be 2 or 3, got {other}"
        ))),
    }
}

fn build_spatial_index(algorithm: &crate::plan::SpatialAlgorithmNode) -> Result<BuiltSpatialIndex> {
    let dimensions = dimensions_from_u8(algorithm.dimensions)?;
    match algorithm.kind.as_str() {
        "hash_grid" => Ok(BuiltSpatialIndex::HashGrid(HashGridIndex::new(
            dimensions,
            algorithm.cell_size.unwrap_or(1.0),
        )?)),
        "quadtree" => {
            if dimensions != Dimensions::D2 {
                return Err(EcsError::InvalidPlan(
                    "quadtree spatial algorithm requires 2D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                2,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("quadtree spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Quadtree(QuadtreeIndex::new(
                bounds,
                algorithm.capacity.unwrap_or(16),
            )?))
        }
        "octree" => {
            if dimensions != Dimensions::D3 {
                return Err(EcsError::InvalidPlan(
                    "octree spatial algorithm requires 3D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                3,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("octree spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Octree(OctreeIndex::new(
                bounds,
                algorithm.capacity.unwrap_or(16),
            )?))
        }
        "hilbert_curve" | "hilbert" => {
            if dimensions != Dimensions::D2 {
                return Err(EcsError::InvalidPlan(
                    "Hilbert spatial algorithm currently requires 2D dimensions".to_string(),
                ));
            }
            let bounds = bounds_from_values(
                2,
                algorithm.bounds.as_deref().ok_or_else(|| {
                    EcsError::InvalidPlan("Hilbert spatial algorithm requires bounds".to_string())
                })?,
            )?;
            Ok(BuiltSpatialIndex::Hilbert(HilbertIndex::new(
                bounds,
                algorithm.bits.unwrap_or(16),
            )?))
        }
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported spatial algorithm '{other}'"
        ))),
    }
}

fn eval_unary(op: &str, input: EcsValue) -> Result<EcsValue> {
    match op {
        "neg" | "-" => match input {
            EcsValue::I64(value) => Ok(EcsValue::I64(-value)),
            EcsValue::U64(value) => Ok(EcsValue::I64(-(value as i64))),
            EcsValue::F64(value) => Ok(EcsValue::F64(-value)),
            other => Err(EcsError::InvalidPlan(format!(
                "unary neg expects a numeric value, got {}",
                other.kind_name()
            ))),
        },
        "not" | "!" => Ok(EcsValue::Bool(!truthy(&input)?)),
        "abs" => Ok(EcsValue::F64(numeric_f64(&input)?.abs())),
        "sqrt" => Ok(EcsValue::F64(numeric_f64(&input)?.sqrt())),
        "sin" => Ok(EcsValue::F64(numeric_f64(&input)?.sin())),
        "cos" => Ok(EcsValue::F64(numeric_f64(&input)?.cos())),
        "floor" => Ok(EcsValue::F64(numeric_f64(&input)?.floor())),
        "ceil" => Ok(EcsValue::F64(numeric_f64(&input)?.ceil())),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported physical unary op '{other}'"
        ))),
    }
}

fn default_input_state_value(name: &str) -> EcsValue {
    match name {
        "dt" | "delta_time" => EcsValue::F64(0.0),
        "key_down" => EcsValue::Bool(false),
        _ => EcsValue::Bool(false),
    }
}

fn eval_binary(op: &str, left: EcsValue, right: EcsValue) -> Result<EcsValue> {
    match op {
        "add" | "+" => numeric_arithmetic(left, right, |a, b| a + b),
        "sub" | "-" => numeric_arithmetic(left, right, |a, b| a - b),
        "mul" | "*" => numeric_arithmetic(left, right, |a, b| a * b),
        "truediv" | "/" => Ok(EcsValue::F64(numeric_f64(&left)? / numeric_f64(&right)?)),
        "floordiv" | "//" => Ok(EcsValue::F64(
            (numeric_f64(&left)? / numeric_f64(&right)?).floor(),
        )),
        "mod" | "%" => Ok(EcsValue::F64(numeric_f64(&left)? % numeric_f64(&right)?)),
        "pow" | "**" => Ok(EcsValue::F64(
            numeric_f64(&left)?.powf(numeric_f64(&right)?),
        )),
        "lt" | "<" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| a < b)?)),
        "le" | "<=" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| {
            a <= b
        })?)),
        "gt" | ">" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| a > b)?)),
        "ge" | ">=" => Ok(EcsValue::Bool(compare_values(&left, &right, |a, b| {
            a >= b
        })?)),
        "eq" | "==" => Ok(EcsValue::Bool(values_equal(&left, &right)?)),
        "ne" | "!=" => Ok(EcsValue::Bool(!values_equal(&left, &right)?)),
        "min" => Ok(if numeric_f64(&left)? <= numeric_f64(&right)? {
            left
        } else {
            right
        }),
        "max" => Ok(if numeric_f64(&left)? >= numeric_f64(&right)? {
            left
        } else {
            right
        }),
        other => Err(EcsError::InvalidPlan(format!(
            "unsupported physical binary op '{other}'"
        ))),
    }
}

fn numeric_arithmetic(
    left: EcsValue,
    right: EcsValue,
    op: impl FnOnce(f64, f64) -> f64,
) -> Result<EcsValue> {
    Ok(EcsValue::F64(op(numeric_f64(&left)?, numeric_f64(&right)?)))
}

fn numeric_f64(value: &EcsValue) -> Result<f64> {
    match value {
        EcsValue::Bool(value) => Ok(if *value { 1.0 } else { 0.0 }),
        EcsValue::I64(value) => Ok(*value as f64),
        EcsValue::U64(value) => Ok(*value as f64),
        EcsValue::F64(value) => Ok(*value),
        other => Err(EcsError::InvalidPlan(format!(
            "expected numeric ECS value, got {}",
            other.kind_name()
        ))),
    }
}

fn truthy(value: &EcsValue) -> Result<bool> {
    match value {
        EcsValue::Bool(value) => Ok(*value),
        EcsValue::I64(value) => Ok(*value != 0),
        EcsValue::U64(value) => Ok(*value != 0),
        EcsValue::F64(value) => Ok(*value != 0.0),
        other => Err(EcsError::InvalidPlan(format!(
            "expected boolean-compatible ECS value, got {}",
            other.kind_name()
        ))),
    }
}

fn compare_values(
    left: &EcsValue,
    right: &EcsValue,
    op: impl FnOnce(f64, f64) -> bool,
) -> Result<bool> {
    Ok(op(numeric_f64(left)?, numeric_f64(right)?))
}

fn values_equal(left: &EcsValue, right: &EcsValue) -> Result<bool> {
    match (left, right) {
        (EcsValue::Bool(left), EcsValue::Bool(right)) => Ok(left == right),
        (EcsValue::String(left), EcsValue::String(right)) => Ok(left == right),
        (
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
            EcsValue::I64(_) | EcsValue::U64(_) | EcsValue::F64(_),
        ) => Ok(numeric_f64(left)? == numeric_f64(right)?),
        _ => Ok(left == right),
    }
}

fn coerce_value_for_storage(storage_type: StorageType, value: EcsValue) -> Result<EcsValue> {
    match storage_type {
        StorageType::Bool => match value {
            EcsValue::Bool(value) => Ok(EcsValue::Bool(value)),
            other => Err(type_mismatch("Bool", other)),
        },
        StorageType::Int8 | StorageType::Int16 | StorageType::Int32 | StorageType::Int64 => {
            match value {
                EcsValue::I64(value) => Ok(EcsValue::I64(value)),
                EcsValue::U64(value) if value <= i64::MAX as u64 => Ok(EcsValue::I64(value as i64)),
                EcsValue::F64(value)
                    if value.is_finite()
                        && value.fract() == 0.0
                        && value >= i64::MIN as f64
                        && value <= i64::MAX as f64 =>
                {
                    Ok(EcsValue::I64(value as i64))
                }
                other => Err(type_mismatch("I64", other)),
            }
        }
        StorageType::UInt8 | StorageType::UInt16 | StorageType::UInt32 | StorageType::UInt64 => {
            match value {
                EcsValue::U64(value) => Ok(EcsValue::U64(value)),
                EcsValue::I64(value) if value >= 0 => Ok(EcsValue::U64(value as u64)),
                EcsValue::F64(value)
                    if value.is_finite()
                        && value.fract() == 0.0
                        && value >= 0.0
                        && value <= u64::MAX as f64 =>
                {
                    Ok(EcsValue::U64(value as u64))
                }
                other => Err(type_mismatch("U64", other)),
            }
        }
        StorageType::Float32 | StorageType::Float64 => match value {
            EcsValue::F64(value) => Ok(EcsValue::F64(value)),
            EcsValue::I64(value) => Ok(EcsValue::F64(value as f64)),
            EcsValue::U64(value) => Ok(EcsValue::F64(value as f64)),
            other => Err(type_mismatch("F64", other)),
        },
        StorageType::String | StorageType::CategoricalString => match value {
            EcsValue::String(value) => Ok(EcsValue::String(value)),
            other => Err(type_mismatch("String", other)),
        },
        StorageType::Vec2F32 => match value {
            EcsValue::Vec2F32(value) => Ok(EcsValue::Vec2F32(value)),
            EcsValue::Vec2F64(value) => Ok(EcsValue::Vec2F32([value[0] as f32, value[1] as f32])),
            other => Err(type_mismatch("Vec2F32", other)),
        },
        StorageType::Vec2F64 => match value {
            EcsValue::Vec2F64(value) => Ok(EcsValue::Vec2F64(value)),
            EcsValue::Vec2F32(value) => Ok(EcsValue::Vec2F64([value[0] as f64, value[1] as f64])),
            other => Err(type_mismatch("Vec2F64", other)),
        },
        StorageType::Vec3F32 => match value {
            EcsValue::Vec3F32(value) => Ok(EcsValue::Vec3F32(value)),
            EcsValue::Vec3F64(value) => Ok(EcsValue::Vec3F32([
                value[0] as f32,
                value[1] as f32,
                value[2] as f32,
            ])),
            other => Err(type_mismatch("Vec3F32", other)),
        },
        StorageType::Vec3F64 => match value {
            EcsValue::Vec3F64(value) => Ok(EcsValue::Vec3F64(value)),
            EcsValue::Vec3F32(value) => Ok(EcsValue::Vec3F64([
                value[0] as f64,
                value[1] as f64,
                value[2] as f64,
            ])),
            other => Err(type_mismatch("Vec3F64", other)),
        },
        StorageType::List => match value {
            EcsValue::List(value) => Ok(EcsValue::List(value)),
            other => Err(type_mismatch("List", other)),
        },
    }
}

fn type_mismatch(expected: &'static str, value: EcsValue) -> EcsError {
    EcsError::ColumnTypeMismatch {
        expected,
        got: value.kind_name(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::plan::{BridgeQueryPayload, BRIDGE_PLAN_VERSION};
    use crate::query::QueryTerm;
    use crate::schema::{ComponentSchema, FieldSchema};

    fn world_with_motion() -> (World, Entity) {
        let mut world = World::new();
        world
            .register_schema(ComponentSchema::new(
                "Position",
                vec![
                    FieldSchema::new("x", StorageType::Float64),
                    FieldSchema::new("y", StorageType::Float64),
                ],
            ))
            .unwrap();
        world
            .register_schema(ComponentSchema::new(
                "Velocity",
                vec![FieldSchema::new("dx", StorageType::Float64)],
            ))
            .unwrap();
        world
            .register_schema(ComponentSchema::new(
                "Clock",
                vec![FieldSchema::new("tick", StorageType::Int64)],
            ))
            .unwrap();
        let entity = world
            .spawn_with_defaults(["Position".to_string(), "Velocity".to_string()])
            .unwrap();
        world
            .set_field(entity, "Position", "x", EcsValue::F64(2.0))
            .unwrap();
        world
            .set_field(entity, "Velocity", "dx", EcsValue::F64(3.0))
            .unwrap();
        (world, entity)
    }

    #[test]
    fn physical_plan_executes_scalar_set_over_query_rows() {
        let (mut world, entity) = world_with_motion();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![
                    QueryTerm::WithComponent("Position".to_string()),
                    QueryTerm::WithComponent("Velocity".to_string()),
                ],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Velocity".to_string(),
                    field: "dx".to_string(),
                },
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 0,
                    right: 1,
                },
            ],
            actions: vec![ActionNode::SetField {
                target: 0,
                value: 2,
            }],
            root_action: 0,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(5.0)
        );
        assert_eq!(report.fields_written, 1);
        assert_eq!(report.writes.len(), 1);
    }

    #[test]
    fn physical_parallel_uses_snapshot_reads_and_stable_merge() {
        let (mut world, entity) = world_with_motion();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![QueryTerm::WithComponent("Position".to_string())],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "y".to_string(),
                },
                ExprNode::LiteralF64(5.0),
            ],
            actions: vec![
                ActionNode::SetField {
                    target: 0,
                    value: 2,
                },
                ActionNode::SetField {
                    target: 1,
                    value: 0,
                },
                ActionNode::Parallel(vec![0, 1]),
            ],
            root_action: 2,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(5.0)
        );
        assert_eq!(
            world.get_field(entity, "Position", "y").unwrap(),
            EcsValue::F64(2.0)
        );
        assert_eq!(report.fields_written, 2);
        assert_eq!(report.duplicate_writes, 0);
    }

    #[test]
    fn physical_plan_executes_conditionals_and_resources() {
        let (mut world, entity) = world_with_motion();
        let mut clock = HashMap::new();
        clock.insert("tick".to_string(), EcsValue::I64(1));
        world.insert_resource("Clock", clock).unwrap();
        let payload = BridgePlanPayload {
            version: BRIDGE_PLAN_VERSION,
            schema_fingerprint: Some(world.schema_fingerprint()),
            queries: vec![BridgeQueryPayload {
                name: "entity".to_string(),
                terms: vec![QueryTerm::WithComponent("Position".to_string())],
                allowed_entities: None,
            }],
            expressions: vec![
                ExprNode::Field {
                    query: "entity".to_string(),
                    component: "Position".to_string(),
                    field: "x".to_string(),
                },
                ExprNode::LiteralF64(1.0),
                ExprNode::Binary {
                    op: "gt".to_string(),
                    left: 0,
                    right: 1,
                },
                ExprNode::ResourceField {
                    resource: "Clock".to_string(),
                    field: "tick".to_string(),
                },
                ExprNode::LiteralI64(2),
                ExprNode::Binary {
                    op: "add".to_string(),
                    left: 3,
                    right: 4,
                },
            ],
            actions: vec![
                ActionNode::SetField {
                    target: 3,
                    value: 5,
                },
                ActionNode::When {
                    condition: 2,
                    then_action: 0,
                    otherwise_action: None,
                },
            ],
            root_action: 1,
        };

        let report = world.execute_bridge_plan(payload).unwrap();

        assert_eq!(
            world.resource_field("Clock", "tick").unwrap(),
            EcsValue::I64(3)
        );
        assert_eq!(
            world.get_field(entity, "Position", "x").unwrap(),
            EcsValue::F64(2.0)
        );
        assert_eq!(report.resource_fields_written, 1);
    }
}
