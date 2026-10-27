# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Draws docs/media/icon.svg and icon.png: a grid of tables, a gate, and the few that pass.

    python docs/media/make_icon.py        (needs Pillow for the PNG)
"""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SIZE = 512
BG, DIM, LIT, GATE = "#0F7B6C", "#3E9A8D", "#FFFFFF", "#F2C14E"

# 5 x 5 grid of tables on the left; the selection is three of them, carried through the gate
CELL, GAP, X0, Y0 = 44, 14, 56, 104
PICKED = {(0, 1), (2, 3), (3, 0)}
GATE_X = X0 + 5 * (CELL + GAP) + 10


def shapes():
    out = [("rect", 0, 0, SIZE, SIZE, 96, BG)]
    for r in range(5):
        for c in range(5):
            x, y = X0 + c * (CELL + GAP), Y0 + r * (CELL + GAP)
            out.append(("rect", x, y, CELL, CELL, 8, LIT if (r, c) in PICKED else DIM))
    out.append(("rect", GATE_X, Y0 - 24, 16, 5 * (CELL + GAP) - GAP + 48, 8, GATE))
    for i in range(len(PICKED)):
        out.append(("rect", GATE_X + 44, Y0 + 30 + i * 96, CELL + 30, CELL, 8, LIT))
    return out


def svg():
    body = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{f}"/>'
                   for _, x, y, w, h, rx, f in shapes())
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">{body}</svg>\n'


def png(path):
    from PIL import Image, ImageDraw
    scale = 2                                  # draw large, shrink: smooth corners
    img = Image.new("RGBA", (SIZE * scale, SIZE * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _, x, y, w, h, rx, f in shapes():
        d.rounded_rectangle([x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1], rx * scale, fill=f)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(path)


(HERE / "icon.svg").write_text(svg(), "utf-8")
png(HERE / "icon.png")
print("wrote icon.svg, icon.png")
