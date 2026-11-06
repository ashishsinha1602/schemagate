# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""Draws docs/media/token-savings.gif: one question, the whole schema vs what schemagate sends.

    python docs/media/make_token_gif.py        (needs Pillow and tiktoken)

Every number in the picture is measured when this runs, the same way as
benchmarks/token_savings/measure.py: tiktoken's cl100k_base over every table's
full DDL, against ``Catalog.select(question)``. The schema is the seeded
1,201-object fixture from benchmarks/fixture_1200.py, so anyone gets the same
picture.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "benchmarks")]

import fixture_1200 as fx  # noqa: E402
import tiktoken  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from schemagate import Catalog, Column, ObjectDoc  # noqa: E402
from schemagate.catalog import ForeignKey  # noqa: E402

QUESTION = "payments received against invoices per contact"
NEEDED = {"bill_invoice", "bill_payment", "crm_contact"}
TOP_K = 12
W, H = 960, 440
BG, PANEL, INK, DIM, TEAL, GOLD, RED = "#0B1F1C", "#12302B", "#F4F7F6", "#8FB3AC", "#3CC4AC", "#F2C14E", "#E46A5E"


def measure():
    enc = tiktoken.get_encoding("cl100k_base")
    cat = Catalog(name="fixture_1200")
    for name, kind, desc, cols in fx.build_spec():
        doc = ObjectDoc(name=name, schema="app", kind=kind, description=desc,
                        columns=[Column(c, t, True, None, c == "id") for c, t in cols])
        if name in fx.FOREIGN_KEYS:
            col, ref = fx.FOREIGN_KEYS[name][:2]
            doc.foreign_keys.append(ForeignKey(columns=[col], ref_table=ref, ref_columns=["id"]))
        cat.add(doc)
    cat.index()
    full = len(enc.encode("\n\n".join(d.render_ddl(max_columns=10**6) for d in cat._docs.values())))
    sel = cat.select(QUESTION, top_k=TOP_K)
    got = {n.split(".")[-1] for n in sel.table_names}
    assert NEEDED <= got, f"selection lost a needed table: {sorted(NEEDED - got)}"
    return len(cat._docs), full, len(got), len(enc.encode(sel.prompt_fragment()))


def font(size, bold=False):
    names = (["consolab.ttf", "DejaVuSansMono-Bold.ttf", "Menlo-Bold.ttf"] if bold
             else ["consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def frame(objects, full, sent, picked, shown_full, shown_sel, verdict):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((40, 30), "Same question, two prompts", font=font(30, True), fill=INK)
    d.text((40, 76), f'"{QUESTION}"', font=font(20), fill=GOLD)

    for x, title, sub, value, colour, tables in (
        (40, "Whole schema", f"{objects:,} tables and views", shown_full, RED, None),
        (500, "schemagate", f"{sent} tables, all {len(NEEDED)} it needs", shown_sel, TEAL, picked),
    ):
        d.rounded_rectangle([x, 126, x + 420, 340], 16, fill=PANEL)
        d.text((x + 24, 146), title, font=font(24, True), fill=INK)
        d.text((x + 24, 182), sub, font=font(17), fill=DIM)
        if value is not None:
            d.text((x + 24, 222), f"{value:,}", font=font(52, True), fill=colour)
            d.text((x + 24, 292), "prompt tokens per question", font=font(17), fill=DIM)
        if tables and value is not None and value == shown_sel and verdict:
            d.text((x + 250, 236), "\n".join(f"+ {t}" for t in sorted(tables)), font=font(15), fill=INK, spacing=6)

    if verdict:
        d.text((40, 362), f"{100 * (1 - shown_sel / full):.0f}% fewer tokens on this question", font=font(26, True), fill=GOLD)
        d.text((40, 400), "Median on real 50+ table databases (Spider 2.0): 91.1% fewer.  #1 on BIRD Mini-Dev.",
               font=font(16), fill=DIM)
    return img


def main():
    objects, full, sent, sel = measure()
    frames, durations = [], []
    steps = 12
    for i in range(steps + 1):                      # the whole-schema count climbs
        frames.append(frame(objects, full, sent, NEEDED, round(full * i / steps), None, False))
        durations.append(70)
    durations[-1] = 700
    for i in range(1, 7):                           # then schemagate's, which stops early
        frames.append(frame(objects, full, sent, NEEDED, full, round(sel * i / 6), False))
        durations.append(90)
    frames.append(frame(objects, full, sent, NEEDED, full, sel, True))
    durations.append(4500)
    out = HERE / "token-savings.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {out.name}: {objects:,} objects, {full:,} -> {sel:,} tokens "
          f"({100 * (1 - sel / full):.1f}% fewer), {sent} tables sent")


if __name__ == "__main__":
    main()
