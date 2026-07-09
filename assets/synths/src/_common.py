"""Shared metadata helpers for bundled source-defined synths."""

from __future__ import annotations

from gummysnake import synth as sy

SAMPLE_PLAYER_SYNTHS = frozenset(
    {
        "mono_player",
        "stereo_player",
        "basic_mono_player",
        "basic_stereo_player",
        "mono_player-future",
        "stereo_player-future",
        "stereo_warp_sample",
    }
)
INPUT_OR_MIXER_SYNTHS = frozenset(
    {
        "amp_stereo_monitor",
        "basic_mixer",
        "live_audio_mono",
        "live_audio_stereo",
        "main_mixer",
        "mixer",
        "recorder",
        "scope",
        "server-info",
        "sound_in",
        "sound_in_stereo",
    }
)
PERCUSSIVE_SYNTHS = frozenset(
    {
        "arpeg-click",
        "gabberkick",
        "gabberkick_gated",
        "kalimba",
        "kalimba_gated",
        "sc808_bassdrum",
        "sc808_clap",
        "sc808_claves",
        "sc808_closed_hihat",
        "sc808_congahi",
        "sc808_congalo",
        "sc808_congamid",
        "sc808_cowbell",
        "sc808_cymbal",
        "sc808_maracas",
        "sc808_open_hihat",
        "sc808_rimshot",
        "sc808_snare",
        "sc808_tomhi",
        "sc808_tomlo",
        "sc808_tommid",
    }
)
LONG_TAIL_SYNTHS = frozenset(
    {
        "blade",
        "blade_gated",
        "dark_ambience",
        "dark_ambience_gated",
        "dark_sea_horn",
        "dull_bell",
        "hollow",
        "hollow_gated",
        "organ_tonewheel",
        "piano",
        "piano_gated",
        "pluck",
        "pluck_gated",
        "pretty_bell",
        "rhodey",
        "rhodey_gated",
        "space_organ",
    }
)


def synth_duration(name: str) -> sy.Duration:
    """Return the bounded compile duration for a bundled synth definition."""

    if name in SAMPLE_PLAYER_SYNTHS:
        return sy.duration(secs=0.3)
    if name in INPUT_OR_MIXER_SYNTHS:
        return sy.duration(secs=0.05)
    if name in PERCUSSIVE_SYNTHS:
        return sy.duration(secs=0.8)
    if name in LONG_TAIL_SYNTHS:
        return sy.duration(secs=1.5)
    return sy.duration(secs=1.0)


def module_name(name: str) -> str:
    """Return the Python module/function stem for a Sonic Pi synth key."""

    return name.replace("-", "_")
