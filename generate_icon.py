#!/usr/bin/env python3
"""Generate DeepSeek Monitor app icon - all shapes, no text rendering.

Usage: python3 generate_icon.py [output_dir]
Output: iconset folder + ICNS file
"""

import os, sys
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
OUT_BASE = sys.argv[1] if len(sys.argv) > 1 else "."
ICONSET_DIR = os.path.join(OUT_BASE, "ds_icon.iconset")
ICNS_OUT = os.path.join(OUT_BASE, "ds_icon.icns")
os.makedirs(ICONSET_DIR, exist_ok=True)

BG_START = (10, 40, 80)
BG_END   = (20, 100, 180)
TEXT_COLOR = (255, 255, 255, 255)
ACCENT = (100, 210, 255)
DARK_ACCENT = (10, 40, 70, 255)

def draw_ds_shape(draw, cx, cy, size, color):
    """Draw stylized 'DS' as geometric shapes for very small icons."""
    unit = size / 100.0
    lw = max(1, int(unit * 14))
    dx, dy = cx - size * 0.18, cy
    dh = size * 0.32
    dw = size * 0.14
    draw.rectangle([dx - lw//2, dy - dh, dx + lw//2, dy + dh], fill=color)
    bbox = [dx, dy - dh, dx + dw * 2, dy + dh]
    draw.arc(bbox, -90, 90, fill=color, width=lw)
    sx, sy = cx + size * 0.18, cy
    sh = size * 0.30
    sw = size * 0.12
    draw.rectangle([sx - sw//2, sy - sh, sx + sw//2, sy - sh + lw], fill=color)
    draw.rectangle([sx - sw//2, sy - lw//2, sx + sw//2, sy + lw//2], fill=color)
    draw.rectangle([sx - sw//2, sy + sh - lw, sx + sw//2, sy + sh], fill=color)
    draw.rectangle([sx - lw//2, sy - sh, sx + lw//2, sy - sh + lw], fill=color)
    draw.rectangle([sx - lw//2, sy - lw//2, sx + lw//2, sy + lw//2], fill=color)
    draw.rectangle([sx - lw//2, sy + sh - lw, sx + lw//2, sy + sh], fill=color)

def draw_ds_text(draw, cx, cy, size, color):
    """Draw 'DS' using PIL text if possible, fall back to shapes."""
    font_size = int(size * 0.55)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
        text = "DS"
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = font_size * 1.3, font_size
        draw.text((cx - tw/2, cy - th/2 - size * 0.02), text, fill=color, font=font)
    except Exception:
        draw_ds_shape(draw, cx, cy, size, color)

def draw_yen_badge(draw, cx, cy, size):
    """Draw ¥ badge using simple shapes."""
    unit = size / 100.0
    lw = max(1, int(unit * 5))
    r = size * 0.42
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT + (220,))
    yh, yw = size * 0.22, size * 0.14
    top_y, bot_y = cy - yh * 0.3, cy + yh * 0.7
    draw.line([cx - yw, top_y, cx, cy + yh * 0.1], fill=DARK_ACCENT, width=lw)
    draw.line([cx + yw, top_y, cx, cy + yh * 0.1], fill=DARK_ACCENT, width=lw)
    draw.line([cx, cy + yh * 0.1, cx, bot_y], fill=DARK_ACCENT, width=lw)
    bar_w = yw * 0.8
    draw.line([cx - bar_w, top_y - yh * 0.1, cx + bar_w, top_y - yh * 0.1], fill=DARK_ACCENT, width=lw)
    draw.line([cx - bar_w, top_y + yh * 0.05, cx + bar_w, top_y + yh * 0.05], fill=DARK_ACCENT, width=lw)

def create_icon(size):
    """Create a single icon image at given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = int(size * 0.08)
    corner = int(size * 0.22)
    steps = size // 2
    for i in range(steps):
        r = int(BG_START[0] + (BG_END[0] - BG_START[0]) * i / steps)
        g = int(BG_START[1] + (BG_END[1] - BG_START[1]) * i / steps)
        b = int(BG_START[2] + (BG_END[2] - BG_START[2]) * i / steps)
        radius = max(0, corner - int(i * 0.5))
        draw.rounded_rectangle(
            [margin + int(i * 0.5), margin + int(i * 0.5),
             size - margin - int(i * 0.5), size - margin - int(i * 0.5)],
            radius=radius, fill=(r, g, b, 255))
    cx, cy = size / 2, size / 2
    if size >= 64:
        draw_ds_text(draw, cx, cy, size, TEXT_COLOR)
    else:
        draw_ds_shape(draw, cx, cy, size, TEXT_COLOR)
    badge_cx = size - margin - size * 0.11
    badge_cy = size - margin - size * 0.11
    draw_yen_badge(draw, badge_cx, badge_cy, size * 0.18)
    return img

if __name__ == "__main__":
    sizes = [
        (16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
        (128, "128x128"), (256, "128x128@2x"), (256, "256x256"), (512, "256x256@2x"),
        (512, "512x512"), (1024, "512x512@2x"),
    ]
    for px, label in sizes:
        img = create_icon(px)
        path = os.path.join(ICONSET_DIR, f"icon_{label}.png")
        img.save(path)
        print(f"  {label} ({px:4d}x{px:<4d}) done")
    print(f"\n{len(sizes)} icons -> {ICONSET_DIR}")
    print(f"Run: iconutil -c icns {ICONSET_DIR} -o {ICNS_OUT}")
