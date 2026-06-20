# Constants and Enums

Gummy Snake exposes Gummy Snake-style uppercase names such as `gs.CENTER`, `gs.WEBGL`, and `gs.BLEND` as enum members rather than untyped string or integer constants.

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
| `CallbackEventName` | `MOUSE_MOVED`, `MOUSE_DRAGGED`, `MOUSE_PRESSED`, `MOUSE_RELEASED`, `MOUSE_CLICKED`, `MOUSE_DOUBLE_CLICKED`, `MOUSE_WHEEL`, `KEY_PRESSED`, `KEY_RELEASED`, `KEY_TYPED`, `TOUCH_STARTED`, `TOUCH_MOVED`, `TOUCH_ENDED`, `TOUCH_CANCELLED` |

Example:

```python
import gummysnake as gs

gs.create_canvas(640, 480, renderer=gs.WEBGL)
gs.rect_mode(gs.CENTER)
gs.blend_mode(gs.MULTIPLY)
```

Event decorators accept either callback-name strings or enum members:

```python
@gs.on(gs.KEY_PRESSED)
def handle_key(event) -> None:
    ...
```

For code that needs type annotations, prefer the enum classes:

```python
def set_renderer(renderer: gs.RendererMode = gs.P2D) -> None:
    gs.create_canvas(400, 400, renderer=renderer)
```

Most enum classes are string-valued enums, so public Gummy Snake names remain readable when displayed or passed through backend payloads. `KeyCode` is integer-valued to preserve Gummy Snake-style keyboard code semantics.

Plugin hook names (`LifecycleHookName`, `EventHookName`) and renderer-internal 3D light kinds (`LightKind`) are also enums in their implementation modules for plugin and renderer authors.
