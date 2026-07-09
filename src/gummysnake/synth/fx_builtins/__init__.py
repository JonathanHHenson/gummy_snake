"""Source definitions for bundled Sonic Pi-style FX physical-plan assets."""

from __future__ import annotations

SONIC_PI_FX_KEYS: tuple[str, ...] = (
    "bitcrusher",
    "krush",
    "reverb",
    "gverb",
    "level",
    "echo",
    "slicer",
    "panslicer",
    "wobble",
    "ixi_techno",
    "compressor",
    "whammy",
    "rlpf",
    "nrlpf",
    "rhpf",
    "nrhpf",
    "hpf",
    "nhpf",
    "lpf",
    "nlpf",
    "normaliser",
    "distortion",
    "pan",
    "bpf",
    "nbpf",
    "rbpf",
    "nrbpf",
    "band_eq",
    "tanh",
    "pitch_shift",
    "ring_mod",
    "octaver",
    "vowel",
    "flanger",
)

__all__ = ["SONIC_PI_FX_KEYS"]
