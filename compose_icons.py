#!/usr/bin/env python3
"""Compose 32x24 mono icons for NFX-BO, NUW-JT, NUW-PT, NUW-TS, NUW-G8.
Bottom label reuses real Elektron glyphs (B from NFX-BC, 2 from NFX-D2 --
kept available even though nothing currently uses the "2" glyph) where
available, hand-designed O/U/W/J/T/S/P/G/8 matched to the same ~8px block
weight otherwise. Top motif: doubled bouncing-ball arcs for BO (echoing
its 12-bit-packing doubled capture length -- NFX-BO was promoted from
the former NFX-B2 on 2026-11-09, retiring the original single-bounce
24-bit build this used to generate under the "BO" name), a loop/
infinity arrow for JT (self-sampling loop + jitter), a tape-reel
pictogram for TS (tape-speed), a bent-line pictogram for PT
(pitch-bend), a scatter of discrete grain marks for G8 (granular
synthesis) -- the one motif in this family that's deliberately NOT a
continuous line, since G8 is the one machine that plays back discrete
sampled fragments rather than a continuous waveform/loop.
"""
import sys
from pathlib import Path

WIDTH, HEIGHT = 32, 24

GLYPHS = {
    "B": [
        "#######.",
        "########",
        "##....##",
        "#######.",
        "#######.",
        "##....##",
        "########",
        "#######.",
    ],
    "2": [
        ".#####.",
        "#######",
        ".....##",
        "....##.",
        "..###..",
        ".##....",
        "#######",
        "#######",
    ],
    "O": [
        ".#####.",
        "#######",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "#######",
        ".#####.",
    ],
    "U": [
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "########",
        ".######.",
    ],
    "W": [
        "#.......#",
        "#.......#",
        "#.#...#.#",
        "#.#...#.#",
        ".#.#.#.#.",
        ".#.#.#.#.",
        ".#.#.#.#.",
        "..##.##..",
    ],
    "J": [
        ".#####.",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "#..##..",
        "##.##..",
        ".####..",
    ],
    "T": [
        "#######",
        "#######",
        "..###..",
        "..###..",
        "..###..",
        "..###..",
        "..###..",
        "..###..",
    ],
    "S": [
        ".######",
        "#######",
        "##.....",
        ".#####.",
        "......#",
        "......#",
        "#######",
        "######.",
    ],
    "P": [
        "######.",
        "#######",
        "##...##",
        "#######",
        "######.",
        "##.....",
        "##.....",
        "##.....",
    ],
    "G": [
        ".#####.",
        "#######",
        "##.....",
        "##.###.",
        "##..##.",
        "##..###",
        "#######",
        ".#####.",
    ],
    "8": [
        ".#####.",
        "#######",
        "##...##",
        ".#####.",
        ".#####.",
        "##...##",
        "#######",
        ".#####.",
    ],
}

def blank_grid():
    return [["0"] * WIDTH for _ in range(HEIGHT)]

def stamp(grid, glyph_rows, top, left):
    for dy, row in enumerate(glyph_rows):
        for dx, ch in enumerate(row):
            if ch == "#":
                y, x = top + dy, left + dx
                if 0 <= y < HEIGHT and 0 <= x < WIDTH:
                    grid[y][x] = "1"

def set_pixel(grid, x, y):
    if 0 <= y < HEIGHT and 0 <= x < WIDTH:
        grid[y][x] = "1"

def place_label(grid, letters, top=14):
    """Center a 2-letter label horizontally, each glyph's own width,
    with a 2px gap between them."""
    widths = [len(GLYPHS[ch][0]) for ch in letters]
    gap = 2
    total_w = sum(widths) + gap * (len(letters) - 1)
    left = (WIDTH - total_w) // 2
    for ch, w in zip(letters, widths):
        stamp(grid, GLYPHS[ch], top, left)
        left += w + gap

def diag_line(grid, x0, y0, x1, y1, thick=False):
    """Draw a straight line where |dx|==|dy| (45-degree) or a horizontal
    line (dy==0), stepping exactly 1px per step -- no rounding, so no
    scatter at this tiny resolution."""
    dx = 1 if x1 > x0 else (-1 if x1 < x0 else 0)
    dy = 1 if y1 > y0 else (-1 if y1 < y0 else 0)
    x, y = x0, y0
    while True:
        set_pixel(grid, x, y)
        if thick:
            set_pixel(grid, x, y + 1)
        if (x, y) == (x1, y1):
            break
        x += dx
        y += dy

def bounce_motif(grid, y_base=9):
    """A bouncing-ball pictogram: baseline plus decaying triangular
    bounces (clean 45-degree up/down legs, no curve-rounding scatter),
    left to right."""
    for x in range(2, 30):
        set_pixel(grid, x, y_base)
    # each bounce: (start_x, apex_height, leg_len) -- apex_height ==
    # leg_len keeps the legs at a clean 45 degrees
    bounces = [(3, 6), (12, 4), (19, 3), (24, 2)]
    x = bounces[0][0]
    for start_x, h in bounces:
        apex_x = start_x + h
        end_x = apex_x + h
        diag_line(grid, start_x, y_base, apex_x, y_base - h)
        diag_line(grid, apex_x, y_base - h, end_x, y_base)

