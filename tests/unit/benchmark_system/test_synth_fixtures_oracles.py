from __future__ import annotations

from dataclasses import replace

import pytest

from benchmarks.suites.synth.fixtures import (
    fixture_manifest,
    generate_signal,
    pcm_wav_bytes,
    validate_manifest,
)
from benchmarks.suites.synth.oracles import (
    SynthOracleError,
    assert_repeatable,
    assert_wav_contract,
    decode_pcm_wav,
)


def test_synth_fixture_manifest_covers_the_generated_signal_corpus() -> None:
    manifest = fixture_manifest()

    validate_manifest(manifest)
    assert {entry.name for entry in manifest} == {
        "impulse-mono",
        "impulse-stereo",
        "silence",
        "sine",
        "dual-tone",
        "chirp",
        "noise",
        "asymmetric-stereo",
        "transients",
        "envelope-control",
    }
    assert all(entry.frames > 0 and entry.byte_length > 44 for entry in manifest)
    assert all(len(entry.sha256) == 64 for entry in manifest)
    assert all(set(entry.spectral_bands) == {"signal", "difference"} for entry in manifest)


def test_synth_fixture_manifest_rejects_stale_signal_metadata() -> None:
    manifest = fixture_manifest()
    stale = (replace(manifest[0], frames=manifest[0].frames + 1), *manifest[1:])

    with pytest.raises(ValueError, match="does not match"):
        validate_manifest(stale)


def test_pcm_oracles_cover_supported_generated_widths_and_stereo() -> None:
    fixture = generate_signal("asymmetric-stereo", sample_rate=8_000, duration_seconds=0.02)

    for width in (1, 2, 4):
        payload = pcm_wav_bytes(fixture, sample_width=width)
        decoded = decode_pcm_wav(payload)
        summary = assert_wav_contract(payload, sample_rate=8_000)

        assert decoded.sample_width == width
        assert decoded.channels == 2
        assert decoded.frames == fixture.frames == summary.frames
        assert summary.left_rms > summary.right_rms


def test_repeat_digest_oracle_rejects_changed_pcm() -> None:
    payload = pcm_wav_bytes(generate_signal("sine"))

    assert assert_repeatable(payload, payload, label="fixture").startswith("sha256:")
    with pytest.raises(SynthOracleError, match="not byte-exact"):
        assert_repeatable(payload, payload + b"changed", label="fixture")
