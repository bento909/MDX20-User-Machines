# NUW-TS

A custom Elektron Machinedrum "User Machine" (NFX effect category) —
[NUW-JT](../NUW-JT/)'s self-sampling overdub/freeze engine, with JITR
(random per-trig position jitter) replaced by **SPED**, a bidirectional
tape-speed/pitch-bend knob on PLAYBACK only. Negative = slower (lower
pitch), positive = faster (higher pitch), 0 = same speed as recorded.
**Round 2 (2026-11-07): the rate is now TRULY CONTINUOUS** (a fixed-
point fractional phase accumulator), not the 5 discrete octave-exact
steps round 1 shipped — direct user request. See `BRIEF.md` (shared
with NUW-JT — the base behavior is identical) and `DESIGN.md` for the
technical design, including SPED's own derivation and why it's
deliberately NOT a resurrection of the old (removed) SPED knob's design.

A sibling machine, [NUW-PT](../NUW-PT/), implements the SAME continuous
range via a completely different mechanism (murdenihcam's own semitone-
table + interpolation scheme, from his SMP-SL[ICE] machine) specifically
to compare cycle cost and performance against this one's approach.

**Final comparison (both full exhaustive certifier runs complete):**

| | NUW-TS (this machine, linear) | NUW-PT (semitone-table) |
|---|---|---|
| MKII | **9157** | 9260 (+1.1%) |
| MKI-DRAM | **11752** | 11886 (+1.1%) |
| MKI-SRAM | **10873** | 10991 (+1.1%) |

Within ~1% of each other despite visibly different per-trig
complexity — both approaches' real cost is dominated by the shared
per-sample PLAYBACK accumulator, not the once-per-trig derivation.
Notably, BOTH continuous designs cost ~5% more than round 1's own
discrete-PERIOD steps (8773 MKII) — see NUW-PT's own README for the
full writeup and the practical takeaway.

## Status

**Round 3 cycle budget (certified MDS 1.1, `mds-certifier`'s full
exhaustive run, 2026-11-09): MKII 9187 / MKI-DRAM 11797 / MKI-SRAM
10888** — up slightly from round 2's 9157/11752/10873; notably HIGHER
than round 1's own discrete-step design (8773 MKII), despite the
per-sample accumulator check being structurally the same shape (one
compare+branch) either way. The worst case is a sustained, long-running
randomized-fuzz scenario (block ~2000 of a continuous trigger-tail
search), not a simple parameter transition — plausibly because a
genuinely continuous rate means the "crossing" point drifts across all
4 group-local positions over time in a way a fixed-PERIOD design's own
always-the-same-position crossings couldn't, giving the certifier's
fuzzer more real scheduling variety to find a bad case in.

**Round 3 (2026-11-09):** fixed a hardware report that faster SPED made
the pass audibly re-loop more often instead of just playing faster —
`WINDOW_REMAIN` (the whole pass's duration budget) now drains by
`STEP_SIZE_Q8` each sample instead of a flat 1, so at `LOOP=127` the
pass plays exactly once at any speed, and at `LOOP<127` it still loops
internally but the whole pass still finishes in proportionally less/
more wall-clock time. That change exposed a genuine out-of-bounds
memory read in `mds-certifier`'s exhaustive fuzz run (`LOGICAL_POS` had
no wraparound bound, previously safe only because the pass length was
fixed) — also fixed, by wrapping `LOGICAL_POS` modulo `LOGICAL_BUFLEN`.
**Not yet tested on real hardware.**

**Round 1's own cycle budget** (certified, 2026-11-06): MKII 8773 /
MKI-DRAM 11324 / MKI-SRAM 10479 — over the real 16-track-safe ceiling
of 3000 (MKII), and noticeably higher than NUW-JT's own current 7136
MKII — the real cost of every one of the 4 inner positions needing its
own independent variable-rate PLAYBACK check, not just 1 of 4 (see the
Round 1 entry below for why). That worst case was found by the
certifier's own randomized search, not the deterministic parameter-
transition sweep that caught every other machine's own peak in this
project.

## Why this exists

NUW-JT's own round 3 (see that project's `DESIGN.md` §8-10) built a
variable-speed/reverse PLAYBACK knob (also called SPED) backed by a
full fixed-point Q12.8 phase accumulator — removed 2026-11-04 after a
hardware report ("the speed parameter just makes it sound like hell")
traced to a real 2x calibration error in the ramp-fraction derivation.
Rather than ship the fix at the time, the user pulled the knob out
entirely ("we might revisit").

This machine is that revisit — built as a **separate, distinct
instance** (not a replacement for NUW-JT, same A/B-comparison
convention as NFX-BO/NFX-B2) once NUW-JT's own engine had been
rewritten into a cheaper bulk-pass structure. Per direct user
instruction, this round deliberately narrows scope from the original
SPED's own design: *"not backwards vs forwards this time rather faster
vs slower"* — direction is explicitly out of scope (RVRS already
handles reverse, on the CAPTURE side only; PLAYBACK here always moves
forward), leaving only speed itself to control. Dropping direction
removes the entire reason the old design needed a continuous fixed-
point accumulator in the first place — see `DESIGN.md` §16 for the
full architectural reasoning.