def loop_motif(grid):
    """A simple infinity/loop glyph: two small diamond rings side by
    side, sharing their middle point -- clean 45-degree legs throughout,
    reads clearly as a 'loop' pictogram at this resolution."""
    def diamond(cx, cy, r):
        diag_line(grid, cx - r, cy, cx, cy - r)
        diag_line(grid, cx, cy - r, cx + r, cy)
        diag_line(grid, cx + r, cy, cx, cy + r)
        diag_line(grid, cx, cy + r, cx - r, cy)
    diamond(11, 6, 4)
    diamond(19, 6, 4)

def reel_motif(grid):
    """Tape-reel pictogram for TS (tape-speed): two diamond 'reels' with
    a crossed spoke through each (distinguishing them from JT's own
    touching-diamond loop glyph), joined by a straight 'tape' line --
    same 45-degree diamond-drawing primitive as loop_motif, just spaced
    apart with a connecting line instead of sharing a middle point."""
    def reel(cx, cy, r):
        diag_line(grid, cx - r, cy, cx, cy - r)
        diag_line(grid, cx, cy - r, cx + r, cy)
        diag_line(grid, cx + r, cy, cx, cy + r)
        diag_line(grid, cx, cy + r, cx - r, cy)
        diag_line(grid, cx - r, cy - r, cx + r, cy + r) # spoke
        diag_line(grid, cx - r, cy + r, cx + r, cy - r) # spoke
    reel(8, 6, 4)
    reel(24, 6, 4)
    for x in range(13, 20):
        set_pixel(grid, x, 6) # tape path between the two reels

def bend_motif(grid):
    """Pitch-bend pictogram for PT: a single waveform-like zigzag line
    that bends upward then back down -- reads as 'pitch wobbling up and
    down' rather than JT/TS's own circular reel/loop glyphs, using the
    same diag_line primitive throughout."""
    diag_line(grid, 3, 9, 9, 3)
    diag_line(grid, 9, 3, 15, 9)
    diag_line(grid, 15, 9, 21, 3)
    diag_line(grid, 21, 3, 27, 9)

def grain_motif(grid):
    """Granular-synthesis pictogram for G8: a scatter of discrete
    'grain' marks (mixed single pixels and 2x2 blocks, for a sense of
    varying grain size), not a continuous line -- the one motif in
    this family that deliberately isn't, since G8 is the one machine
    playing back discrete sampled fragments rather than a continuous
    waveform/loop. Hand-placed (not random) so it's reproducible and
    reads as a deliberate spray rather than noise."""
    for (x, y) in [
        (4, 3), (8, 2), (13, 3), (17, 2), (21, 3), (27, 2),
        (6, 9), (11, 9), (24, 9), (29, 6), (3, 6), (30, 3),
    ]:
        set_pixel(grid, x, y)
    for (x0, y0) in [(9, 5), (15, 6), (20, 5), (25, 7), (5, 7)]:
        for dx in range(2):
            for dy in range(2):
                set_pixel(grid, x0 + dx, y0 + dy)

def to_rows(grid):
    return ["".join(row) for row in grid]

def render(rows, label=""):
    print(f"--- {label} ---")
    for row in rows:
        print(row.replace("1", "#").replace("0", "."))
    print()

def write_pbm(rows, path):
    bits = "\n".join(rows)
    tokens = " ".join(bits.replace("\n", ""))
    with open(path, "w") as f:
        f.write(f"P1\n{WIDTH} {HEIGHT}\n")
        for row in rows:
            f.write(" ".join(row) + "\n")

if __name__ == "__main__":
    # NFX-BO (promoted 2026-11-09 from the former NFX-B2 -- the original
    # single-bounce 24-bit build this slot used to generate is retired):
    # doubled bounce traces (two interleaved arcs at slightly different
    # baselines) echoing the 12-bit packing's doubled capture length + "BO"
    g_bo = blank_grid()
    bounce_motif(g_bo, y_base=9)
    bounce_motif(g_bo, y_base=11)
    place_label(g_bo, ["B", "O"])
    rows_bo = to_rows(g_bo)
    render(rows_bo, "NFX-BO")

    # NUW-JT: loop/repeat arrow + "JT"
    g_jt = blank_grid()
    loop_motif(g_jt)
    place_label(g_jt, ["J", "T"])
    rows_jt = to_rows(g_jt)
    render(rows_jt, "NUW-JT")

    # NUW-TS: tape-reel pictogram + "TS"
    g_ts = blank_grid()
    reel_motif(g_ts)
    place_label(g_ts, ["T", "S"])
    rows_ts = to_rows(g_ts)
    render(rows_ts, "NUW-TS")

    # NUW-PT: pitch-bend zigzag pictogram + "PT"
    g_pt = blank_grid()
    bend_motif(g_pt)
    place_label(g_pt, ["P", "T"])
    rows_pt = to_rows(g_pt)
    render(rows_pt, "NUW-PT")

    # NUW-G8: grain-scatter pictogram + "G8"
    g_g8 = blank_grid()
    grain_motif(g_g8)
    place_label(g_g8, ["G", "8"])
    rows_g8 = to_rows(g_g8)
    render(rows_g8, "NUW-G8")

    write_pbm(rows_bo, "nfxbo_icon.pbm")
    write_pbm(rows_jt, "nuwjt_icon.pbm")
    write_pbm(rows_ts, "nuwts_icon.pbm")
    write_pbm(rows_pt, "nuwpt_icon.pbm")
    write_pbm(rows_g8, "nuwg8_icon.pbm")
    print("wrote nfxbo_icon.pbm, nuwjt_icon.pbm, nuwts_icon.pbm, nuwpt_icon.pbm, nuwg8_icon.pbm")
