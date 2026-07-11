"""Rust-owned mesh buffer construction and lazy hydration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from gummysnake.drawing.renderer3d._mesh_buffers import (
    MeshFaceInput,
    MeshFloatInput,
    MeshIndexInput,
    MeshRustHandle,
    Vec2Rows,
    Vec3Rows,
    coerce_vec2_rows,
    coerce_vec3_rows,
    create_rust_mesh_handle,
    pack_faces,
    resolve_face_buffers,
)


@dataclass(frozen=True, slots=True)
class MeshBufferData:
    """Immutable Python inspection buffers materialized from a mesh handle."""

    vertices: Vec3Rows
    face_indices: tuple[int, ...]
    face_offsets: tuple[int, ...]
    normals: Vec3Rows
    texcoords: Vec2Rows


def create_mesh_handle_from_input(
    vertices: MeshFloatInput,
    faces: MeshFaceInput,
    normals: MeshFloatInput,
    texcoords: MeshFloatInput,
    *,
    face_indices: MeshIndexInput | None,
    face_offsets: MeshIndexInput | None,
) -> MeshRustHandle:
    """Coerce input buffers and create the canonical Rust mesh handle."""
    vertex_rows = coerce_vec3_rows(vertices, name="vertices")
    packed_indices, packed_offsets = resolve_face_buffers(
        faces, face_indices, face_offsets, len(vertex_rows)
    )
    return create_rust_mesh_handle(
        vertex_rows,
        packed_indices,
        packed_offsets,
        coerce_vec3_rows(normals, name="normals"),
        coerce_vec2_rows(texcoords, name="texcoords"),
    )


def hydrate_mesh_buffers(handle: MeshRustHandle) -> MeshBufferData:
    """Materialize immutable Python buffers from a Rust-owned mesh handle."""
    payload = handle.to_mesh_payload()
    vertices = coerce_vec3_rows(cast(MeshFloatInput, payload["vertices"]), name="vertices")
    indices, offsets = pack_faces(cast(MeshFaceInput, payload["faces"]), len(vertices))
    return MeshBufferData(
        vertices=vertices,
        face_indices=indices,
        face_offsets=offsets,
        normals=coerce_vec3_rows(cast(MeshFloatInput, payload.get("normals", ())), name="normals"),
        texcoords=coerce_vec2_rows(
            cast(MeshFloatInput, payload.get("texcoords", ())), name="texcoords"
        ),
    )
