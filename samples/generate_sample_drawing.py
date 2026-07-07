"""
Generate samples/A-201_stair_section.pdf — a clean, monochrome architectural
stair section with dimension annotations, used as the sample input for the
LLM PDF extraction path (extractors/pdf_extractor.py).

The annotation strings on this sheet are the ground truth the extractor is
expected to read back:

    RISER 190 mm
    TREAD RUN 255 mm
    CLEAR WIDTH 910 mm            (plan note)
    HANDRAIL 920 mm ABOVE NOSING
    HEADROOM 2050 mm

Run:  python3 samples/generate_sample_drawing.py
Deps: matplotlib (pip3 install matplotlib --break-system-packages)
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "A-201_stair_section.pdf")

# Drawing scale: 1 unit = 100 mm real-world (so a 190 mm riser is 1.9 units).
RISER = 1.90   # 190 mm
TREAD = 2.55   # 255 mm
N_STEPS = 6

INK = "#1a1a1a"
THIN = 0.7
MED = 1.1

FONT = {"family": "Helvetica", "size": 7, "color": INK}
FONT_SMALL = {"family": "Helvetica", "size": 5.5, "color": INK}


def _leader(ax, xy_from, xy_to, text, ha="left", va="center"):
    """Dimension annotation with a thin leader line and a dot at the target."""
    ax.annotate(
        text,
        xy=xy_from,
        xytext=xy_to,
        fontsize=7,
        fontfamily="Helvetica",
        color=INK,
        ha=ha,
        va=va,
        arrowprops=dict(arrowstyle="-", lw=THIN, color=INK, shrinkA=2, shrinkB=1),
    )
    ax.plot([xy_from[0]], [xy_from[1]], marker="o", ms=1.6, color=INK)


def main() -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5))  # US letter landscape
    ax.set_aspect("equal")
    ax.axis("off")

    # ---- stepped stair profile ------------------------------------------
    # Build the nosing polyline: up a riser, across a tread, repeated.
    xs, ys = [0.0], [0.0]
    for i in range(N_STEPS):
        xs.append(xs[-1])
        ys.append(ys[-1] + RISER)
        xs.append(xs[-1] + TREAD)
        ys.append(ys[-1])
    ax.plot(xs, ys, color=INK, lw=MED, solid_joinstyle="miter")

    top_x = xs[-1]
    top_y = ys[-1]

    # Underside of the stringer (parallel soffit line) closing the profile.
    soffit_drop = 2.2
    ax.plot([0, top_x], [-soffit_drop, top_y - soffit_drop], color=INK, lw=MED)
    ax.plot([0, 0], [0, -soffit_drop], color=INK, lw=MED)
    ax.plot([top_x, top_x], [top_y, top_y - soffit_drop], color=INK, lw=MED)

    # Ground floor line and upper landing line.
    ax.plot([-4.0, 1.0], [0, 0], color=INK, lw=THIN)
    ax.plot([top_x, top_x + 5.0], [top_y, top_y], color=INK, lw=MED)
    ax.plot([top_x, top_x + 5.0], [top_y - 0.35, top_y - 0.35], color=INK, lw=THIN)

    # Floor/ceiling assembly above the stair (defines headroom).
    ceil_y = ys[3] + 2050 / 100.0  # headroom 2050 mm above 2nd nosing (1 unit = 100 mm)
    ceil_x0, ceil_x1 = -4.0, top_x - 1.5 * TREAD
    ax.plot([ceil_x0, ceil_x1], [ceil_y, ceil_y], color=INK, lw=MED)
    ax.plot([ceil_x0, ceil_x1], [ceil_y + 0.35, ceil_y + 0.35], color=INK, lw=MED)
    ax.plot([ceil_x1, ceil_x1], [ceil_y, ceil_y + 0.35], color=INK, lw=MED)

    # ---- handrail (920 mm above nosings, parallel to pitch) --------------
    HR = 920 / 100.0  # 920 mm in drawing units (1 unit = 100 mm)
    hr_x0, hr_y0 = xs[2], ys[2] + HR          # above 1st nosing
    hr_x1, hr_y1 = xs[-2], ys[-2] + HR        # above last nosing
    ax.plot([hr_x0, hr_x1], [hr_y0, hr_y1], color=INK, lw=MED)
    # Balusters (thin, every other nosing).
    for i in range(1, N_STEPS + 1):
        bx, by = xs[2 * i], ys[2 * i]
        ax.plot([bx, bx], [by, by + HR], color=INK, lw=THIN * 0.6)

    # ---- dimension annotations with leader lines --------------------------
    # RISER 190 mm — extension ticks on the 3rd riser.
    rx = xs[4]  # x of 3rd riser face
    ry0, ry1 = ys[4], ys[5]
    ax.plot([rx - 0.9, rx - 0.9], [ry0, ry1], color=INK, lw=THIN)
    ax.plot([rx - 1.1, rx - 0.7], [ry0, ry0], color=INK, lw=THIN)
    ax.plot([rx - 1.1, rx - 0.7], [ry1, ry1], color=INK, lw=THIN)
    _leader(ax, (rx - 0.9, (ry0 + ry1) / 2), (rx - 5.5, (ry0 + ry1) / 2 - 1.2),
            "RISER 190 mm", ha="right")

    # TREAD RUN 255 mm — extension ticks under the 3rd tread.
    tx0, tx1 = xs[5], xs[6]
    ty = ys[5]
    ax.plot([tx0, tx1], [ty - 0.9, ty - 0.9], color=INK, lw=THIN)
    ax.plot([tx0, tx0], [ty - 1.1, ty - 0.7], color=INK, lw=THIN)
    ax.plot([tx1, tx1], [ty - 1.1, ty - 0.7], color=INK, lw=THIN)
    _leader(ax, ((tx0 + tx1) / 2, ty - 0.9), ((tx0 + tx1) / 2 + 4.5, ty - 3.2),
            "TREAD RUN 255 mm", ha="left")

    # HANDRAIL 920 mm ABOVE NOSING — leader to the rail.
    mid_hr_x = (hr_x0 + hr_x1) / 2
    mid_hr_y = (hr_y0 + hr_y1) / 2
    _leader(ax, (mid_hr_x, mid_hr_y), (mid_hr_x - 9.5, mid_hr_y + 3.0),
            "HANDRAIL 920 mm ABOVE NOSING", ha="right")

    # HEADROOM 2050 mm — vertical dimension from 2nd nosing to ceiling.
    hx = xs[3] + 0.3
    hy0 = ys[3]
    ax.plot([hx, hx], [hy0, ceil_y], color=INK, lw=THIN)
    ax.plot([hx - 0.2, hx + 0.2], [hy0, hy0], color=INK, lw=THIN)
    ax.plot([hx - 0.2, hx + 0.2], [ceil_y, ceil_y], color=INK, lw=THIN)
    _leader(ax, (hx, (hy0 + ceil_y) / 2), (hx - 6.5, (hy0 + ceil_y) / 2 + 1.5),
            "HEADROOM 2050 mm", ha="right")

    # CLEAR WIDTH 910 mm — plan note (width is perpendicular to this section).
    ax.text(top_x + 0.5, ys[7] + 1.0,
            "CLEAR WIDTH 910 mm\n(SEE PLAN — BETWEEN WALL FACES)",
            fontsize=7, fontfamily="Helvetica", color=INK, ha="left", va="center")

    # Section label (top-left, clear of leaders).
    ax.text(-13.0, 25.8, "STAIR SECTION 1",
            fontsize=10, fontfamily="Helvetica", fontweight="bold", color=INK)
    ax.text(-13.0, 24.9, "SCALE 1:20",
            fontsize=7, fontfamily="Helvetica", color=INK)

    # ---- title block bottom-right ----------------------------------------
    ax.set_xlim(-14, 30)
    ax.set_ylim(-7.5, 27)
    tb_w, tb_h = 15.0, 2.4
    tb_x, tb_y = 30 - tb_w - 0.8, -7.5 + 0.6
    ax.add_patch(Rectangle((tb_x, tb_y), tb_w, tb_h, fill=False, ec=INK, lw=MED))
    ax.plot([tb_x, tb_x + tb_w], [tb_y + tb_h / 2, tb_y + tb_h / 2], color=INK, lw=THIN)
    ax.text(tb_x + 0.3, tb_y + tb_h * 0.72,
            "SHEET A-201 — STAIR SECTIONS",
            fontsize=8, fontfamily="Helvetica", fontweight="bold", color=INK, va="center")
    ax.text(tb_x + 0.3, tb_y + tb_h * 0.25,
            "PROJECT: SAMPLE 2-STOREY DWELLING  |  SCALE 1:20",
            fontsize=6.5, fontfamily="Helvetica", color=INK, va="center")

    # Sheet border.
    ax.add_patch(Rectangle((-13.7, -7.2), 43.4, 33.9, fill=False, ec=INK, lw=MED))

    fig.savefig(OUT_PATH, format="pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
