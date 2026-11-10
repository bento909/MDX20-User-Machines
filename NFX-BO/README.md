# NFX-BO

A custom Elektron Machinedrum "User Machine" (NFX effect category) — a
bouncing-ball delay: on each trig, captures a short blend of the two
tracks before it and plays it back as a series of discrete, decaying,
bouncing-ball-style echoes. 12-bit sample packing doubles capture length
for a given `DECIM` versus a plain 24-bit buffer.

**Promoted to be the mainline NFX-BO on 2026-11-09**, retiring the
original 24-bit build of the same name (direct user request: "we are
going to retire NFX-BO and rename NFX-B2 to NFX-BO" — the original had
the same behavior, just half the capture length at a given `DECIM`, and
the user found the 12-bit version both equally good and the better of
the two to keep). Everything below this point in the file's own history
was written while this was still a separate sibling machine named
**NFX-B2** — `DESIGN.md`/`BRIEF.md` still refer to that now-retired
original by its old name, `NFX-BO`, throughout; read historical sections
below with that in mind rather than as describing a currently-existing
sibling.

## Status

**Confirmed working on real hardware (user report, 2026-11-09): both
this (12-bit) and the now-retired original 24-bit build were good, and
this one's the better of the two to keep — longer delay capture for the
same `DECIM`.**

**Cycle budget (certified MDS 1.1, `mds-certifier`'s full exhaustive
run, 2026-11-09): MKII 7400 / MKI-DRAM 9500 / MKI-SRAM 9036.** (Earlier,
pre-promotion certified numbers under the NFX-B2 name: MKII 7393 /
MKI-DRAM 9491 / MKI-SRAM 9029 — the tiny increase is just the icon swap
done the same day, not a logic change.) See "Round 2 (2026-11-06):
fresh rebuild" below for the full history of how this build reached a
certified, working state.

v1 ships the same 7 parameters the original 24-bit NFX-BO had —
**NBAL, GATE, RATE, BEND, DCAY, MIX, RVRS** — implemented, assembled,
packed, and cycle-checked. Functionally verified against the real
DSP56300 emulator (capture pack/unpack round-trip, the window-boundary
edge, reverse-capture write-pairing, a precise single-step
BOUNCE_ADVANCE check, and a long-run decay-to-IDLE trace — see
`DESIGN.md` §4/§6/§7 for details).

### History, back when this was a separate sibling named NFX-B2

