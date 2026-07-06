"""Query-term serialization for ECS physical payloads."""

from __future__ import annotations

from collections.abc import Callable

from gummysnake.ecs.expressions import QueryProxy
from gummysnake.ecs.physical_payload.helpers import schema_name
from gummysnake.ecs.physical_payload.types import BridgeNode, PayloadState, PhysicalPlanUnsupported
from gummysnake.ecs.specs import ChangeTerm, QuerySpec, TagTerm, WithoutTerm
from gummysnake.exceptions import SystemPlanError

type AddTerm = Callable[[str, str], None]


def query_payload(state: PayloadState, query: QueryProxy) -> BridgeNode:
    """Serialize one query proxy into the Rust bridge query payload."""

    spec = query.spec
    if not isinstance(spec, QuerySpec):
        raise PhysicalPlanUnsupported(f"query {query.name!r} has an unsupported specification")

    terms: list[tuple[str, str]] = []
    seen_terms: set[tuple[str, str]] = set()
    change_terms: list[ChangeTerm] = []

    def add_term(kind: str, name: str) -> None:
        term = (kind, name)
        if term not in seen_terms:
            seen_terms.add(term)
            terms.append(term)

    for term in spec.terms:
        if isinstance(term, TagTerm):
            _add_tag_term(add_term, "with_tag", term.value)
        elif isinstance(term, WithoutTerm):
            _add_without_term(state, add_term, term.value)
        elif isinstance(term, ChangeTerm):
            state.world.validate_schema(term.component_type)
            change_terms.append(term)
            if term.kind != "removed":
                add_term("with_component", schema_name(term.component_type))
        elif isinstance(term, type):
            state.world.validate_schema(term)
            add_term("with_component", schema_name(term))
        else:
            raise PhysicalPlanUnsupported(f"unsupported query term {term!r}")

    payload: BridgeNode = {"name": query.name, "terms": terms}
    if change_terms:
        state.mark_dynamic()
        matches = state.world.match_query(spec)
        payload["allowed_entities"] = [
            (int(entity.entity.index), int(entity.entity.generation)) for entity in matches
        ]
    return payload


def _add_tag_term(add_term: AddTerm, kind: str, value: object) -> None:
    tag = str(value)
    if not tag:
        raise SystemPlanError("ECS tag values cannot be empty.")
    add_term(kind, tag)


def _add_without_term(state: PayloadState, add_term: AddTerm, value: object) -> None:
    if isinstance(value, TagTerm):
        _add_tag_term(add_term, "without_tag", value.value)
    elif isinstance(value, type):
        state.world.validate_schema(value)
        add_term("without_component", schema_name(value))
    else:
        raise PhysicalPlanUnsupported(f"unsupported ecs.Without query term {value!r}")
