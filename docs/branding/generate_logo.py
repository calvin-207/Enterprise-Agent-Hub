"""Generate Enterprise Agent Hub logo assets (PNG / ICO) with Pillow.

The geometry mirrors logo.svg (same master design):
  - rounded-square icon, 135deg gradient #2B4EE8 -> #52A0FF, subtle top-left highlight
  - white hub-and-spoke network: central hub node + 3 agent nodes (abstract "A")
  - governance orbit ring around the hub

Outputs (into docs/branding/):
  - logo-1024.png   master raster (transparent corners)
  - logo-64.png     small-size legibility check
  - favicon.ico     multi-size 16/24/32/48/64/128/256

Then copy/commit:
  - frontend/src/assets/lee/imgs/logo.png  <- logo-1024.png
  - frontend/public/logo.png              <- logo-1024.png
  - frontend/public/favicon.ico           <- favicon.ico

Usage:  python generate_logo.py
"""

import math
import os

from PIL import Image, ImageDraw

# --- master geometry (1024 design space, supersampled x4) --------------------

SCALE = 4
BASE = 1024 * SCALE

DEEP = (43, 78, 232)    # #2B4EE8
LIGHT = (82, 160, 255)  # #52A0FF
WHITE = (255, 255, 255)

CORNER_R = 236                       # rounded-square radius
HUB = (512, 565, 76)                 # cx, cy, r
RING_R, RING_W, RING_ALPHA = 112, 16, 115   # orbit ring (45% white)
SATELLITES = [                       # agent nodes
    (512, 310, 50),
    (291, 692, 50),
    (733, 692, 50),
]
SPOKE_W = 36


# --- helpers ------------------------------------------------------------------

def diagonal_mask(size: int) -> Image.Image:
    """135deg gradient mask: 0 at top-left -> 255 at bottom-right."""
    m = Image.new("L", (256, 256))
    px = m.load()
    for y in range(256):
        for x in range(256):
            px[x, y] = int((x + y) / 510 * 255)
    return m.resize((size, size), Image.BICUBIC)


def highlight_mask(size: int) -> Image.Image:
    """Soft radial highlight centred at ~(0.32, 0.26), max ~20% white."""
    m = Image.new("L", (256, 256))
    px = m.load()
    cx, cy, r = 256 * 0.32, 256 * 0.26, 256 * 0.75
    for y in range(256):
        for x in range(256):
            d = math.hypot(x - cx, y - cy) / r
            v = max(0.0, 1.0 - d) ** 1.6 * 0.20
            px[x, y] = int(v * 255)
    return m.resize((size, size), Image.BICUBIC)


def build_master() -> Image.Image:
    # gradient background
    img = Image.composite(
        Image.new("RGB", (BASE, BASE), LIGHT),
        Image.new("RGB", (BASE, BASE), DEEP),
        diagonal_mask(BASE),
    )
    # subtle highlight
    img = Image.composite(
        Image.new("RGB", (BASE, BASE), WHITE),
        img,
        highlight_mask(BASE),
    )

    # rounded corners -> RGBA with transparent outside
    corner = Image.new("L", (BASE, BASE), 0)
    ImageDraw.Draw(corner).rounded_rectangle(
        [0, 0, BASE - 1, BASE - 1], radius=CORNER_R * SCALE, fill=255
    )
    img = img.convert("RGBA")
    img.putalpha(corner)

    # emblem (separate layer, composited)
    ring = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    hx, hy, hr = HUB
    ImageDraw.Draw(ring).ellipse(
        [
            (hx - RING_R) * SCALE, (hy - RING_R) * SCALE,
            (hx + RING_R) * SCALE, (hy + RING_R) * SCALE,
        ],
        outline=WHITE + (RING_ALPHA,),
        width=RING_W * SCALE,
    )

    emb = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(emb)
    for sx, sy, _ in SATELLITES:
        d.line(
            [(hx * SCALE, hy * SCALE), (sx * SCALE, sy * SCALE)],
            fill=WHITE + (255,),
            width=SPOKE_W * SCALE,
        )
    for sx, sy, sr in SATELLITES:
        d.ellipse(
            [(sx - sr) * SCALE, (sy - sr) * SCALE, (sx + sr) * SCALE, (sy + sr) * SCALE],
            fill=WHITE + (255,),
        )
    d.ellipse(
        [(hx - hr) * SCALE, (hy - hr) * SCALE, (hx + hr) * SCALE, (hy + hr) * SCALE],
        fill=WHITE + (255,),
    )

    img = Image.alpha_composite(img, ring)
    img = Image.alpha_composite(img, emb)
    return img


# --- main ----------------------------------------------------------------------

def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    master = build_master()

    master.resize((1024, 1024), Image.LANCZOS).save(os.path.join(here, "logo-1024.png"))
    master.resize((64, 64), Image.LANCZOS).save(os.path.join(here, "logo-64.png"))

    # multi-size favicon from a 256 base
    fav = master.resize((256, 256), Image.LANCZOS)
    fav.save(
        os.path.join(here, "favicon.ico"),
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("assets written to", here)


if __name__ == "__main__":
    main()
