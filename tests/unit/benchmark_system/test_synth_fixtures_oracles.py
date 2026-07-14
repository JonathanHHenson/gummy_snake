from __future__ import annotations

from dataclasses import replace

import pytest

from benchmarks.suites.synth.fixtures import (
    ffmpeg_mp3_capability,
    fixture_manifest,
    generate_signal,
    packaged_sample_catalog,
    pcm_variant_catalog,
    pcm_variant_manifest,
    pcm_wav_bytes,
    validate_manifest,
    validate_packaged_sample_catalog,
    validate_pcm_variant_manifest,
)
from benchmarks.suites.synth.oracles import (
    SynthOracleError,
    assert_generated_signal,
    assert_lifecycle_contract,
    assert_repeatable,
    assert_unqualified_device,
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


def test_complete_pcm_variant_manifest_covers_rates_widths_and_channels() -> None:
    catalog = pcm_variant_catalog()
    manifest = pcm_variant_manifest()

    validate_pcm_variant_manifest(manifest)
    assert len(catalog) == len(manifest) == 24
    assert {entry.sample_rate for entry in manifest} == {8_000, 16_000, 44_100, 48_000}
    assert {entry.sample_width for entry in manifest} == {1, 2, 4}
    assert {entry.channels for entry in manifest} == {1, 2}
    assert all(entry.byte_length > 44 and len(entry.sha256) == 64 for entry in manifest)


def test_packaged_flac_catalog_is_pinned_and_contains_a_minimal_reviewed_case() -> None:
    catalog = packaged_sample_catalog()
    paths = validate_packaged_sample_catalog()

    assert {case.name for case in catalog} == {
        "reviewed-minimal-flac",
        "packaged-transient-flac",
        "packaged-loop-flac",
    }
    assert all(case.license == "CC0-1.0" for case in catalog)
    assert all(paths[case.name].read_bytes().startswith(b"fLaC") for case in catalog)
    assert min(case.byte_length for case in catalog) == 18_056


def test_ffmpeg_mp3_capability_never_claims_a_substitute_encoder() -> None:
    capability = ffmpeg_mp3_capability().as_dict()

    assert capability["codec"] == "mp3-ffmpeg"
    assert capability["substitute_used"] is False
    if capability["available"]:
        assert capability["executable"]
        assert capability["reason"] is None
    else:
        assert capability["executable"] is None
        assert "no substitute" in str(capability["reason"]).lower()


def test_generated_signal_oracle_respects_pcm_quantization() -> None:
    fixture = generate_signal("asymmetric-stereo", sample_rate=8_000, duration_seconds=0.02)
    payload = pcm_wav_bytes(fixture, sample_width=2)

    pcm = assert_generated_signal(
        payload,
        expected_left=fixture.left,
        expected_right=fixture.right,
        tolerance=1.0 / 32767.0,
    )
    assert pcm.channels == 2
    with pytest.raises(SynthOracleError, match="exceeds"):
        assert_generated_signal(
            payload,
            expected_left=(1.0,) * fixture.frames,
            expected_right=fixture.right,
            tolerance=1e-9,
        )


def test_lifecycle_and_device_oracles_reject_false_qualification() -> None:
    with pytest.raises(SynthOracleError, match="schema_version"):
        assert_lifecycle_contract({"schema_version": 1})
    assert_unqualified_device(
        {
            "schema_version": 1,
            "qualified": False,
            "available": False,
            "audibility_claimed": False,
        }
    )
    with pytest.raises(SynthOracleError, match="must not be marked qualified"):
        assert_unqualified_device(
            {"schema_version": 1, "qualified": True, "audibility_claimed": False}
        )


def test_repeat_digest_oracle_rejects_changed_pcm() -> None:
    payload = pcm_wav_bytes(generate_signal("sine"))

    assert assert_repeatable(payload, payload, label="fixture").startswith("sha256:")
    with pytest.raises(SynthOracleError, match="not byte-exact"):
        assert_repeatable(payload, payload + b"changed", label="fixture")