## Round 1 (2026-11-06): built from NUW-JT's current (bulk-pass) build

Forked from NUW-JT's own latest `NUWJT.asm56k` (the just-shipped `do #8`
bulk-pass rewrite, see that project's `DESIGN.md` §14), with JITR's
whole per-trig derivation replaced by SPED's. Key design choice: SPED's
rate is **discrete, not continuous** — bucketed into 5 steps via a
plain threshold-compare chain on the raw `bipolar_q23` knob value, each
step a power-of-2 PERIOD (1/2/4/8/16 real samples per decimated
advance) with a small dead-zone around center landing exactly on
PERIOD=4 (the unchanged baseline rate). Halving/doubling PERIOD is
*exactly* one octave down/up — the same relationship real tape-speed-
vs-pitch has, not an approximation, and musically more honest than a
continuous linear rate would have been.

This keeps PLAYBACK's existing plain-integer decimated-advance counter
(`PB_POS`/`PB_DECIM_CTR`) completely intact — only its reseed threshold
(`PB_PERIOD_M1`) becomes a per-trig knob-derived value instead of the
hardcoded `DECIM_M1`, and the interpolation ramp's divide-by-period
step uses a register-sourced shift (`asr x0,a,a`) instead of a fixed
immediate. No fixed-point phase accumulator, no halve-before-mpy-then-
double dance — mechanically simpler than the original SPED design, not
just safer, because dropping direction removes the need for the
generality that design paid for. Verified the register-sourced shift
directly via probe before trusting it (same discipline that would have
caught NFX-BO's own real "portal to hell" bug in its live-DECIM-knob
attempt, where an analogous shift silently stayed hardcoded at one
site — see `DESIGN.md` §16).

**Real architectural consequence**: CAPTURE's own cadence stays a fixed
DECIM=4 stride (completely unaffected by SPED), so the bulk-pass loop's
`do #8` grouping is still correct for capture — but PLAYBACK's own
crossing can now land on any of the 4 group-local positions, not just
capture's own fixed one (the exact "two counters provably always in
lockstep" proof NUW-JT's own bulk-pass rewrite depended on no longer
holds for PLAYBACK specifically). So every one of the 4 inner positions
independently runs PLAYBACK's own variable-period check now, not just a
plain ramp — a real, necessary cost of supporting variable speed, not a
design regression.

Functionally verified via a new `probe_nuwts.cpp` (modeled on
`probe_nuwjt.cpp`): pack/unpack round-trip, reverse write-pairing (all
1536 words), SPED at both extremes (PERIOD=1 advances every real
sample; PERIOD=16 advances every 16th), both dead-zone boundaries
landing exactly where derived, loop wraparound at the fastest speed,
and the past-buffer-end physical wrap at the slowest — all pass.

Real cost (full exhaustive certifier): **MKII 8773 / MKI-DRAM 11324 /
MKI-SRAM 10479** — the real price of the architectural consequence
above (every position now doing a real variable-rate check, not just
1 of 4). Program grew to 728 words (from NUW-JT's own 553 — the extra
~175 words are the PLAYBACK block duplicated at 4 positions instead of
1). Properly certified and stamped via `mds_pack.py --certify`.

## Round 2 (2026-11-07): truly continuous rate

Round 1 shipped 5 discrete, octave-exact speed steps (4x slower, 2x
slower, unchanged, 2x faster, 4x faster), with a dead-zone around
center. Direct user feedback: *"can there be an 'infinitely' variable
range of speed? as it is there is only 0 = no speed change and double
and double-double both positive and negative."*

