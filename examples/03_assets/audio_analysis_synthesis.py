"""Interactive audio synthesis controls with analysis, filtering, and playback."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gummysnake as gs
from examples.common import example_parser, save_once

OUTPUT = Path("examples/output/03_assets/audio_analysis_synthesis.png")
ARGS = example_parser(__doc__ or "", OUTPUT).parse_args()

CHECKBOX_X = 32.0
CHECKBOX_Y = 108.0
CHECKBOX_SIZE = 22.0

WAVEFORM = "sawtooth"
FREQUENCY = 220.0
AMPLITUDE = 0.75
FILTER_CUTOFF = 1_200.0
PLAY_AUDIO = False
PLAYBACK_STATUS = "click the checkbox to play the filtered synthesized oscillator"
ACTIVE_SLIDER: str | None = None

SAMPLES: tuple[float, ...] = ()
FILTERED: tuple[float, ...] = ()
SPECTRUM: tuple[float, ...] = ()
LEVEL = 0.0
AUDIO_CONTEXT: dict[str, object] = {}
SYNTH_SOUND: gs.Sound | None = None


@dataclass(frozen=True, slots=True)
class Slider:
    key: str
    label: str
    x: float
    y: float
    width: float
    min_value: float
    max_value: float
    units: str = ""

    def knob_x(self, value: float) -> float:
        amount = (value - self.min_value) / (self.max_value - self.min_value)
        return self.x + max(0.0, min(1.0, amount)) * self.width

    def value_from_x(self, mouse_x: float) -> float:
        amount = (mouse_x - self.x) / self.width
        amount = max(0.0, min(1.0, amount))
        return self.min_value + amount * (self.max_value - self.min_value)

    def contains(self, x: float, y: float) -> bool:
        return self.x - 10 <= x <= self.x + self.width + 10 and self.y - 18 <= y <= self.y + 18


SLIDERS = {
    "frequency": Slider("frequency", "frequency", 318, 114, 360, 80, 880, "Hz"),
    "amplitude": Slider("amplitude", "amplitude", 318, 154, 360, 0.05, 1.0),
    "filter": Slider("filter", "filter cutoff", 318, 194, 360, 80, 4_000, "Hz"),
}


def setup() -> None:
    global AUDIO_CONTEXT
    gs.create_canvas(760, 500)
    AUDIO_CONTEXT = gs.get_audio_context()
    rebuild_audio(update_sound=True)


def rebuild_audio(*, update_sound: bool) -> None:
    """Regenerate analysis data, and optionally replace the playable sound."""

    global FILTERED, LEVEL, SAMPLES, SPECTRUM, SYNTH_SOUND
    analysis_oscillator = gs.create_oscillator(WAVEFORM, frequency=FREQUENCY, amplitude=AMPLITUDE)
    raw = analysis_oscillator.sample(0.08, sample_rate=8_000)
    shaped = gs.create_envelope(attack=0.015, decay=0.025, sustain=0.45, release=0.03).apply(
        raw, gate_duration=0.055
    )
    filtered = gs.create_filter("lowpass", frequency=FILTER_CUTOFF).process(shaped)

    # AudioInput is useful for deterministic tests and audio-reactive sketches.
    audio_in = gs.create_capture("audio")
    assert isinstance(audio_in, gs.AudioInput)
    audio_in.push_samples(filtered.samples)

    SAMPLES = raw.samples[:192]
    FILTERED = audio_in.read(192).samples
    LEVEL = gs.create_amplitude(filtered).analyze()
    SPECTRUM = gs.create_fft(filtered, bins=32).analyze()

    if not update_sound:
        return

    if SYNTH_SOUND is not None:
        SYNTH_SOUND.stop()
    playback_oscillator = gs.create_oscillator(WAVEFORM, frequency=FREQUENCY, amplitude=AMPLITUDE)
    playback_raw = playback_oscillator.sample(1.25, sample_rate=44_100)
    playback_shaped = gs.create_envelope(attack=0.02, decay=0.05, sustain=0.82, release=0.15).apply(
        playback_raw, gate_duration=1.08
    )
    playback_filtered = gs.create_filter("lowpass", frequency=FILTER_CUTOFF).process(
        playback_shaped
    )
    SYNTH_SOUND = playback_filtered.to_sound("filtered-synth.wav")
    if PLAY_AUDIO:
        play_current_sound()


def play_current_sound() -> None:
    global PLAYBACK_STATUS
    if SYNTH_SOUND is None:
        return
    try:
        SYNTH_SOUND.play()
    except gs.BackendCapabilityError as exc:
        PLAYBACK_STATUS = f"playback unavailable: {exc}"
        return
    PLAYBACK_STATUS = "playing the filtered 1.25s sawtooth oscillator through the platform player"


def stop_current_sound() -> None:
    global PLAYBACK_STATUS
    if SYNTH_SOUND is not None:
        SYNTH_SOUND.stop()
    PLAYBACK_STATUS = "playback stopped"


def draw_waveform(
    samples: tuple[float, ...], x: float, y: float, width: float, height: float
) -> None:
    if len(samples) < 2:
        return
    gs.no_fill()
    gs.stroke(80, 160, 255)
    previous_x = x
    previous_y = y + height / 2 - samples[0] * height * 0.45
    for index, sample in enumerate(samples[1:], start=1):
        px = x + index / (len(samples) - 1) * width
        py = y + height / 2 - sample * height * 0.45
        gs.line(previous_x, previous_y, px, py)
        previous_x, previous_y = px, py


def draw_spectrum(
    values: tuple[float, ...], x: float, y: float, width: float, height: float
) -> None:
    if not values:
        return
    bar_width = width / len(values)
    gs.no_stroke()
    for index, value in enumerate(values):
        amount = max(0.0, min(1.0, value))
        gs.fill(255, 118 + index * 3, 75)
        gs.rect(x + index * bar_width, y + height * (1 - amount), bar_width * 0.75, height * amount)


def draw_checkbox() -> None:
    gs.stroke(165, 180, 210)
    gs.no_fill()
    gs.rect(CHECKBOX_X, CHECKBOX_Y, CHECKBOX_SIZE, CHECKBOX_SIZE)
    if PLAY_AUDIO:
        gs.stroke(120, 255, 165)
        gs.line(CHECKBOX_X + 5, CHECKBOX_Y + 12, CHECKBOX_X + 10, CHECKBOX_Y + 18)
        gs.line(CHECKBOX_X + 10, CHECKBOX_Y + 18, CHECKBOX_X + 18, CHECKBOX_Y + 5)
    gs.no_stroke()
    gs.fill(235)
    gs.text("play filtered synth tone", CHECKBOX_X + 34, CHECKBOX_Y + 16)


def draw_slider(slider: Slider, value: float) -> None:
    knob_x = slider.knob_x(value)
    formatted = f"{value:.0f} {slider.units}" if slider.units else f"{value:.2f}"
    gs.no_stroke()
    gs.fill(230)
    gs.text(f"{slider.label}: {formatted}", slider.x, slider.y - 13)
    gs.stroke(85, 100, 135)
    gs.line(slider.x, slider.y, slider.x + slider.width, slider.y)
    gs.stroke(110, 205, 255)
    gs.line(slider.x, slider.y, knob_x, slider.y)
    gs.no_stroke()
    gs.fill(110, 205, 255)
    gs.circle(knob_x, slider.y, 14)


def draw_controls() -> None:
    draw_checkbox()
    draw_slider(SLIDERS["frequency"], FREQUENCY)
    draw_slider(SLIDERS["amplitude"], AMPLITUDE)
    draw_slider(SLIDERS["filter"], FILTER_CUTOFF)
    gs.no_stroke()
    gs.fill(170, 180, 205)
    gs.text(PLAYBACK_STATUS, 32, 154)
    gs.text(
        "Sawtooth harmonics make the low-pass filter audible; release sliders to restart.", 32, 178
    )


def draw() -> None:
    gs.background(17, 22, 34)
    gs.fill(245)
    gs.no_stroke()
    gs.text_size(22)
    gs.text("Audio analysis + synthesis", 32, 40)
    gs.text_size(14)
    gs.text(
        f"backend: {AUDIO_CONTEXT.get('backend')} | analysis: {AUDIO_CONTEXT.get('analysis')} | "
        f"synthesis: {AUDIO_CONTEXT.get('synthesis')} | playback: {AUDIO_CONTEXT.get('playback')}",
        32,
        68,
    )
    gs.text(f"RMS amplitude: {LEVEL:.3f}", 32, 92)
    draw_controls()

    gs.stroke(70, 78, 95)
    gs.no_fill()
    gs.rect(32, 228, 300, 120)
    gs.rect(384, 228, 300, 120)
    draw_waveform(SAMPLES, 40, 236, 284, 104)
    draw_waveform(FILTERED, 392, 236, 284, 104)

    gs.no_stroke()
    gs.fill(210)
    gs.text(f"raw {WAVEFORM} oscillator", 32, 374)
    gs.text("enveloped + filtered input", 384, 374)

    draw_spectrum(SPECTRUM, 32, 410, 652, 48)
    gs.fill(180)
    gs.text("FFT bins", 32, 486)

    save_once(ARGS, gs.frame_count(), gs.save_canvas)


def point_in_checkbox(x: float, y: float) -> bool:
    return (
        CHECKBOX_X <= x <= CHECKBOX_X + CHECKBOX_SIZE
        and CHECKBOX_Y <= y <= CHECKBOX_Y + CHECKBOX_SIZE
    )


def set_slider_value(slider_key: str, mouse_x: float, *, update_sound: bool) -> None:
    global AMPLITUDE, FILTER_CUTOFF, FREQUENCY
    slider = SLIDERS[slider_key]
    value = slider.value_from_x(mouse_x)
    if slider_key == "frequency":
        FREQUENCY = value
    elif slider_key == "amplitude":
        AMPLITUDE = value
    else:
        FILTER_CUTOFF = value
    rebuild_audio(update_sound=update_sound)


def mouse_pressed(event) -> None:
    global ACTIVE_SLIDER, PLAY_AUDIO
    if point_in_checkbox(event.x, event.y):
        PLAY_AUDIO = not PLAY_AUDIO
        if PLAY_AUDIO:
            rebuild_audio(update_sound=True)
        else:
            stop_current_sound()
        return

    for key, slider in SLIDERS.items():
        if slider.contains(event.x, event.y):
            ACTIVE_SLIDER = key
            set_slider_value(key, event.x, update_sound=False)
            return


def mouse_dragged(event) -> None:
    if ACTIVE_SLIDER is not None:
        set_slider_value(ACTIVE_SLIDER, event.x, update_sound=False)


def mouse_released(event) -> None:
    global ACTIVE_SLIDER
    if ACTIVE_SLIDER is not None:
        set_slider_value(ACTIVE_SLIDER, event.x, update_sound=True)
        ACTIVE_SLIDER = None


if __name__ == "__main__":
    gs.run(
        setup=setup,
        draw=draw,
        mouse_pressed=mouse_pressed,
        mouse_dragged=mouse_dragged,
        mouse_released=mouse_released,
        headless=ARGS.headless,
        max_frames=ARGS.frames,
    )
