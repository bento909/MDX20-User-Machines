# NUW-JT

A custom Elektron Machinedrum "User Machine" (NFX effect category) —
a self-sampling overdub/freeze machine, built from NFX-BO's patterns but
architecturally different. On each trig, it runs a single pass through
its own small capture buffer: reading whatever's already there (that's
what you hear), and — depending on the REC knob — blending in a fresh
live capture before writing it back, sound-on-sound. See `BRIEF.md` for
the design brief and `DESIGN.md` for the technical design (parameter
transforms, memory layout, the 12-bit packing scheme).

## Status

**Cycle budget (certified MDS 1.1, `jmamma`'s `mds-certifier`,
2026-11-06): MKII 7136 / MKI-DRAM 9421 / MKI-SRAM 8863 — over the real
16-track-safe ceiling of 3000 (MKII), down from 8001/10200/9729 after
Round 6's ground-up bulk-pass rewrite of RENDER (~9-11% cut).** See the
Round 6 entry below. Re-verified unchanged 2026-11-09 after the
NFX-UW&rarr;NUW-JT rename (pure identity/text change, no code touched).

v1 ships 8 parameters — **NBAL, GATE, REC, RVRS, MIX, STRT, LOOP,
JITR** — implemented, assembled, packed. **Round 5 (2026-11-06): the real
certifier shows the true worst-case cost is 8001/3951 MKII (10200 MKI),
not 3948** — this project's own `dsp56300/cyclecheck` emulator doesn't
model real memory wait-states/pipeline interlocks and badly underestimated
it; the real 16-track-safe ceiling is 3000 cycles (MKII), not 3951. Audited
for safe, non-feature-affecting fixes and found none left to apply (every
spare register is already caching a block-constant from an earlier round)
— see `DESIGN.md` §13. Closing the real gap needs a feature-level change,
not attempted yet. Round 2's hardware test found two real bugs, both
fixed (see `DESIGN.md` §3/§4/§4a): a write-pairing bug that scrambled
captures specifically in reverse, and an off-by-one that dropped the
very last word of every capture in both directions. A feedback gate was
also added — REC's overdub is a closed feedback loop with no forced
decay, and near-silent residue (plus the 12-bit quantization's own
rounding bias) could otherwise recirculate and slowly build up.

