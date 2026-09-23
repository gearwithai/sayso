"""Draws the tray / app icon (a microphone) in a colour per state. No image files needed."""
from PIL import Image, ImageDraw

COLORS = {
    "loading": "#5B8DEF",
    "ready": "#6E56CF",  # brand purple - visible on light and dark taskbars
    "listening": "#E5484D",
    "thinking": "#F5A524",
    "paused": "#9A9A9A",
    "error": "#E5484D",
}
BRAND = "#6E56CF"


def mic_icon(state: str = "ready", size: int = 64, bg: str | None = None) -> Image.Image:
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = bg or COLORS.get(state, COLORS["ready"])
    d.ellipse([0, 0, size - 1, size - 1], fill=fill)
    w = "white"
    # capsule
    d.rounded_rectangle([24 * s, 12 * s, 40 * s, 38 * s], radius=8 * s, fill=w)
    # cradle
    d.arc([17 * s, 20 * s, 47 * s, 46 * s], start=0, end=180, fill=w, width=max(1, round(3 * s)))
    # stand
    d.line([32 * s, 46 * s, 32 * s, 52 * s], fill=w, width=max(1, round(3 * s)))
    d.line([25 * s, 52 * s, 39 * s, 52 * s], fill=w, width=max(1, round(3 * s)))
    if state == "paused":
        d.line([14 * s, 14 * s, 50 * s, 50 * s], fill=w, width=max(2, round(4 * s)))
    if state == "error":
        d.ellipse([44 * s, 4 * s, 60 * s, 20 * s], fill="#FFD60A")
    return img


def save_app_icon(path: str) -> None:
    """Multi-size .ico for the .exe and installer."""
    big = mic_icon(bg=BRAND, size=256)
    big.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    import sys
    save_app_icon(sys.argv[1] if len(sys.argv) > 1 else "sayso.ico")
