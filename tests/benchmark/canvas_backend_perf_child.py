from __future__ import annotations

import json
import platform
import sys
import time

from canvas_backend_perf_scenes import draw_scene, setup_scene

import gummysnake as gs
from gummysnake.rust.canvas import canvas_gpu_available, require_canvas_runtime


def _flatten_metrics(counters):
    native = counters.get("native", {})
    if not isinstance(native, dict):
        native = {}
    python_bridge_calls = int(counters.get("bridge_calls", 0))
    native_bridge_calls = int(native.get("bridge_calls", 0))
    return {
        "gpu_draws": int(native.get("gpu_draws", counters.get("gpu_draws", 0))),
        "gpu_primitive_batches": int(native.get("gpu_primitive_batches", 0)),
        "gpu_image_batches": int(native.get("gpu_image_batches", 0)),
        "gpu_vertex_buffer_allocations": int(native.get("gpu_vertex_buffer_allocations", 0)),
        "gpu_vertex_uploads": int(native.get("gpu_vertex_uploads", 0)),
        "gpu_uploaded_vertex_bytes": int(native.get("gpu_uploaded_vertex_bytes", 0)),
        "gpu_encode_time_ms": float(native.get("gpu_encode_time_ms", 0.0)),
        "gpu_present_time_ms": float(native.get("gpu_present_time_ms", 0.0)),
        "gpu_region_effect_passes": int(native.get("gpu_region_effect_passes", 0)),
        "gpu_blend_commands": int(native.get("gpu_blend_commands", 0)),
        "native_draw_commands": int(native.get("native_draw_commands", 0)),
        "native_triangle_commands": int(native.get("native_triangle_commands", 0)),
        "native_ellipse_commands": int(native.get("native_ellipse_commands", 0)),
        "native_image_commands": int(native.get("native_image_commands", 0)),
        "native_text_commands": int(native.get("native_text_commands", 0)),
        "native_model_commands": int(native.get("native_model_commands", 0)),
        "native_erase_commands": int(native.get("native_erase_commands", 0)),
        "native_region_effect_commands": int(native.get("native_region_effect_commands", 0)),
        "native_primitive_instance_commands": int(
            native.get("native_primitive_instance_commands", 0)
        ),
        "native_staged_primitive_vertices": int(native.get("native_staged_primitive_vertices", 0)),
        "native_staged_image_vertices": int(native.get("native_staged_image_vertices", 0)),
        "native_primitive_records": int(native.get("native_primitive_records", 0)),
        "native_primitive_batches": int(native.get("native_primitive_batches", 0)),
        "native_command_ingest_time_ms": float(native.get("native_command_ingest_time_ms", 0.0)),
        "pixel_readbacks": int(native.get("pixel_readbacks", counters.get("pixel_readbacks", 0))),
        "pixel_uploads": int(native.get("pixel_uploads", counters.get("pixel_uploads", 0))),
        "texture_cache_hits": int(native.get("texture_cache_hits", 0)),
        "texture_uploads": int(native.get("texture_uploads", counters.get("texture_uploads", 0))),
        "text_cache_hits": int(native.get("text_cache_hits", counters.get("text_cache_hits", 0))),
        "text_cache_misses": int(
            native.get("text_cache_misses", counters.get("text_cache_misses", 0))
        ),
        "frames_presented": int(native.get("frames_presented", 0)),
        "gpu_frames_rendered": int(native.get("gpu_frames_rendered", 0)),
        "bridge_calls": python_bridge_calls,
        "python_bridge_calls": python_bridge_calls,
        "native_bridge_calls": native_bridge_calls,
        "cpu_fallbacks": int(native.get("cpu_fallbacks", counters.get("cpu_fallbacks", 0))),
        "direct_model_draws": int(native.get("direct_model_draws", 0)),
        "python_face_payloads": int(native.get("python_face_payloads", 0)),
        "primitive_batch_records": int(counters.get("primitive_batch_records", 0)),
        "primitive_batch_flushes": int(counters.get("primitive_batch_flushes", 0)),
        "primitive_batch_max_records": int(counters.get("primitive_batch_max_records", 0)),
        "primitive_batch_fallbacks": int(counters.get("primitive_batch_fallbacks", 0)),
        "image_batch_records": int(counters.get("image_batch_records", 0)),
        "image_batch_flushes": int(counters.get("image_batch_flushes", 0)),
        "image_batch_max_records": int(counters.get("image_batch_max_records", 0)),
        "image_batch_fallbacks": int(counters.get("image_batch_fallbacks", 0)),
        "retained_batch_cache_hits": int(native.get("retained_batch_cache_hits", 0)),
        "retained_batch_cache_misses": int(native.get("retained_batch_cache_misses", 0)),
        "retained_batch_cache_evictions": int(native.get("retained_batch_cache_evictions", 0)),
        "retained_batch_reused_bytes": int(native.get("retained_batch_reused_bytes", 0)),
    }


def main() -> None:
    variant = sys.argv[1]
    frames = int(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "interactive"
    if mode not in {"interactive", "headless"}:
        raise ValueError("benchmark mode must be 'interactive' or 'headless'")
    start = 0.0
    python_draw_time = 0.0
    canvas_size = [0, 0]

    def setup() -> None:
        nonlocal start, canvas_size
        setup_scene(variant)
        canvas_size = [gs.current.width, gs.current.height]
        start = time.perf_counter()

    def draw() -> None:
        nonlocal python_draw_time
        draw_start = time.perf_counter()
        draw_scene(variant)
        python_draw_time += time.perf_counter() - draw_start

    require_canvas_runtime()
    context = gs.run(setup=setup, draw=draw, headless=(mode == "headless"), max_frames=frames)
    elapsed = time.perf_counter() - start
    metrics = _flatten_metrics(context.renderer_performance_counters())
    metrics["python_draw_time_ms"] = python_draw_time * 1000.0
    print(
        json.dumps(
            {
                "variant": variant,
                "frames": frames,
                "canvas_size": canvas_size,
                "pixel_density": 1.0,
                "backend_mode": mode,
                "gpu_available": canvas_gpu_available(),
                "metrics": metrics,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "elapsed": elapsed,
                "fps": frames / max(elapsed, 1e-9),
            }
        )
    )


if __name__ == "__main__":
    main()
