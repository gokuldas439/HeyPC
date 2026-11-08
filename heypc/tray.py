"""The system tray icon, which replaces the console window."""
import os

import pystray
from PIL import Image, ImageDraw


def draw_icon(size: int = 256) -> Image.Image:
    """A glowing ring."""
    scale = 4
    full = size * scale
    image = Image.new("RGBA", (full, full), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    centre = full / 2

    def ring(radius: float, width: float, colour) -> None:
        box = (centre - radius, centre - radius, centre + radius, centre + radius)
        draw.ellipse(box, outline=colour, width=int(width))

    def disc(radius: float, colour) -> None:
        draw.ellipse((centre - radius, centre - radius, centre + radius, centre + radius), fill=colour)

    disc(full * 0.5, (11, 18, 32, 255))
    ring(full * 0.44, full * 0.07, (79, 209, 255, 255))
    ring(full * 0.27, full * 0.04, (79, 209, 255, 170))
    disc(full * 0.15, (190, 240, 255, 255))
    return image.resize((size, size), Image.LANCZOS)


def start_tray(jarvis, open_settings) -> pystray.Icon:
    def toggle_sleep(_icon, _item) -> None:
        jarvis.asleep = not jarvis.asleep

    menu = pystray.Menu(
        pystray.MenuItem("Settings", lambda _icon, _item: open_settings(), default=True),
        pystray.MenuItem("Asleep (ignore wake word)", toggle_sleep, checked=lambda _item: jarvis.asleep),
        pystray.MenuItem("Quit HeyPC", lambda _icon, _item: os._exit(0)),
    )
    icon = pystray.Icon("HeyPC", draw_icon(64), "HeyPC", menu)
    icon.run_detached()
    return icon