Round 3 added a decoupled PLAYBACK head with its own loop region
(STRT/LOOP) plus a variable-speed/reverse knob (SPED) — capture keeps
running at its own fixed, pristine rate regardless of what PLAYBACK is
doing. **SPED was REMOVED 2026-11-04** (same day, direct user request)
after a hardware report: "the speed parameter just makes it sound like
hell" / "at 0 speed nothing happens." The root cause — a genuine 2x
calibration error in the interpolation-ramp math, worse at the clamped
extremes — was found and fixed, but rather than ship-and-retest the
user asked to pull the knob out entirely ("we might revisit"). PLAYBACK
kept its decoupled-from-capture design and its loop region (STRT/LOOP),
just always scrubbing forward now at the machine's original fixed
rate — and dropping the variable-rate knob let PLAYBACK's own
internals simplify a lot: no more fixed-point phase accumulator, no
more forward/backward loop-body split, just a plain decimated advance
(the same shape capture's own DECIM_CTR already uses) — which also
freed enough cycle budget to go from razor-thin margins back to a
comfortable one. See `DESIGN.md` §8/§9 for the full architecture and
cycle-budget story, and §10 for the SPED-removal writeup.

Round 4 (2026-11-05) filled the trailing-unused 8th slot with **JITR**
— a random per-trig offset on LOOP_START, for a small amount of
position jitter. Found and fixed a real, independent bug while
designing it: PLAYBACK's loop region can legitimately extend past the
buffer's own physical end (by design — see LOOP above), but wasn't
actually wrapping the read/write address back into bounds, risking
reads/writes outside this track's own buffer. Closed a resulting
cycle-budget overage (37 over at the worst case where RVRS's own draw
and JITR's draw both fire on the same trig) down to 3948/3951 (3
spare) by switching JITR's own randomness mix from a conditional,
branching shape to an unconditional, branchless one — JITR doesn't
need RVRS's full statistical rigor, just per-trig variation, and this
project has found branches (not instruction count) to be the real
cost driver on this emulator. See `DESIGN.md` §11/§12 for the full
writeup. **Not yet tested on hardware since this round.**

Round 6 (2026-11-06): a ground-up rewrite of RENDER's per-sample loop,
inspired by a community catalog of USR machines
(`github.com/murdenihcam/murdenihcam-usr-machines`) that certified
cheaper than NUW-JT despite being more feature-rich. The old loop
checked "is this a decimated step?" via two separate counters, 32
times a block, to gate work that only ever actually ran 8 times — a
real, measured proof showed those two counters are provably always in
lockstep (same seed, same period), so the real decimated event always
lands on a fixed stride (every 4th sample), never data-dependent.
RENDER_LOOP now runs `do #8` instead of `do #32`, with 3 plain
samples (dry blend + ramp + mix only) unrolled ahead of the 1 real
decimated sample (full capture + playback retarget) each iteration —
the loop structure itself is the gate, no per-sample counter check
needed at all. Every correctness-critical detail (window-boundary
fix, reverse write-pairing, the physical-wrap fix, the shift-fusion-
safe unpack patterns, the overflow-safe INTERP_STEP math, the
FEEDBACK_GATE clamp) is carried over verbatim, just re-triggered at
each of the 4 inner positions instead of once per sample. Verified
functionally byte-for-byte identical to the pre-rewrite build across
all 8 existing `probe_nuwjt.cpp` scenarios before re-measuring.
Program size grew 494→553 words (the unrolling tax) but real cost
dropped MKII 8001→7136 / MKI-DRAM 10200→9421 / MKI-SRAM 9729→8863 (a
genuine ~9-11% cut, confirming branches — not memory access or raw
instruction count — were the real driver, same conclusion the
murdenihcam comparison predicted). The pre-rewrite build is kept as a
full folder snapshot in the sibling `NUW-JT_pre_bulkpass_backup/`
directory. **Not yet tested on hardware since this round.** See
`DESIGN.md` §14 for the full writeup.

No RATE/BEND/DCAY, no repeat/decay engine — every trig plays through the
buffer exactly once (STRT/LOOP shape HOW that one pass scrubs through
the buffer, not how many passes happen); any additional looping or
stuttering comes from how you sequence trigs, not from this machine
itself. BITS (a bit-depth knob) was floated in the brief as "just an
idea for now" and is deliberately deferred — 12-bit packing is already
a fixed part of this build (see below), not a live-adjustable depth
yet. Grain-table-style playback and a variable-speed/reverse knob were
both explored and are deliberately deferred ("we might revisit") rather
than shipped half-working.

## Parameters

| # | Knob | Range | What it does |
|---|------|-------|---------------|
| 1 | NBAL | unipolar | Neighbour blend: 0 = two tracks back (far), max = one track back (near). |
| 2 | GATE | bipolar | Shapes how much of the fixed window writing is allowed to run for (reading always covers the whole window). |
| 3 | REC | unipolar | 0 = pure fresh capture, ignoring whatever's already in the buffer. 1..~126 = the existing buffer's content is folded back in at a REC-scaled level, on top of a full-level fresh capture (an overdub, not a crossfade). ~127 disables writing entirely for that trig — pure replay of whatever's already captured. |
| 4 | RVRS | bipolar | Reverse-capture probability: one extreme always reverses this trig's pass, the other never does, center is a 50/50 coin flip. Same mechanism as NFX-BO's own RVRS. |
| 5 | MIX | unipolar | Dry/wet on what you hear — never affects what gets captured. |
| 6 | STRT | unipolar | Playback loop region's start point, as a fraction of the buffer. |
| 7 | LOOP | unipolar, squared | Playback loop region's length. Max = the region spans the rest of the trig's fixed-length pass, so it plays once with no time left to wrap; smaller values wrap more times within that same fixed duration, circularly past the buffer's own physical end if needed. Playback always moves forward at the machine's fixed rate — no speed/reverse control for now. The knob's raw fraction is squared before scaling (2026-11-04) — low values get finer resolution (where small length changes have the biggest, most pitch-like effect), high values get coarser resolution (where it matters less). |
| 8 | JITR | unipolar | Random per-trig offset on the loop region's start point — 0 (default) = no jitter, exactly the plain STRT value every time; higher values draw a fresh random offset each trig, wrapping circularly if it pushes the region past either end of the buffer. |

**12-bit sample packing** is built into this machine from the ground up
(not a knob): two 12-bit samples share each 24-bit buffer word, doubling
effective capture length for the same `DECIM` setting (currently 4,
giving ~278ms — double NFX-BO's ~139ms at the same `DECIM`). The
tradeoff is dynamic range: ~72dB instead of full 24-bit headroom,
SP-1200/Akai-S900-style crunch. `DECIM` itself is a compile-time
constant in `NUWJT.asm56k`, same convention as NFX-BO.

## Repo contents

- `BRIEF.md` — design brief
- `DESIGN.md` — technical design notes
- `NUWJT.asm56k` — DSP56300 assembly source (the machine itself)
- `NUWJT.json` — machine manifest (parameters, transforms, memory/import declarations)
- `NUWJT.lod` / `NUWJT.mds` / `NUW-JT.syx` — build outputs (see Build below)
- `NUWJT.symbols.json` — label/address table from the assembler
- `NUWJT_icon.pbm` — the machine's 32x24 mono sprite, ASCII P1 PBM source
  (a loop/infinity pictogram + "JT" label, see `../compose_icons.py`). To
  view/edit it in a normal image editor instead:
  `python mds-tools/tools/mds_bitmap_export.py NUWJT.mds -o icon.bmp`,
  edit, then `--bitmap icon.bmp` on the next pack (BMP/PBM/native sprite
  all accepted).
  bundled into the build via `mds_pack.py --bitmap`

Open items and hardware-test history, plus any test recordings, live in
`_authoring\resource\`, same as NFX-BO's.

## Build toolchain (external — not included in this repo)

Same three external tools as NFX-BO, cloned as sibling directories:

- [`kitbasher`](https://github.com/etcetc000/kitbasher) (GPLv3) — supplies the
  real DSP56300 cross-assembler used as the `.asm56k` front end.
- [`MDS`](https://github.com/jmamma/MDS) — supplies the packaging/sysex-conversion
  tools and the official Machine Dump Standard spec.
- [`dsp56300`](https://github.com/dsp56300/dsp56300) (GPLv3) — DSP56300
  emulator; only needed if you want to cycle-check or simulate, not required
  to build.

### Build steps

```sh
# 1. assemble: .asm56k -> .lod
python tools/mds_assemble.py NUWJT.asm56k --out NUWJT.lod --symbols-out NUWJT.symbols.json

# 2. package + certify-and-stamp real cycle costs: .json + .lod -> .mds
python mds-tools/tools/mds_pack.py NUWJT.json NUWJT.lod --format lod --certify -o NUWJT.mds

# 3. transfer-encode: .mds -> .syx
python mds-tools/tools/mds_to_syx.py NUWJT.mds --slot 1 -o NUW-JT.syx
```

(always use `mds-tools/tools/`, not the stale `MDS/tools/` copies — the
latter don't understand MDS 1.1's 3-way cycle declaration and either
reject or mis-stamp a valid package)

(adjust paths to wherever you clone each dependency)

Flash the resulting `NUW-JT.syx` to the Machinedrum over MIDI to install it
into a USR machine slot (U01–U16). Only install machine code from sources you
trust — it runs directly on the DSP.

## Not included

This repo deliberately excludes any disassembled/extracted Elektron factory
firmware content used during development (see `.gitignore`) — that material
is proprietary and isn't redistributable.

## License

TBD.
