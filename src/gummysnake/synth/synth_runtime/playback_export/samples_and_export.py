from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Mapping
from pathlib import Path

from gummysnake.exceptions import BackendCapabilityError
from gummysnake.synth.synth_runtime.values.foundation import Format, _as_float

_BUILTIN_SAMPLE_DURATIONS = {
    "loop_amen": 1.753310657596372,
    "loop_garzul": 4.0,
    "loop_industrial": 4.0,
    "loop_mika": 4.0,
    "ambi_choir": 3.2,
    "ambi_drone": 4.0,
    "ambi_lunar_land": 5.0,
    "drum_heavy_kick": 0.45,
    "drum_bass_hard": 0.35,
    "drum_cymbal_closed": 0.25,
    "drum_cymbal_open": 1.0,
    "drum_cymbal_soft": 0.5,
    "drum_snare_hard": 0.35,
    "bass_hit_c": 0.55,
    "bass_trance_c": 1.0,
    "bass_voxy_hit_c": 0.7,
    "elec_plip": 0.2,
    "elec_blup": 0.25,
    "elec_blip2": 0.18,
    "elec_beep": 0.18,
    "elec_flip": 0.2,
    "elec_hi_snare": 0.25,
    "elec_snare": 0.25,
    "elec_filt_snare": 0.25,
    "perc_bell": 1.2,
    "guit_em9": 3.0,
    "bd_haus": 0.4,
    "bd_boom": 1.0,
    "bd_ada": 0.35,
    "misc_burp": 0.6,
}


def _sample_duration_seconds(value: object, opts: Mapping[str, object]) -> float:
    # Metadata-only helper; actual audio rendering is Rust-owned.
    from gummysnake.synth.synth_runtime.composition.event_api import _resolve_sample_source
    from gummysnake.synth.synth_runtime.physical.rendering import _require_synth_runtime

    name = value[0] if isinstance(value, tuple) and value else value
    resolved_name = _resolve_sample_source(name)
    if isinstance(resolved_name, Path) or (
        isinstance(resolved_name, str) and Path(resolved_name).exists()
    ):
        base = float(_require_synth_runtime().synth_sample_duration(str(resolved_name)))
    elif isinstance(name, Path) or (isinstance(name, str) and Path(name).exists()):
        base = float(_require_synth_runtime().synth_sample_duration(str(name)))
    else:
        base = _BUILTIN_SAMPLE_DURATIONS.get(str(name).removeprefix(":"), 0.5)
    start = _as_float(opts.get("start", 0.0) or 0.0)
    finish = _as_float(opts.get("finish", 1.0) or 1.0)
    fraction = abs(finish - start)
    if "beat_stretch" in opts:
        return _as_float(opts["beat_stretch"])
    rate_value = _as_float(opts.get("rate", 1.0) or 1.0)
    if "rpitch" in opts:
        rate_value *= 2.0 ** (_as_float(opts["rpitch"]) / 12.0)
    return base * max(0.0, fraction) / max(0.0001, abs(rate_value))


def _wav_duration_seconds(payload: bytes) -> float:
    with wave.open(io.BytesIO(payload), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())


def _resolve_format(path: Path, format_value: Format | str | None) -> Format:
    if format_value is not None:
        return Format(format_value)
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "gss":
        return Format.GSS
    if suffix == "gsfx":
        return Format.GSFX
    if suffix == "mp3":
        return Format.MP3
    return Format.WAV


def _write_mp3_with_ffmpeg(wav_payload: bytes, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise BackendCapabilityError(
            "MP3 export requires ffmpeg on PATH. Save WAV or install ffmpeg."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.gummysnake-",
        suffix=".mp3",
        delete=False,
    ) as file:
        temporary_output = Path(file.name)
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "wav",
                "-i",
                "pipe:0",
                str(temporary_output),
            ],
            input=wav_payload,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        temporary_output.replace(output_path)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip()
        message = f"ffmpeg could not export MP3 to {output_path!s}."
        if detail:
            message = f"{message} {detail}"
        raise BackendCapabilityError(message) from exc
    except OSError as exc:
        raise BackendCapabilityError(
            f"MP3 export could not update {output_path!s} atomically: {exc}"
        ) from exc
    finally:
        with contextlib.suppress(OSError):
            temporary_output.unlink(missing_ok=True)
