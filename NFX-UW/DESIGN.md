# NFX-UW v1 — Technical Design

*Written 2026-11-04 to describe the actual implementation, sourced
directly from `NFXUW.asm56k`'s own header comment and body — same
current-state-reference approach as NFX-BO's own `DESIGN.md`. For the
reasoning trail (how REC/RVRS/12-bit packing were decided, the real
toolchain bug found along the way), see `TODO.md` / project memory, not
this file.*

**Status**: implemented, assembled, packed, cycle-checked, functionally
verified. `NFXUW.asm56k` + `NFXUW.json` build to `NFXUW.mds` →
`NFX-UW.syx` (494 program words, 1 import, structurally validated via
`mds_validate.js`, worst-case measured at **3948/3951 cycles**, 3
spare). Hardware-tested once already (round 1→2), which surfaced two
real bugs fixed in round 2 — see §3/§4 below. Round 3 (same day) added a
decoupled playback head with its own loop region (STRT/LOOP) plus a
variable-speed/reverse knob (SPED) — see §8/§9 for that architecture and
the cycle-budget fight it required. **SPED was then REMOVED, same day**,
after a hardware report found a real calibration bug in it — rather
than ship the fix and re-test, the user asked to pull the knob out
entirely ("we might revisit"); PLAYBACK kept its decoupled design and
loop region but was simplified down to a fixed-rate decimated advance —
see §10. Round 3c (same day) squared LOOP's knob curve — see its own
table row in §2. **Round 4 (2026-11-05)** filled the trailing-unused
8th slot with JITR (per-trig random offset on LOOP_START), found and
fixed a real, independent PLAYBACK out-of-bounds bug while designing
it, and closed a resulting cycle-budget overage down to the 3 spare
cycles above — see §11/§12. **Not yet tested on hardware since this
round.**

## 1. What this machine is, in one paragraph