Rather than resurrect round 3's own old fixed-point design (removed
for a real calibration bug, see "Why this exists" above), the
accumulator stays as simple as a continuous rate allows by exploiting
one key fact: **capping `STEP_SIZE` at 255** (just under the Q8 "1.0
logical position per real sample" boundary) guarantees AT MOST ONE
integer-position crossing per real sample, no matter how fast SPED is
set. That means the existing single-compare-and-wrap structure (the
same shape round 1's own discrete countdown already used) stays
exactly as cheap and exactly as simple — it just counts a fractional
phase UP instead of an integer counter DOWN. No loop, no general
multi-step correction, ever.

`STEP_SIZE_Q8` is derived from the raw knob via the same bipolar GROW/
SHRINK branch-split NFX-BO's own BEND knob already uses (scale a
baseline value up one way, down the other), landing on `STEP_SIZE_Q8
=64` exactly at center and `16`/`~252` at the two extremes (4x slower/
faster). `RAMP_FRACTION` (the interpolation ramp's own divide-by-rate
step) is `STEP_SIZE_Q8<<15` — a single FIXED-immediate shift, since
only the value varies per trig, not the shift amount itself — simpler
than round 1's own register-sourced-shift design, not more complex.

Functionally re-verified via an extended `probe_nuwts.cpp`: the exact
baseline and both exact-extreme cases land precisely on their predicted
values, loop wraparound and physical-wrap still hold at the fastest/
slowest settings, and — the key new check — 7 SPED values spanning the
range give monotonically increasing, genuinely DISTINCT `PB_POS`
trajectories (not the identical-within-a-band results round 1's
discrete design would have given for several of them).

A real, explainable Q23-precision edge case was found and fixed along
the way: at the exact negative extreme, `|raw|` can only ever reach
`$7fffff` (Q23 can't represent a true `1.0`), so computing the rate via
a multiply there truncated `0.99999988*48` down to `47` instead of
`48`, landing `STEP_SIZE_Q8` one unit short (`17` instead of the true
minimum `16`). Fixed with the same exact-extreme special case this
project already uses for GATE/BEND/RVRS's own analogous `$800000`
boundary — skip the multiply entirely at that one exact input, use the
known-correct constant directly.

Real cost (full exhaustive certifier): **MKII 9157 / MKI-DRAM 11752 /
MKI-SRAM 10873** — see the Status section above for the comparison
against round 1's own discrete-step numbers. Certified and stamped via
`mds_pack.py --certify`.

## Parameters

| # | Knob | Range | What it does |
|---|------|-------|---------------|
| 1 | NBAL | unipolar | Neighbour blend: 0 = two tracks back (far), max = one track back (near). |
| 2 | GATE | bipolar | Shapes how much of the fixed window writing is allowed to run for (reading always covers the whole window). |
| 3 | REC | unipolar | 0 = pure fresh capture, ignoring whatever's already in the buffer. 1..~126 = the existing buffer's content is folded back in at a REC-scaled level, on top of a full-level fresh capture (an overdub, not a crossfade). ~127 disables writing entirely for that trig — pure replay of whatever's already captured. |
| 4 | RVRS | bipolar | Reverse-capture probability: one extreme always reverses this trig's pass, the other never does, center is a 50/50 coin flip. |
| 5 | MIX | unipolar | Dry/wet on what you hear — never affects what gets captured. |
| 6 | STRT | unipolar | Playback loop region's start point, as a fraction of the buffer. |
| 7 | LOOP | unipolar, squared | Playback loop region's length. Max = plays once with no time left to wrap; smaller values wrap more times within the trig's fixed-length pass, circularly past the buffer's own physical end if needed. |
| 8 | SPED | bipolar | Tape-speed/pitch-bend on PLAYBACK only. 0 (center) = same speed as recorded. Moving down slows playback (lower pitch); moving up speeds it up (higher pitch), continuously (round 2) across roughly a 4x slower to 4x faster range. Capture's own rate is never affected. |

**12-bit sample packing** is built in from the ground up (not a knob),
identical mechanism to NUW-JT's own: two 12-bit samples share each
24-bit buffer word, doubling effective capture length for the same
`DECIM` (currently 4, giving ~278ms). `DECIM` is a compile-time
constant in `NUWTS.asm56k`.

## Repo contents

- `BRIEF.md` — design brief (shared with NUW-JT)
- `DESIGN.md` — technical design notes, including SPED's own history
- `NUWTS.asm56k` — DSP56300 assembly source (the machine itself)
- `NUWTS.json` — machine manifest (parameters, transforms, memory/import declarations)
- `NUWTS.lod` / `NUWTS.mds` / `NUW-TS.syx` — build outputs (see Build below)
- `NUWTS.symbols.json` — label/address table from the assembler
- `NUWTS_icon.pbm` — the machine's 32x24 mono sprite: a tape-reel pictogram + "TS" label, see `../compose_icons.py`

Open items and hardware-test history, plus any test recordings, live in
`_authoring\resource\`, same as NFX-BO's.

## Build toolchain (external — not included in this repo)

Same three external tools as NFX-BO/NUW-JT, cloned as sibling directories:

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
python tools/mds_assemble.py NUWTS.asm56k --out NUWTS.lod --symbols-out NUWTS.symbols.json

# 2. package + certify-and-stamp real cycle costs: .json + .lod -> .mds
python mds-tools/tools/mds_pack.py NUWTS.json NUWTS.lod --format lod --certify -o NUWTS.mds

# 3. transfer-encode: .mds -> .syx
python mds-tools/tools/mds_to_syx.py NUWTS.mds --slot 2 -o NUW-TS.syx
```

(always use `mds-tools/tools/`, not the stale `MDS/tools/` copies;
adjust paths to wherever you clone each dependency; slot 2 is just
convention, so NUW-TS can sit alongside NUW-JT's own U01 for A/B
comparison)

Flash the resulting `NUW-TS.syx` to the Machinedrum over MIDI to install it
into a USR machine slot (U01–U16). Only install machine code from sources you
trust — it runs directly on the DSP.

## Not included

This repo deliberately excludes any disassembled/extracted Elektron factory
firmware content used during development (see `.gitignore`) — that material
is proprietary and isn't redistributable.

## License

TBD.
