# pyright: reportUnboundVariable=false
# pyright: reportUnsupportedDunderAll=false
# pyright: reportUndefinedVariable=false, reportPossiblyUnboundVariable=false
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportAssignmentType=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false
# pyright: reportInvalidTypeForm=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalSubscript=false
# pyright: reportRedeclaration=false, reportReturnType=false
def range(start: float, stop: float | None = None, *, step: float = 1.0) -> Ring:  # noqa: A001
    """Create a numeric ring.

    This mirrors Sonic Pi's ``range`` constructor while keeping Python keyword
    style. ``stop`` is exclusive.
    """

    if stop is None:
        start, stop = 0.0, start
    if step == 0:
        raise ArgumentValidationError("range step cannot be zero.")
    values: list[float] = []
    current = float(start)
    end = float(stop)
    if step > 0:
        while current < end:
            values.append(current)
            current += step
    else:
        while current > end:
            values.append(current)
            current += step
    return Ring(values)


def line(start: float, stop: float, *, steps: int) -> Ring:
    """Create a ring of linearly interpolated values including both endpoints."""

    if steps <= 0:
        raise ArgumentValidationError("line steps must be positive.")
    if steps == 1:
        return Ring([float(start)])
    return Ring(start + (stop - start) * index / (steps - 1) for index in builtins.range(steps))


def bools(*values: int | bool) -> Ring:
    """Create a ring of booleans from truthy/falsy values."""

    return Ring(bool(value) for value in values)


def knit(*pairs: object) -> Ring:
    """Create a ring by repeating value/count pairs."""

    if len(pairs) % 2 != 0:
        raise ArgumentValidationError("knit() requires value/count pairs.")
    output: list[object] = []
    iterator = iter(pairs)
    for value, count in zip(iterator, iterator, strict=True):
        output.extend(value for _ in builtins.range(max(0, int(cast(Any, count)))))
    return Ring(output)


def spread(pulses: int, steps: int) -> Ring:
    """Create a Euclidean rhythm as a boolean ring."""

    if steps <= 0:
        raise ArgumentValidationError("spread steps must be positive.")
    pulses = max(0, min(int(pulses), int(steps)))
    return Ring(((index * pulses) % steps) < pulses for index in builtins.range(steps))


def octs(root: object, count: int) -> Ring | Expression:
    """Return octaves above ``root`` as MIDI note values."""

    if isinstance(root, Expression):
        return MusicExpression("octs", root, count=ensure_expr(count))
    return _octaves_from_root(root, count)


def tick(name: str | None = None) -> Expression:
    """Advance a named logical tick counter and return its index."""

    return TickExpression(None, name or "default", True)


def look(name: str | None = None) -> Expression:
    """Read a named logical tick counter without advancing it."""

    return TickExpression(None, name or "default", False)


def choose(values: object) -> Expression:
    """Choose a random value from a sequence at physical-plan/render time."""

    return _source_bound_expression(ChoiceExpression(ensure_expr(values)))


def rand(max_value: float = 1.0) -> Expression:
    """Return a lazy random float in ``[0, max_value)``."""

    return _source_bound_expression(RandomExpression("rand", (ensure_expr(max_value),)))


def rand_i(max_value: int) -> Expression:
    """Return a lazy random integer in ``[0, max_value)``."""

    return _source_bound_expression(RandomExpression("rand_i", (ensure_expr(max_value),)))


def rrand(low: float, high: float) -> Expression:
    """Return a lazy random float between two values."""

    return _source_bound_expression(
        RandomExpression("rrand", (ensure_expr(low), ensure_expr(high)))
    )


def rrand_i(low: int, high: int) -> Expression:
    """Return a lazy random integer between two inclusive bounds."""

    return _source_bound_expression(
        RandomExpression("rrand_i", (ensure_expr(low), ensure_expr(high)))
    )


def dice(sides: int = 6) -> Expression:
    """Return a lazy dice roll in ``1..sides``."""

    return _source_bound_expression(RandomExpression("dice", (ensure_expr(sides),)))


def one_in(sides: int) -> Expression:
    """Return a lazy boolean that is true with probability ``1 / sides``."""

    return _source_bound_expression(RandomExpression("one_in", (ensure_expr(sides),)))


_NOTE_OFFSETS = {
    "c": 0,
    "cs": 1,
    "c#": 1,
    "db": 1,
    "d": 2,
    "ds": 3,
    "d#": 3,
    "eb": 3,
    "e": 4,
    "f": 5,
    "fs": 6,
    "f#": 6,
    "gb": 6,
    "g": 7,
    "gs": 8,
    "g#": 8,
    "ab": 8,
    "a": 9,
    "as": 10,
    "a#": 10,
    "bb": 10,
    "b": 11,
}

_CHORD_INTERVALS = {
    "major": (0, 4, 7),
    "maj": (0, 4, 7),
    "M": (0, 4, 7),
    "minor": (0, 3, 7),
    "m": (0, 3, 7),
    "m7": (0, 3, 7, 10),
    "minor7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
    "major7": (0, 4, 7, 11),
    "dom7": (0, 4, 7, 10),
    "7": (0, 4, 7, 10),
    "dim": (0, 3, 6),
    "dim7": (0, 3, 6, 9),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "m9": (0, 3, 7, 10, 14),
    "m13": (0, 3, 7, 10, 14, 17, 21),
}

_SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "chromatic": tuple(builtins.range(12)),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}


def note(value: object) -> float | None:
    """Convert a note name or MIDI-like number to a MIDI note value.

    ``None``, ``"r"``, and ``"rest"`` represent rests and return ``None``.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return None if not value else 60.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower().removeprefix(":")
        if text in {"r", "rest", "nil", "none", "false"}:
            return None
        if not text:
            raise ArgumentValidationError("Empty note name.")
        root = text[0]
        rest = text[1:]
        accidental = ""
        if rest.startswith(("#", "s", "b")):
            accidental = "#" if rest[0] in {"#", "s"} else "b"
            rest = rest[1:]
        name = root + accidental
        if name not in _NOTE_OFFSETS:
            raise ArgumentValidationError(f"Unsupported note name: {value!r}.")
        octave = int(rest) if rest else 4
        return float((octave + 1) * 12 + _NOTE_OFFSETS[name])
    raise ArgumentValidationError(f"Unsupported note value: {value!r}.")


def note_frequency(value: object) -> float:
    """Convert a note value to Hertz."""

    midi = note(value)
    if midi is None:
        return 0.0
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


@overload
def chord(root: Expression, name: str = "major") -> Expression: ...


@overload
def chord(root: str | int | float | None, name: str = "major") -> Ring: ...


def chord(root: object, name: str = "major") -> Ring | Expression:
    """Return a chord ring, or a lazy chord expression when ``root`` is lazy."""

    if isinstance(root, Expression):
        return MusicExpression("chord", root, name)
    return _chord_from_root(root, name)


@overload
def scale(root: Expression, name: str = "major", *, num_octaves: int = 1) -> Expression: ...


@overload
def scale(root: str | int | float | None, name: str = "major", *, num_octaves: int = 1) -> Ring: ...