A self-sampling overdub/freeze machine, architecturally unrelated to
NFX-BO's decaying bounce-train delay despite reusing several of its
patterns. Every trig runs a single unified pass through its own capture
buffer, once, in real time: at each position, read the existing content
(that becomes this instant's output), optionally blend it with a fresh
live capture and write the blend back, then advance. There is no repeat
engine, no decay, no RATE/BEND — looping/stuttering comes entirely from
how the user sequences trigs on the step grid, not from anything this
machine does on its own.

## 2. Parameters (8, per `NFXUW.json` — all slots used as of round 4)

| # | Name (JSON) | Transform | Default | What it does |
|---|------|-----------|---------|--------------|
| 1 | NBAL | `unipolar_q23` | 3 | Neighbour blend (far/near) — identical convex-combination formula to NFX-BO's. |
| 2 | GATE | `bipolar_q23` | 0 | Shapes how many LOGICAL samples writing is allowed for (not reading — reading always covers the whole fixed window). `missing = \|g\|*LOGICAL_BUFLEN`, `CAP_REMAIN = LOGICAL_BUFLEN-missing`; positive GATE also delays the write start by `missing*DECIM` real samples (`CAP_DELAY_REMAIN`). Moot at the default REC (below) since capture is disabled there regardless. |
| 3 | REC | `unipolar_q23` | 127 | 0 = pure fresh capture (old content's contribution is scaled to zero). 1..~126 = old content folded back at a REC-scaled level, summed with a full-level fresh capture, clamped. At/above the firmware's knob=127 raw value ($7f0000) writing is disabled entirely for the whole trig — pure replay (the default: a freshly-loaded machine just plays back whatever's in the buffer via STRT/LOOP, capturing nothing until REC is turned down). The scaled old-content contribution passes through a **feedback gate** first (`FEEDBACK_GATE`, ~-66dB) — magnitudes below it are forced to exact zero before being added, breaking the recirculating-residue problem a closed feedback loop with no forced decay would otherwise have (see §4a). |
| 4 | RVRS | `bipolar_q23` | 127 (= NEVER) | Reverse-capture probability — the exact mechanism NFX-BO uses (same LFSR, same `$800000`/`$7e0000` extremes, same `p_reverse=(1-RVRS)/2` formula), controlling the WRITE head's direction (`REVERSE_FLAG`/`LOGICAL_POS`). Independent of the playback head below — capture direction and playback direction are not the same thing. Only drawn when writing is enabled this trig (REC below the disable threshold). |
| 5 | MIX | `unipolar_q23` | 64 | Dry/wet on the OUTPUT only. Never affects what's captured — the write side always uses the pre-mix dry signal, same principle as NFX-BO. |
| 6 | STRT (displayed; "START" in comments) | `unipolar_q23` | 0 | Round 3. Playback loop region's start point, as a fraction of the buffer. |
| 7 | LOOP (displayed; "LOOP_LEN" in comments) | `unipolar_q23`, squared | 127 | Round 3. Playback loop region's length. 127 = the region spans the rest of the trig's fixed-length pass (plays once, no time left to wrap); smaller values wrap more times within that same fixed duration, wrapping circularly past the buffer's own physical end if the region crosses it. Floored to a minimum of one logical position. Playback always moves forward at the machine's fixed rate (see §10) -- no speed/reverse control for now. **Round 3c (2026-11-04)**: the raw fraction is squared before scaling by `LOGICAL_BUFLEN` (same proven idiom as NFX-BO's own BEND shrink-branch squaring) -- direct user request for finer resolution near the short-loop end, where small absolute length changes have the biggest (pitch-like) perceptual effect, at the cost of coarser resolution near the long-loop end. This moves the knob's own reference points off the original linear design conversation's examples (e.g. knob~64 now gives ~1/4-length, not ~1/2) -- a deliberate, informed tradeoff, not an oversight. |
| 8 | JITR | `unipolar_q23` | 0 | Round 4 (2026-11-05). Random per-trig offset applied to `LOOP_START`, drawn fresh from the same persistent `RNG_STATE` RVRS's own draw advances, reused directly as a BIPOLAR Q23 fraction (any pseudo-random 24-bit pattern is already a valid signed Q23 value, no masking needed, unlike RVRS's own unipolar masked draw). Gated on `JITR!=0` so the default (0) pays exactly zero extra cost — confirmed `JITR=0` gives the bit-exact un-jittered `LOOP_START` on every trig, never an approximation. Wraps circularly into `[0, LOGICAL_BUFLEN)` via an explicit compare+add/sub, same style as LOOP's own wrap. See §11 for the mix-depth tradeoff this needed to clear its cycle budget. |

(JSON param names are capped at 4 characters — same constraint that
renamed NFX-BO's DECIM to DECM. "START"/"LOOP_LEN" are used throughout
this file's and `NFXUW.asm56k`'s comments for readability; only the
actual machine-visible knob labels are the truncated forms. A round-3
8th param, SPED/"SPEED", was removed 2026-11-04 -- see §10 -- and its
freed slot was filled by JITR in round 4 -- see §11.)

## 3. 12-bit sample packing

Two signed 12-bit samples share one 24-bit Y-memory word, doubling
effective buffer capacity: `LOGICAL_BUFLEN = BUFLEN*2 = 3072` logical
positions instead of NFX-BO's 1536 words, independent of `DECIM`. A
logical sample index replaces a plain word index throughout:
`word-index = logical>>1`, `sub-phase = logical&1` (0=top 12 bits,
1=bottom 12).

- **Quantize**: `asr #12,a,a` — the top 12 bits, already correctly
  sign-extended by the arithmetic shift.
- **Pack**: mask each quantized half to `#$fff`, shift the first left
  12 (`asl #12,a,a`) to position it, `add` the second (the two 12-bit
  fields never overlap, so `add` and `or` are equivalent here).
- **Unpack**: top half — `asr #12,b,b` (sign-extends from the word's
  own top bit) then, via a DIFFERENT register, `asl #12,a,a` (rescales
  back to Q23 range; the bottom 12 bits are now zero — this is the
  quantization noise floor, the SP-1200/S900-style character this
  packing trades for 2x capacity). Bottom half — `asl #12,b,b` first
  (repositions bits 11..0 up into 23..12, discarding the top half), then
  the same sign-extend/rescale pair.

**Critical toolchain fact this design depends on** (see
[[reference_dsp56300_sign_overflow_quirks]], Quirk 3, for the full
writeup — found via direct probe BEFORE this machine's capture/playback
loop was written, same discipline as every other new idiom in this
project): two consecutive immediate-shift instructions naming the SAME
register silently merge into one NET shift (`asr` counts negative, `asl`
positive) regardless of what unrelated instructions sit between them —
confirmed via `dsp56300/cyclecheck/sign_test/shift12_isolate*.asm56k`.
Every unpack sequence in `NFXUW.asm56k` therefore **alternates
registers** for each shift in a pair (shift on `b`, `move b1,a`, shift
on `a`) — never two shifts in a row naming the same register.
Same-direction chains (two `asr`s, two `asl`s) compound correctly on
their own and don't need this.

**Write pairing**: each decimated event positions its OWN quantized
value into its correct 12-bit slot first (top if sub-phase=0, bottom if
sub-phase=1 — this part is direction-independent), then separately
decides whether it's the first or second half of its word-pair:
`first_of_pair = (sub_phase == REVERSE_FLAG)`. The first event of a pair
is stashed in `PENDING_HALF` (memory not touched yet); the second is
added to it (the two positioned halves never overlap in bits, so `add`
is equivalent to `or`) and the complete word is written.

**Real bug, found 2026-11-04 via a hardware report** ("feedback tends to
only kick off on reverse"): an earlier version hardcoded "sub-phase 0 is
always first/stashed/top, sub-phase 1 is always second/written/bottom"
— true for FORWARD traversal (position 0,1,2,3,... always visits
sub-phase 0 before sub-phase 1 within a pair), but wrong for REVERSE:
`LOGICAL_BUFLEN` is even, so the reverse start point
(`LOGICAL_BUFLEN-1`) is ODD — the very first event of a reverse pass
has sub-phase 1, encountered before its sub-phase-0 partner. The old
code wrote a garbage top-half (from `PENDING_HALF`'s post-reset value
of 0) into the first word touched, and every subsequent pair was
misaligned by one word throughout the whole reverse pass. The
`first_of_pair` formula above replaces the hardcoded assumption and
gives identical correct results in both directions — verified via
`dsp56300/cyclecheck/probe_nfxuw.cpp`: a full-window capture with a
constant input packs every one of the 1536 words identically in both
forward and reverse.

## 4. The unified pass: one position, read-before-write

Unlike NFX-BO (where capture's write-head and bounce's read-head are
independent, running on separate clocks across separate trigs),
NFX-UW's read and write are the SAME pass, driven by one position
counter (`LOGICAL_POS`). At each decimated step: read the existing half
at the current position (unpack it — this becomes the output target for
the interpolator), then — if writing is enabled and still within GATE's
allowed length — blend it with a fresh capture and write the result
back to that SAME position, then advance. Reading never waits on
writing being enabled; a REC=127 (pure replay) trig runs the identical
read/output path, just skipping the blend-and-write step entirely.

`REVERSE_FLAG` controls the shared direction for the WHOLE pass (both
read and write move together, since they are the same pass): forward
starts at logical 0 and counts up; reverse starts at `LOGICAL_BUFLEN-1`
and counts down. A trig that captures in reverse therefore also *plays
back* in reverse during that same trig's monitoring — a side effect of
the unified-pass design, and a reasonable one given the brief's own
explicit goal of "creating unpredictability."

**No separate `CAP_LEN_FINAL`/valid-length tracking**: the pass always
runs the full fixed `WINDOW_SAMPLES` duration (`LOGICAL_BUFLEN*DECIM`
real samples) regardless of GATE — GATE only ever shapes what gets
WRITTEN, never how long reading continues (same "GATE shapes WHAT, never
WHEN" principle as NFX-BO). Any position never yet written simply reads
back as silence, since `INIT` clears the whole buffer and an all-zero
pack is all-zero either way — no special-casing needed for "nothing
recorded here yet."

**Ending**: when the fixed window closes (`WINDOW_REMAIN` reaches zero),
the pass stops abruptly — there is no decay mechanism to taper into, so
this is a plain one-shot cutoff at the sample's natural end, the same
way any ordinary sample player stops when the sample ends.
`WINDOW_SAMPLES` is an exact multiple of `DECIM` by construction, so in
the normal case this lands exactly on a decimated-step boundary, not
mid-ramp.

**Real off-by-one, found alongside the reverse-pairing bug above**: the
window-close check was `ble` (branch if `WINDOW_REMAIN<=0`), which ends
the pass on the SAME sample where the countdown hits exactly zero —
that sample is also the final decimated event's sample, so it never
got to run. This silently dropped the very last word of every capture
(word 1535 in forward mode; only caught because the reverse test's
`word[0]` — the equivalent last-touched word in reverse order — came
back wrong first). Fixed by using `blt` (strictly negative) instead:
the pass now runs the full `WINDOW_SAMPLES` samples, letting
`WINDOW_REMAIN` reach exactly 0 on a still-valid sample and only ending
once it goes negative.

### 4a. The feedback gate

REC's overdub is a closed feedback loop with no forced decay — unlike
NFX-BO, there's no DCAY guaranteeing eventual silence. Two things can
make that loop audibly runaway rather than settle: plain near-silent
residue that never truly reaches zero, and the 12-bit quantization's
own rounding bias (`asr` rounds toward -infinity for negative values
but toward zero for positive ones — not symmetric), which can
accumulate a slow DC-like drift across many re-quantization passes of
the same recirculating signal. Found via a hardware report ("with REC
at 0 it doesn't overwrite the capture as expected, the feedback stays"
/ "feedback tends to only kick off on reverse" — the latter turned out
to mostly be the write-pairing bug above, but the feedback mechanism
itself is real regardless).

Fix: before adding the scaled old-content contribution to the fresh
capture, its magnitude is compared against `FEEDBACK_GATE` (`$001000`,
~-66dB); below that, it's forced to exact zero. This breaks the
recirculation of anything quiet enough that it should have decayed to
silence, while leaving genuinely audible feedback untouched. Provisional
value — revisit by ear once this is confirmed on hardware.

## 5. Playback interpolation

Same decimated-hold-with-linear-interpolation approach as NFX-BO: a
hard jump every `DECIM` samples is audibly harsh, so `HELD_WET` ramps
toward the latest target every sample (nudged by `INTERP_STEP`), with
the step recomputed as `(target-current) >> DECIM_SHIFT` — subtracting
in the full accumulator first and shifting once at the end, not
shifting each operand independently (the double-truncation form of this
was a real, shipped bug in NFX-BO that produced an audible ring on quiet
signals; this file never had that bug, having been written after that
lesson).

## 6. Memory layout (Y, relative to r6)

```
Y+1..5     NBAL GATE REC RVRS MIX (params)
Y+6/7      STRT LOOP (params, round 3; were Y+7/Y+8 before SPED's
                            removal freed Y+6)
Y+8        unused (was SPED, removed -- see §10)
Y+9        TRACKMEM_BASE
Y+10       PHASE (0=IDLE 1=ACTIVE)
Y+11       TRIG_FLAG
Y+12       LOGICAL_POS      current logical sample index -- the WRITE
                            head only, as of round 3 (see §8; no longer
                            shared with reading)
Y+13       CAP_REMAIN       logical samples left for which writing is
                            still allowed this trig (GATE-derived)
Y+14       DECIM_CTR        real-sample countdown between decimated steps
Y+15       CAP_DELAY_REMAIN real samples to wait before writing starts
                            (GATE>0 case -- delays the WRITE only)
Y+16       WINDOW_REMAIN    real samples left in the fixed-duration pass
Y+17       REVERSE_FLAG     the WRITE head's direction (capture only,
                            round 3 -- no longer the playback direction too)
Y+18       RNG_STATE        24-bit Galois LFSR state (same mechanism as
                            NFX-BO's RVRS), seeded nonzero in INIT
Y+19       PENDING_HALF     stashed quantized half awaiting its pair
Y+20       HELD_WET         continuously-ramping interpolated output
Y+21       INTERP_STEP      per-sample increment toward the latest target
Y+22       CAPTURE_ENABLED  0/1, latched once per trig from REC
Y+23       REC_SCALE        Q23 fraction scaling old content's
                            contribution to the write-back blend
Y+24       PB_POS           PLAYBACK's own read position, in PLAIN
                            logical units (not fixed-point -- see §10
                            for why that simplified after SPED's removal)
Y+25       PB_DECIM_CTR     real-sample countdown before PB_POS advances,
                            same shape as capture's own DECIM_CTR
Y+26       unused (was RAMP_FRACTION, Q23 -- now a true compile-time
                            constant loaded as an immediate at the
                            retarget site, never latched here)
Y+27       LOOP_START       STRT's value in plain logical-position
                            units, latched once per trig
Y+28       LOOP_LEN         LOOP's value in plain units, floored to a
                            minimum of one logical position. Kept for
                            reference only -- PLAYBACK itself reads
                            LOOP_END (Y+29) instead
Y+29       LOOP_END         = LOOP_START + LOOP_LEN, latched once per
                            trig (not recomputed per sample)
Y+30       unused (was LAST_READ_POS, a crossing-detection sentinel the
                            decimated-advance redesign no longer needs)
```

Notably absent vs. NFX-BO: no `GAP_REMAIN`/`GAP_CUR`/BEND math, no
`DCAY_MULT`/`ACCUM_LEVEL`/`REPEATS_FIRED`/`MAXREPEATS` safety net —
there is no restart loop to safety-cap, since playback is a fixed
one-shot window, not a decaying train.

## 7. Cycle budget

Round 2 worst case: **3139/3951** (812 spare). Round 3's decoupled
playback engine (with its original variable-speed SPED knob) pushed
this much higher before optimization — see §9 for that story. Final
state, after SPED's removal and the resulting PLAYBACK simplification
(§10), measured via `dsp56300/cyclecheck/cyclecheck_nfxuw_v1.cpp`:
**3853/3951** (98 spare) — comfortably more headroom than ANY point in
round 3's SPED-enabled history had, confirming the simplification was
a genuine win, not just a feature cut. Re-run this harness after any
change to `DECIM`, the pack/unpack layer, or anything in the per-sample
loop body.

## 8. Round 3: decoupling playback from capture

Rounds 1-2 shared ONE position (`LOGICAL_POS`) between reading (what
you hear) and writing (what gets captured) — every trig's single pass
did both at once, at the same fixed `DECIM`-derived rate. The user
wanted a genuinely different kind of control on top of that: a
tape-style variable-speed/reverse playback knob (SPED), plus a
sampler-style loop region (STRT/LOOP) — both **decoupled from
capture**, so capture keeps running at its own fixed, pristine rate
while playback becomes an independent head scrubbing through whatever
is currently in the buffer.

**Capture (write) engine** — unchanged in spirit from round 2.
`LOGICAL_POS`/`REVERSE_FLAG`/`CAP_REMAIN`/`CAP_DELAY_REMAIN` all work
exactly as before. The REC blend's "old content" now needs its own
dedicated read at the WRITE position (previously this doubled as the
audible output target; it no longer does) — one extra unpack per
decimated write-step, same mechanism as before.

**Playback (read) engine** — new. A fixed-point phase accumulator
(`READ_PHASE`, Q12.8) adds a signed `STEP_SIZE` every real sample — not
gated by `DECIM_CTR`, since SPED can make playback faster than
capture's own rate, so this needs full sample-rate resolution.
`STEP_SIZE` is derived once per trig from SPED via a single shift (no
division needed — `DECIM` being a fixed power-of-two makes "divide by
it" just a shift). Each real sample: add `STEP_SIZE` to `READ_PHASE`;
wrap into `[LOOP_START_FP, LOOP_END_FP)` if needed (a single
correction, not a full modulo loop — see the known v1 limitation
below); if the new integer position differs from `LAST_READ_POS`,
fetch that position's unpacked value as a fresh interpolation target
and recompute `INTERP_STEP` so `HELD_WET`'s existing ramp mechanism
(unchanged from round 2) automatically matches however many real
samples SPED implies between crossings.

At SPED=0, `STEP_SIZE=0`, so `READ_PHASE` never changes integer part —
`HELD_WET` ramps to and then holds exactly one sample: a frozen-scrub
state, by design, not a bug.

**Known v1 limitation**: the loop-region wrap is a single correction
(`phase -= END; phase += START`, or the mirror for the low side), not a
true modulo. This is only valid as long as `|STEP_SIZE|` doesn't exceed
the loop region's own length in one sample — an extremely short LOOP
combined with a very fast SPED could, in principle, violate this and
skip past the wrap instead of landing inside it. Not solved here;
worth another look if LOOP is ever allowed to go shorter or SPED faster
than today's clamp.

**Explicitly out of scope for round 3**: grain-table-style playback
(floated as a possible future, separate machine) and NFX-BO's own
12-bit sampling backport (a separate, later round, to keep each
codebase's bugs easy to isolate).

## 9. Round 3's cycle-budget fight

Adding the decoupled playback engine on top of round 2's already-tight
budget pushed the worst case from 3139/3951 up to **5259/3951** at the
roughest point measured — nearly 1.3x over. Getting back under budget
took several real, measured fixes, in order, each verified against the
actual emulator rather than assumed from instruction-count reasoning:

1. **A test-harness bug, not a real one**: the cycle-check's own
   `stepSize` default was `0x2000` (intended as "~0.25 in Q8"), but
   `0x2000` in Q8 (256=1.0) is actually 32.0, not 0.25 — a 128x error
   that inflated EVERY scenario to the absolute worst case. Fixed to
   `0x40` (64, the actually-intended 0.25).
2. **Register caching for per-block constants** (`STEP_SIZE`,
   `LOOP_START_FP`, `LOOP_LEN_FP`, `RAMP_FRACTION` into `n2`/`n4`/`n5`/
   `r0`) instead of re-reading Y-memory 32 times/block — the same
   hoist-out-of-the-hot-loop principle already used for NBAL/MIX.
3. **A "fast path" branch-skip attempt was tried and reverted** after
   measuring it made things WORSE (5259→... higher), not better — the
   added compare+branch on the "normal" path outweighed any savings on
   the "fast" one. Explicit lesson: DSP56300 cycle-cost intuitions must
   be measured, not assumed — this was the second time this project hit
   that lesson (the first being NFX-BO's own `do`-loop-vs-unrolled-LFSR
   surprise).
4. **Halved SPED's max achievable rate** (the SPED→STEP_SIZE derivation
   shift changed from `#15` to `#16`) — directly, predictably halves the
   worst-case retarget frequency. Reduced worst case from 5259 to 4588.
5. **Register residency for READ_PHASE/LAST_READ_POS across the whole
   block** (`n6`/`n7`, read from Y-memory once before the sample loop,
   written back once after) instead of round-tripping through Y-memory
   3-4 times EVERY sample. 4588→4466.
6. **Caching `LOOP_END_FP` directly instead of recomputing it from
   START+LEN every sample**: a forward-moving pass takes the "at/past
   start" branch on nearly every sample (position only dips near start
   once per lap), so that recompute was effectively running every
   sample, not rarely as first assumed. Latching `LOOP_END_FP` once per
   trig (Y+29) and expressing both wrap directions as plain adds against
   the two cached bounds removed 4 instructions from the hot path.
   4466→4339.
7. **A genuinely redundant `tst a` after `and #>1,a`**, found by directly
   probing (not assuming) whether `and`'s own condition-code output
   survives an intervening plain `move` — confirmed via
   `and_flags_direct_test.asm56k` that it does, in all three ways this
   file depends on it. Removed from all four sub-phase-check sites.
   4339→4054 (combined with item 8 below, measured together).
8. **Forward/backward-specialized loop bodies**: PLAYBACK's wrap-check
   was running BOTH the "below start" and "at/past end" comparisons
   every sample even though only ONE is ever reachable for a given pass
   (direction is fixed for the whole pass, and the read head always
   starts exactly at `LOOP_START_FP`). Branching once per `RENDER` call
   (not per sample) to one of two separate hardware `do` loops
   (`RENDER_LOOP_FWD`/`RENDER_LOOP_BWD`), each containing only its
   relevant single check, removes the unreachable half from the
   executed instruction stream entirely — something no per-sample
   branch could achieve, since every iteration of one shared loop runs
   identical code.
9. **Capture logic inlined (duplicated) into both loop copies instead
   of called via a shared subroutine**: an intermediate version called
   the capture/write-pairing logic via `bsr`/`rts` from both FWD/BWD
   copies specifically to avoid duplicating that larger, more delicate
   logic — but measured `bsr`/`rts` overhead on this 8-times-per-block
   path as a real, worthwhile cost to remove once it was the next
   biggest lever. The two inlined copies are a verbatim copy-paste of
   logic already verified correct in round 2 (not independently
   re-derived), so the "copies silently drift apart" risk this was
   originally trying to avoid is low — but any FUTURE change to capture
   logic must now be made in both places. 4054 final.
10. **A `STEP_SIZE_MAX` clamp**, applied once per trig (not per sample,
    so essentially free): even after every fix above, the full
    +/-127 range the `#16` shift alone allows still measured
    4054/3951. Rather than narrow SPED's whole range further (halving
    the shift again would have cut the top speed to ~1x, undoing most
    of the point of the knob), a small clamp to +/-80 (~1.25x) buys back
    just enough margin — tuned by direct measurement, not calculated in
    one step, to land comfortably (not barely) under budget: 3951→3928
    at a clamp of 96, then 3928→**3893** at 80, the shipped value.

**A real, separate bug this process surfaced and fixed**: the default
SPED knob value (originally 80) had been calibrated assuming the `#15`
shift (where 80 landed exactly on `STEP_SIZE=64`, the old fixed rate).
Once the shift changed to `#16` for the budget fix above, 80 silently
started producing `STEP_SIZE=32` — HALF the intended default rate —
and nobody had re-derived it. Caught while writing this section, not by
a test; fixed by recalculating the default for the shift actually
shipped: 96 (see §2).

**Functional correctness was re-verified after all of this**, not just
cycle-counted — `dsp56300/cyclecheck/probe_nfxuw.cpp` gained tests
confirming: the capture logic's inlined BWD copy produces byte-identical
results to the FWD copy's already-proven-correct output (the reverse
write-pairing check from round 2, re-run through `RENDER_LOOP_BWD`
specifically); SPED=0 freezes; positive/negative SPED reads forward and
backward; and — the highest-risk area, given two prior boundary bugs
this session already — the loop region's wraparound stays strictly
inside `[LOOP_START_FP, LOOP_END_FP)` over 100 blocks (several full
laps) in BOTH directions. All pass.

## 10. SPED removed (same day, 2026-11-04): a real calibration bug,
## then a design simplification on top

Hardware test of the §8/§9 build: user reported "the speed parameter
just makes it sound like hell" and "at 0 speed nothing happens." The
second part was expected behavior (0 = frozen, by design, a deliberate
accepted consequence of unifying speed+reverse onto one axis) — but the
first pointed at something real.

**Root cause, found before any fix was shipped**: `RAMP_FRACTION`
(§8's Y+26) was derived as `|SPEED_raw|` directly — wrong two ways.
First, it used the knob's *unclamped* raw magnitude, not the actual
(clamped) `STEP_SIZE` — at exactly the knob positions a user exploring
"speed" would reach, the ramp fraction could be several times larger
than the real crossing rate implied. Second, even ignoring the clamp,
the scale itself was off by exactly 2x: `RAMP_FRACTION` needs to equal
`1/N` where `N` is the number of samples between position crossings
(`256/|STEP_SIZE|` in Q8 terms) — i.e. `|STEP_SIZE|<<15` in Q23 units —
but `|SPEED_raw|` works out to `|STEP_SIZE|<<16`, one shift too many.
Sanity check that confirmed it: at the default knob (`STEP_SIZE=64`,
the machine's old fixed rate), the correct `RAMP_FRACTION` is
`64<<15=$200000` (0.25) — exactly the ratio this machine's
interpolation has always used (`1/DECIM`) — while the buggy code gave
`$400000` (0.5), double that. `INTERP_STEP` (`= diff*RAMP_FRACTION`)
landing at 2x the correct fraction every sample means `HELD_WET`
overshoots its target and gets yanked back on the next retarget instead
of landing smoothly — audible as harshness across the range, worse at
the clamped extremes where the first bug compounded it further.

**The fix was derived and written, but not what shipped.** Rather than
ship-and-retest, the user asked directly: *"do me a favour, just
completely remove that dial and it's functionality — we might
revisit."* SPED's slot (Y+6) was removed from `NFXUW.json`; STRT/LOOP
moved down to fill it (Y+6/Y+7), leaving Y+8 as the trailing-unused
slot.

**With no more variable rate to support, PLAYBACK's whole fixed-point
design stopped earning its keep.** Round 3 built `READ_PHASE` as a
Q(12.8) phase accumulator specifically because SPED let the crossing
rate vary continuously — direction-specialized forward/backward loop
bodies, a `STEP_SIZE_MAX` clamp, the `RAMP_FRACTION` machinery above,
all existed to serve that generality. With the rate now ALWAYS exactly
`DECIM`'s own cadence, forward only, that generality was pure overhead
on the 3-out-of-4 samples that never cross a position boundary — so
PLAYBACK was redesigned down to a plain decimated-advance counter
(`PB_POS`/`PB_DECIM_CTR`), structurally identical to capture's own
`LOGICAL_POS`/`DECIM_CTR` pattern, just independent (to keep the
STRT/LOOP loop-region feature). This ALSO let the loop-region wrap
simplify: since `PB_POS` only ever advances by a clean `+1` and is
always kept in-range beforehand, "if `PB_POS>=LOOP_END`, set
`PB_POS=LOOP_START`" is exact — no subtraction needed (the old
fixed-point version needed a general correction because a variable
`STEP_SIZE` could overshoot by an arbitrary amount; a fixed `+1` step
never can).

**Net effect measured, not assumed**: worst case dropped from
3893/3951 (58 spare) to **3853/3951 (98 spare)** — removing a knob and
simplifying its supporting machinery recovered real cycle margin on
top of the feature cut itself, confirming the fixed-point design really
had been pure overhead once the variable rate it served was gone.
(One intermediate step, worth recording: a smaller, surgical fix —
replacing a per-sample register load with `add #>imm,a` directly, since
`STEP_SIZE` was now a true compile-time constant — was tried FIRST and
only recovered 3 cycles. The bigger architectural simplification was
the real lever; verify `add #>imm,a` itself via direct probe
(`add_imm_test.asm56k`) before reusing that specific idiom elsewhere.)

**Functional correctness re-verified again**, specifically for the new
decimated-advance design (not a carry-over, genuinely new code):
`probe_nfxuw.cpp`'s tests now confirm `PB_POS` advances by exactly 1
every `DECIM`(4) real samples (160 samples → `PB_POS=40`, exact), and —
still the highest-risk area — the loop region's wraparound stays
strictly inside `[LOOP_START, LOOP_END)` over 100 blocks (several full
laps). Both pass.

## 11. Round 4 (2026-11-05): JITR, and a real PLAYBACK bug found while designing it

User, after confirming the SPED removal and LOOP's squared curve both
landed well: asked what an 8th knob could be, then confirmed "go for
JITR" on the recommendation of a random per-trig offset on
`LOOP_START` — a small amount of position jitter, musically similar to
the kind of humanize/jitter controls found on sampler-style effects,
distinct from anything NFX-BO or NFX-UW already does.

**A real, independent bug found first, while designing this feature
(not caused by it):** `PLAYBACK`'s loop region can legitimately extend
past `LOGICAL_BUFLEN` — the design doc has always claimed circular
wrap past the buffer's own physical end (see LOOP's own §2 row) — but
`PB_POS` was used DIRECTLY as the buffer address with no modulo wrap
back into `[0, LOGICAL_BUFLEN)`. This risked reading/writing outside
this track's own buffer whenever `STRT` sat near the buffer's end with
a sizable `LOOP` value pushing `LOOP_END` past it — a combination JITR
makes far more likely to hit in practice (it perturbs `LOOP_START`
randomly every trig, so a region that happened to sit safely inside
the buffer on one trig can land right on this edge on the next).
**Fixed** with an explicit compare+subtract at a new `PB_ADDR_OK`
label, right after the loop-region wrap and before the word-index
computation — not a bitmask, since `LOGICAL_BUFLEN=3072` isn't a power
of 2. Confirmed via a new Test 7 in `probe_nfxuw.cpp`: a sentinel word
placed just past this track's own buffer stays untouched even when the
loop region is deliberately pushed past the buffer's end over 100
blocks.

**JITR itself**: drawn once per trig, gated on `JITR!=0` (the default)
so it costs nothing when unused — measured, not assumed: running the
draw unconditionally pushed worst case to 3981/3951 even at `JITR=0`,
confirming the gate was worth adding. Reuses RVRS's own persistent
`RNG_STATE` rather than a separate generator (one shared, continuously-
advancing LFSR sequence feeding two independent per-trig draws), and
reuses the raw mixed bits DIRECTLY as a signed bipolar Q23 fraction —
no masking needed, unlike RVRS's own unipolar draw, since any
pseudo-random 24-bit pattern already IS a valid Q23 value. The jitter
offset (`random_bipolar * JITR_fraction * LOGICAL_BUFLEN`) is added to
`LOOP_START` and wrapped back into range with the same explicit
compare+add/sub style as every other wrap in this file.

## 12. Round 4's cycle-budget fight: gating alone wasn't enough

Gating JITR's draw got the *default* case (JITR=0) back under budget,
but the TRUE worst case — RVRS's own general-value draw AND JITR's
draw BOTH firing on the same fresh trig, found only once a dedicated
`cyclecheck_nfxuw_v1.cpp` scenario was added to actually exercise that
combination — still measured 3988/3951, 37 over.

Unlike RVRS's own draw (which feeds a probability comparison and needs
its full, true 8-step Galois mix to keep that probability honest),
JITR has no statistical requirement at all — it only needs to "look
different each trig" for a purely creative effect. Closed via two
rounds of measurement, both confirming this project's own established
finding (NFX-UW round 3, NFX-B2 §4) that **branches, not instruction
count, are the expensive resource on this emulator**:

1. Cutting RVRS's own 8-step CONDITIONAL mix shape down to 4, then 2
   steps (still gated on the shifted-out bit via `bcc`, same shape,
   just shorter) only recovered ~4-5 cycles per step cut — diminishing
   returns, still 7 over at 2 steps (3958/3951).
2. Switching to a 2-step UNCONDITIONAL mix instead (`lsl`+`eor` every
   time, not gated on the carry at all — not a true Galois LFSR step
   any more, since the tap no longer depends on the bit shifted out,
   but JITR never needed that correctness) got under budget for the
   first time (3950/3951) — removing the branch entirely saved more
   than shortening the branching chain had. Still only 1 spare cycle,
   too thin to trust given this project's OWN same-day lesson from
   NFX-B2's hardware failure (see that project's `DESIGN.md` §7) that a
   wafer-thin margin on brand-new code is a real, not theoretical,
   risk. Cut to a single unconditional step for a final **3948/3951 (3
   spare)**.

3 spare cycles is thin by this project's historical standards, but the
new code it's protecting is structurally much simpler than NFX-B2's
case (a handful of plain arithmetic instructions, no novel addressing
patterns, no first-of-its-kind read-modify-write shape) — lower risk
per spare cycle than NFX-B2's 12-bit backport was. Re-run
`cyclecheck_nfxuw_v1.cpp` after any further change near JITR's draw or
anything else in `RENDER`'s fresh-trig preamble.

**Functional verification**: a new Test 8 in `probe_nfxuw.cpp`
confirms `JITR=0` gives the exact (not approximately-zero) un-jittered
`LOOP_START` across 20 fires; `JITR=127` at a fixed `STRT` produces
genuinely varying `LOOP_START` across 20 fires (not frozen); and 100
fires at both `STRT` extremes with max `JITR` all land inside
`[0, LOGICAL_BUFLEN)` — the wrap-around edge, both directions.

**A test-methodology trap worth recording, same family as this
project's own recurring lesson**: the first version of Test 8b showed
`JITR=127` producing an IDENTICAL `LOOP_START` on every single fire —
looked exactly like a frozen/broken draw. Root cause was the test's
own `setupTrackBase` helper, which simulates "a fresh param block" by
zeroing the WHOLE persistent-state range on every call, including
`RNG_STATE` — on real hardware that word is seeded once in `INIT` and
NEVER reset between trigs, but the test was unintentionally resetting
it to 0 before every single fire, and this round's own new
UNCONDITIONAL mix step happens to have an exact fixed point at seed 0
(zero always maps to the same next value). Fixed by saving/restoring
`RNG_STATE` around each test fire, and explicitly re-seeding it to a
known-nonzero value before the test block starts (simulating `INIT`'s
own nonzero-seed guarantee) rather than trusting whatever earlier
tests happened to leave behind. Once fixed, both parities came back
correct. **Not yet tested on real hardware.**
