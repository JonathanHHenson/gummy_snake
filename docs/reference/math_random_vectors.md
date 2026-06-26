# Math, Random, and Vectors

## Math

- `map(value, start1, stop1, start2, stop2)`
- `map_value(value, start1, stop1, start2, stop2)`
- `constrain(value, min_value, max_value)`
- `norm(value, start, stop)`
- `lerp(start, stop, amount)`
- `dist(...)`
- `mag(...)`
- `radians(degrees)`
- `degrees(radians)`
- `sin(angle)`, `cos(angle)`, `tan(angle)`
- `asin(value)`, `acos(value)`, `atan(value)`, `atan2(y, x)`
- `sq(value)`, `fract(value)`

Use Python built-ins and the standard `math` module for simple numeric operations such as `abs`, `round`, `ceil`, `floor`, `sqrt`, `pow`, `exp`, and `log`.

## Random and Noise

- `random(high=None, low=None)`
- `random_seed(seed)`
- `random_gaussian(mean=0, sd=1)`
- `noise(...)`
- `noise_seed(seed)`
- `noise_detail(octaves, falloff=None)`

`random_seed(seed)` controls Gummy Snake's sketch RNG used by `random()` and
`random_gaussian()`; it does not mutate Python's standard-library `random`
module. Use `noise_seed(seed)` separately for deterministic noise.

## Vectors

- `create_vector(x=0, y=0, z=0)`
- `Vector`

Vectors support common arithmetic and geometry operations used by sketches.
They also implement Python data-model helpers:

```python
speed = abs(velocity)
direction = velocity.normalized()
projection = velocity @ normal
rounded = round(position, 2)
```

## Formatting and Conversion

Use Python-native formatting and conversion APIs such as `bool`, `int`, `float`, `str`, `chr`, `ord`, `hex`, f-strings, `format`, `str.split`, and `re.split`.
