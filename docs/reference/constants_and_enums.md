# Constants and Enums

p5-py exposes p5-style uppercase names such as `p5.CENTER`, `p5.WEBGL`, and `p5.BLEND` as enum members rather than untyped string or integer constants.

The enum classes are also public for type annotations and introspection:

| Enum | Public values |
| --- | --- |
| `ShapeMode` | `CORNER`, `CORNERS`, `CENTER`, `RADIUS` |
| `ArcMode` | `OPEN`, `CLOSE`, `CHORD`, `PIE` |
| `ShapeKind` | `POINTS`, `LINES`, `TRIANGLES`, `TRIANGLE_STRIP`, `TRIANGLE_FAN`, `QUADS`, `QUAD_STRIP` |
| `AngleMode` | `RADIANS`, `DEGREES` |
| `ColorMode` | `RGB`, `HSB`, `HSL` |
| `StrokeCap` | `ROUND`, `SQUARE`, `PROJECT` |
| `StrokeJoin` | `MITER`, `BEVEL`, `ROUND` |
| `TextAlign` | `LEFT`, `RIGHT`, `CENTER`, `TOP`, `BOTTOM`, `BASELINE` |
| `TextStyle` | `NORMAL`, `ITALIC`, `BOLD`, `BOLDITALIC` |
| `RendererMode` | `P2D`, `WEBGL` |
| `BlendMode` | `BLEND`, `ADD`, `DARKEST`, `LIGHTEST`, `DIFFERENCE`, `EXCLUSION`, `MULTIPLY`, `SCREEN`, `REPLACE` |
| `ImageSampling` | `LINEAR`, `NEAREST` |
| `ImageFilter` | `THRESHOLD`, `GRAY`, `INVERT`, `BLUR`, `POSTERIZE`, `ERODE`, `DILATE` |
| `MouseButton` | `LEFT`, `CENTER`, `RIGHT` |
| `KeyCode` | `BACKSPACE`, `TAB`, `ENTER`, `ESCAPE`, `SHIFT`, `CONTROL`, `ALT`, `UP_ARROW`, `DOWN_ARROW`, `LEFT_ARROW`, `RIGHT_ARROW` |
| `TouchEventName` | `TOUCH_STARTED`, `TOUCH_MOVED`, `TOUCH_ENDED` |
| `CompatibilityStatus` | `SUPPORTED`, `PARTIAL`, `DEFERRED`, `EXCLUDED` |

Example:

```python
import p5

p5.create_canvas(640, 480, renderer=p5.WEBGL)
p5.rect_mode(p5.CENTER)
p5.blend_mode(p5.MULTIPLY)
```

For code that needs type annotations, prefer the enum classes:

```python
def set_renderer(renderer: p5.RendererMode = p5.P2D) -> None:
    p5.create_canvas(400, 400, renderer=renderer)
```

Most enum classes are string-valued enums, so public p5 names remain readable when displayed or passed through backend payloads. `KeyCode` is integer-valued to preserve p5-style keyboard code semantics.

Plugin hook names (`LifecycleHookName`, `EventHookName`) and renderer-internal 3D light kinds (`LightKind`) are also enums in their implementation modules for plugin and renderer authors.