**First real-hardware test (2026-11-04/05) came back "screeching noise,
utterly unusable."** Extensive re-verification (see `DESIGN.md` §7)
found no logic bug — the leading hypothesis (a shift-fusion hazard in
`BOUNCE_ADVANCE`'s write-back) was directly disproven by re-running the
probes, and a long-run trace confirmed the decay/stop machinery works
correctly over many real repeats. One genuinely unprecedented pattern
(a same-address Y-memory read done TWICE per event) was removed as a
risk-reduction measure regardless.

**A follow-up report (2026-11-06) sharpened the picture: still
unusable, AND it freezes/crashes the unit after some trigs/repeats.**
This time a root cause was found with real confidence: a `jeq`
(absolute long jump) had been added inside the hardware `do #32,...`
loop, purely to work around the short-branch distance limit — the ONE
instruction in the whole file with no precedent in this engine's own
12-rounds-hardware-proven history (under its original 24-bit name).
**Confirmed against the official Motorola DSP56000 Assembler Reference
Manual**: `Jcc` (what `jeq` is) is explicitly documented as a
hardware-DO-loop-interacting, two-word instruction class, grouped with
`JMP`/`JSET`/`JCLR` — plain short branches are not in that class. Fixed
by replacing it with a two-hop short-branch relay (`beq`→`bra`), using
only instruction forms already proven throughout this project. See
`DESIGN.md` §8 for the full writeup and manual citation. Re-verified
(cycle budget and functional probes unchanged, 3934/3951). The real
hardware test that followed (per the Status section above) confirmed
this fix held.

## Round 2 (2026-11-06): fresh rebuild from the original NFX-BO's current build

Per direct user request ("try and implement NFX-BO in 12 bit again"),
rebuilt from scratch starting from the original 24-bit NFX-BO's own
CURRENT, already certifier-audited source (which had since picked up
the FIRST_GAP_FLOOR stacking guard and DCAY_MULT caching — both absent
from this backport's own first attempt, which had forked from an
earlier snapshot of the original) — not a continuation of that first
attempt's shelved file (kept as a full folder backup at the time in a
sibling `..._pre_rebuild_backup/` directory, since deleted). The SAME
proven 12-bit pack/unpack mechanism (CAP_STORE's write-pairing,
BOUNCE_ADVANCE's TOP/BOTTOM dual-path read-modify-write) was re-applied,
carrying forward every lesson from the first attempt: the
`y_workset_words` fix (31→32, for the new PENDING_HALF slot) was
correct from the start, and the short-branch-range relay for the shared
PHASE=0 gate check was applied PROACTIVELY (not discovered the hard way
via a hardware freeze) — the relay turned out to be necessary again
(280 words between the gate check and its target, over the +/-255-word
short-branch range), confirming it wasn't a one-off accident of the
original code shape.

Functionally re-verified via `probe_nfxbo.cpp` (same probe, re-run
against the new build): 12-bit pack/unpack round-trip, the window-
boundary edge, reverse-capture write-pairing (all 1536 words), and a
precise single-step `BOUNCE_ADVANCE` check at both parities (TOP
updates/BOTTOM preserved and vice versa) — all pass exactly.

Unlike NUW-JT, this machine's bounce-restart timing is data-dependent
(driven by RATE/BEND), so the bulk-pass restructuring that cut NUW-JT's
own cost by ~10% doesn't carry over directly here.

## What's actually different from the original 24-bit NFX-BO

Two 12-bit samples now share each 24-bit buffer word (same packing
NUW-JT already shipped), doubling effective capture length for the
same `DECIM` — e.g. ~139ms becomes ~278ms at `DECIM=4`. The tradeoff is
dynamic range: ~72dB instead of full 24-bit headroom, SP-1200/Akai-S900
-style crunch. Behaviorally this sounds and feels like the original did,
just with room for longer (or equivalently lower-`DECIM`, cleaner)
captures at the same buffer size.

One real bug in the ORIGINAL 24-bit build was found and fixed while
backporting (see `DESIGN.md` §3), and carried the fix forward into this
one: the capture window's own close-check dropped the very last word of
every capture (an off-by-one, `ble` where it needed to be `blt`) — never
caught in 12 rounds of hardware testing on the original because losing
1 word out of 1536 at the tail of a long capture is easy to miss by ear.

## Parameters

| # | Knob | Range | What it does |
|---|------|-------|---------------|
| 1 | NBAL | unipolar | Neighbour blend: 0 = two tracks back (far), max = one track back (near). |
| 2 | GATE | bipolar | Shapes the capture window around center (full window): one side delays the start (keeps the tail), the other stops early (keeps the head). |
| 3 | RATE | unipolar, squared | Gap before the first repeat. |
| 4 | BEND | bipolar | Per-repeat gap multiplier: center = steady, one side shrinks the gap each repeat (speeding up), the other grows it (slowing down). |
| 5 | DCAY | unipolar | How much level survives each repeat (max ≈ 99%). |
| 6 | MIX | unipolar | Dry/wet — **monitor-only**: it blends what you hear, but every capture always stores dry+wet regardless of where MIX is set (the delay always has to "hear" the raw input to have anything to echo back later). Change MIX while a capture is in progress and that captured segment keeps whatever dry/wet split was live at the time, baked in — expected, not a bug, if a brief dry-ish tinge rides along on it a little while after. |
| 7 | RVRS | bipolar | Reverse-capture probability: one extreme always reverses this trig's capture, the other never does, center is a 50/50 coin flip (every value between is the probability). |

`DECIM` (capture/playback decimation, now doubling capture length at a
given value since the buffer holds twice as many logical samples) is
**not a knob**, a compile-time constant near the top of `NFXBO.asm56k`.

## Repo contents

- `BRIEF.md` — design brief (written under this machine's former name, NFX-B2 — the behavior it describes is unchanged)
- `DESIGN.md` — technical design notes (the 12-bit backport specifically, written under the NFX-B2 name throughout)
- `NFXBO.asm56k` — DSP56300 assembly source (the machine itself)
- `NFXBO.json` — machine manifest (parameters, transforms, memory/import declarations)
- `NFXBO.lod` / `NFXBO.mds` / `NFX-BO.syx` — build outputs (see Build below)
- `NFXBO.symbols.json` — label/address table from the assembler
- `NFXBO_icon.pbm` — the machine's 32x24 mono sprite, ASCII P1 PBM source. Still carries its original "B2"-labeled artwork from before the rename — not yet redesigned to say "BO"; edit it in Sprite Bench (`../sprite_bench.html`) whenever you want to update it. To view/edit it in a normal image editor instead: `python mds-tools/tools/mds_bitmap_export.py NFXBO.mds -o icon.bmp`, edit, then `--bitmap icon.bmp` on the next pack (BMP/PBM/native sprite all accepted)

## Build toolchain (external — not included in this repo)

Same three external tools as the rest of this project, cloned as sibling directories:

- [`kitbasher`](https://github.com/etcetc000/kitbasher) (GPLv3) — supplies the
  real DSP56300 cross-assembler used as the `.asm56k` front end.
- [`mds-tools`](https://github.com/jmamma/mds-tools) — supplies the packaging/sysex-conversion
  tools and the official Machine Dump Standard spec (use `mds-tools/tools/`, NOT the stale `MDS/tools/` copies — the latter don't understand MDS 1.1's 3-way cycle declaration).
- [`dsp56300`](https://github.com/dsp56300/dsp56300) (GPLv3) — DSP56300
  emulator; only needed if you want to cycle-check or simulate, not required
  to build.

### Build steps

```sh
export PATH="/c/Users/thisi/AI/Workspace/Tools/mingw64/bin:$PATH"  # mds-certifier needs this on PATH

# 1. assemble: .asm56k -> .lod
python tools/mds_assemble.py NFXBO.asm56k --out NFXBO.lod --symbols-out NFXBO.symbols.json

# 2. package + certify-and-stamp real cycle costs: .json + .lod -> .mds
python mds-tools/tools/mds_pack.py NFXBO.json NFXBO.lod --format lod --bitmap NFXBO_icon.pbm --certify --report NFXBO_cert.json -o NFXBO.mds

# 3. transfer-encode: .mds -> .syx
python mds-tools/tools/mds_to_syx.py NFXBO.mds --slot 1 -o NFX-BO.syx
```

(adjust paths to wherever you clone each dependency; slot 1 is the
convention this machine now uses, having taken over the retired
original's slot — pick whatever free slot you actually want on your own
Machinedrum)

Flash the resulting `NFX-BO.syx` to the Machinedrum over MIDI to install it
into a USR machine slot (U01–U16). Only install machine code from sources you
trust — it runs directly on the DSP.

## Not included

This repo deliberately excludes any disassembled/extracted Elektron factory
firmware content used during development (see `.gitignore`) — that material
is proprietary and isn't redistributable.

## License

TBD.
