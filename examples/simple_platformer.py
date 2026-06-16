from dataclasses import dataclass

import p5


def cut_strip(image: p5.Image, num_sprites: int) -> list[p5.Image]:
    sprite_width = image.width // num_sprites

    sprites = [
        image.get(i * sprite_width, 0, sprite_width, image.height) for i in range(num_sprites)
    ]

    return sprites  # pyright: ignore[reportReturnType]


@dataclass
class Animation:
    sprites: list[p5.Image]
    fps: int
    index: int = 0
    timer: float = 0

    def update(self):
        interval = 1000 / self.fps
        self.timer += p5.delta_time()
        if self.timer >= interval:
            self.timer %= interval
            self.index = (self.index + 1) % len(self.sprites)

    def draw(self, x: float, y: float, w: float, h: float):
        sprite = self.sprites[self.index]
        p5.image(sprite, x, y, w, h)


@dataclass
class Entity:
    diameter: float
    x: float
    y: float
    dx: float = 0.0
    dy: float = 0.0

    def update(self):
        self.x += self.dx
        self.y += self.dy


@dataclass
class Platform:
    x: float
    y: float
    w: float
    h: float


class Hero:
    move_speed: float = 5
    gravity: float = 1.5
    jump_speed: float = 18

    def __init__(self, x: float, y: float) -> None:
        self.facing_left = False
        self.on_ground = False
        self.status = "idle"
        self.entity = Entity(50, x, y)
        _idle_strip = p5.load_image("examples/assets/herochar/herochar_idle_anim_strip_4.png")
        running_strip = p5.load_image("examples/assets/herochar/herochar_run_anim_strip_6.png")
        self._idle_animation = cut_strip(_idle_strip, 4)
        self._running_animation = cut_strip(running_strip, 6)
        self.animation = Animation(self._idle_animation, 7)

    def update(self, platforms: list[Platform]):
        if p5.keyIsDown(key_code=ord("a")):
            self.entity.dx = -self.move_speed
            self.facing_left = True
        elif p5.keyIsDown(key_code=ord("d")):
            self.entity.dx = self.move_speed
            self.facing_left = False
        else:
            self.entity.dx = 0

        if (p5.keyIsDown(key_code=ord("w")) or p5.keyIsDown(key_code=ord(" "))) and self.on_ground:
            self.entity.dy = -self.jump_speed
            self.on_ground = False

        radius = self.entity.diameter / 2
        old_bottom = self.entity.y + radius

        self.entity.x += self.entity.dx
        self.entity.dy += self.gravity
        self.entity.y += self.entity.dy

        self.on_ground = False
        new_bottom = self.entity.y + radius

        for platform in platforms:
            horizontal_overlap = (
                self.entity.x + radius > platform.x
                and self.entity.x - radius < platform.x + platform.w
            )
            is_falling_onto_platform = (
                self.entity.dy >= 0 and old_bottom <= platform.y and new_bottom >= platform.y
            )

            if horizontal_overlap and is_falling_onto_platform:
                self.entity.y = platform.y - radius
                self.entity.dy = 0
                self.on_ground = True
                break

        next_status = "running" if self.entity.dx != 0 else "idle"

        if self.status != next_status:
            self.status = next_status
            if self.status == "running":
                self.animation = Animation(self._running_animation, 7)
            elif self.status == "idle":
                self.animation = Animation(self._idle_animation, 7)

        self.animation.update()

    def draw(self):
        with p5.pushed():
            p5.no_smooth()
            p5.imageMode(p5.CENTER)
            if self.facing_left:
                p5.translate(self.entity.x, self.entity.y)
                p5.scale(-1, 1)
                self.animation.draw(0, 0, self.entity.diameter, self.entity.diameter)
            else:
                self.animation.draw(
                    self.entity.x,
                    self.entity.y,
                    self.entity.diameter,
                    self.entity.diameter,
                )


width = 1200
height = 800
hero = Hero(600, 400)
platforms = [
    Platform(250, 650, 700, 40),
]


def setup():
    p5.create_canvas(width, height)


def update():
    hero.update(platforms)


def draw_platforms():
    with p5.pushed():
        p5.fill(90, 90, 90)
        p5.no_stroke()
        for platform in platforms:
            p5.rect(platform.x, platform.y, platform.w, platform.h)


def draw():
    update()

    p5.background(0)
    draw_platforms()
    hero.draw()


def main():
    p5.run(setup=setup, draw=draw)


if __name__ == "__main__":
    main()
