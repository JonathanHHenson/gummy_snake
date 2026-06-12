"""p5.js-style camelCase aliases."""

from p5_py.api.global_mode import (
    angle_mode,
    apply_matrix,
    begin_shape,
    bezier_point,
    bezier_tangent,
    bezier_vertex,
    color_mode,
    create_canvas,
    delta_time,
    ellipse_mode,
    end_shape,
    frame_count,
    frame_rate,
    is_looping,
    key_is_down,
    lerp_color,
    load_pixels,
    mouse_x,
    mouse_y,
    no_fill,
    no_loop,
    no_stroke,
    pmouse_x,
    pmouse_y,
    quadratic_vertex,
    rect_mode,
    reset_matrix,
    resize_canvas,
    save_canvas,
    shear_x,
    shear_y,
    stroke_weight,
    update_pixels,
)

createCanvas = create_canvas
resizeCanvas = resize_canvas
colorMode = color_mode
lerpColor = lerp_color
noFill = no_fill
noStroke = no_stroke
strokeWeight = stroke_weight
ellipseMode = ellipse_mode
rectMode = rect_mode
beginShape = begin_shape
endShape = end_shape
bezierVertex = bezier_vertex
quadraticVertex = quadratic_vertex
shearX = shear_x
shearY = shear_y
applyMatrix = apply_matrix
resetMatrix = reset_matrix
angleMode = angle_mode
frameRate = frame_rate
frameCount = frame_count
deltaTime = delta_time
noLoop = no_loop
isLooping = is_looping
keyIsDown = key_is_down
mouseX = mouse_x
mouseY = mouse_y
pmouseX = pmouse_x
pmouseY = pmouse_y
loadPixels = load_pixels
updatePixels = update_pixels
saveCanvas = save_canvas
bezierPoint = bezier_point
bezierTangent = bezier_tangent

__all__ = [
    "createCanvas",
    "resizeCanvas",
    "colorMode",
    "lerpColor",
    "noFill",
    "noStroke",
    "strokeWeight",
    "ellipseMode",
    "rectMode",
    "beginShape",
    "endShape",
    "bezierVertex",
    "quadraticVertex",
    "shearX",
    "shearY",
    "applyMatrix",
    "resetMatrix",
    "angleMode",
    "frameRate",
    "frameCount",
    "deltaTime",
    "noLoop",
    "isLooping",
    "keyIsDown",
    "mouseX",
    "mouseY",
    "pmouseX",
    "pmouseY",
    "loadPixels",
    "updatePixels",
    "saveCanvas",
    "bezierPoint",
    "bezierTangent",
]
