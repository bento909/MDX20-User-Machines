# NFX-BO v1 — Technical Design

*Rewritten 2026-11-04 to describe the CURRENT implementation (round 12),
sourced directly from `NFXBO.asm56k`'s own header comment and body — not
the pre-implementation planning document this used to be. For the full
round-by-round history of how it got here (bugs found, ideas tried and
dropped), see `TODO.md` (`_authoring\resource\`); that stays the
authoritative chronological record. This doc is a snapshot of "how it
works now," and can drift out of sync again if a future round edits the
code without touching this file — check `NFXBO.asm56k`'s header against
this doc before trusting either blindly.*

**Status**: implemented, assembled, packed, cycle-checked. `NFXBO.asm56k`
+ `NFXBO.json` build to `NFXBO.mds` → `NFX-BO.syx` (453 program words, 1
import, structurally validated via `mds_validate.js`, worst-case measured
at **3267/3951 cycles**, 684 spare). Not yet confirmed on real hardware.

## 1. Machine declaration

```json
{
  "id": "org.mathsmechanic.nfxbo",
  "display_name": "NFX-BO",
  "category": "NFX",
  "short_label": "BO",
  "neighbour": true
}
```

`neighbour: true` is required to read the "one back"/"two back" buffers
NBAL blends between. `stereo_pair` is not set (not needed — nothing here
is stereo-aware). Retrigger behavior uses the firmware default
(`restart`): the firmware's own anti-click engine fades the previous
block's audio out before calling `TRIG`, so cancelling a still-playing
train is click-free "for free" — `TRIG`/`RENDER` only need to reset this
machine's *own* internal state (phase, pointers, gap), not worry about
the audible jump itself.

## 2. Parameters (7, per `NFXBO.json`)

| # | Name | Transform | Default | What it does |
|---|------|-----------|---------|--------------|
| 1 | NBAL | `unipolar_q23` | 0 | Neighbour blend: 0 = two-back (far), max = one-back (near). Linear crossfade, `two_back*(1-NBAL) + one_back*NBAL`, computed as a convex combination (see §6) so it can't overflow regardless of how different the two inputs are. |
| 2 | GATE | `bipolar_q23` | 64 (center = full window) | Shapes the capture window: `g>0` delays the start by `g*BUFLEN` words (keeps the tail); `g<0` stops early at `(1+g)*BUFLEN` words (keeps the head). Both extremes converge to capturing nothing. Never affects *when* anything happens, only *what* gets kept — see §4. |
| 3 | RATE | `unipolar_square_q23` | 32 | Initial gap before repeat 1, counted from the trig itself: `gap = RATE²*GAP_RANGE + GAP_FLOOR`, clamped to `[GAP_FLOOR, GAP_CEIL]`. |
| 4 | BEND | `bipolar_q23` | 64 (center = steady) | Per-repeat gap multiplier. Shrink branch (negative): `|BEND|` is first scaled by 0.625 then squared before scaling the gap down by up to 0.5 per repeat (compounds — exponential speedup). Grow branch (positive): plain linear scale, up to +0.5 per repeat. Clamped to `[GAP_FLOOR, GAP_CEIL]` every restart. |
| 5 | DCAY | `unipolar_q23` | 80 | Per-repeat level survival, scaled to a 0.99 ceiling (`DCAY_MULT = DCAY * 0.99`, `$7eb852` in Q23). Hand-rolled once-per-restart multiplier, not the firmware's native per-sample `decay` transform (wrong grain for an event that only changes once per bounce). Skipped entirely on the pass that fires repeat 1 (the pristine capture) — compounding starts from repeat 2 onward. |
| 6 | MIX | `unipolar_q23` | 96 | Dry/wet. Snaps to exactly full-wet at the firmware's knob=127 raw value ($7f0000), which otherwise falls just short of Q23's true ceiling and would leave a small dry residual. |
| 7 | RVRS | `bipolar_q23` | 127 (= NEVER reverse) | Reverse-capture probability. $800000 (knob=0) = ALWAYS reverse; ≥$7e0000 (knob≥127, bipolar's own knob=127 raw value) = NEVER; otherwise `p_reverse=(1-RVRS)/2`, compared against a 24-bit Galois-LFSR draw once per trig. See §7. |

**Not a parameter**: `DECIM` (capture/playback decimation — real samples
skipped per stored word) is a compile-time `.equ`, currently **4**
(≈139ms of full-length capture, `WINDOW_SAMPLES = BUFLEN*DECIM = 6144`
samples). Raise it for longer/more lo-fi captures, lower it for
shorter/cleaner ones — edit `NFXBO.asm56k` and rebuild. `DECIM_SHIFT`
(=log2(DECIM), used as the interpolation ramp's divide-by-DECIM shift
amount) must be kept in sync by hand; there's no `log2()` in this
project's assembler. It was briefly a live knob (round 11) but a real bug
in that derivation (the interpolation shift never actually tracked the
live value) made it misbehave above roughly DECIM=16 — see TODO.md Round
12 for the full story. `GAP_FLOOR` is likewise a plain constant (8
samples) again, not runtime-derived.

**Removed, not shipped**: TONE (a highpass, repurposed mid-project from
an original tone-darkening concept, then dropped), BITS (bit-depth
crush, never built past the idea stage), ALFC (an anti-alias lowpass,
dropped once DECIM was understood to be the actual fix for decimation
aliasing).

## 3. Memory layout (Y, relative to r6)

```
Y+0        reserved
Y+1        NBAL
Y+2        GATE
Y+3        RATE
Y+4        BEND
Y+5        DCAY
Y+6        MIX
Y+7        RVRS
Y+8        unused (free — ALFC's old slot)
Y+9        TRACKMEM_BASE     this track's TRACK_BUFFERS base word address
Y+10       PHASE             0=IDLE 1=ACTIVE (see §4)
Y+11       TRIG_FLAG         set by TRIG, consumed once by RENDER
Y+12       CAP_POS           capture write offset, 0..CAP_LEN_FINAL-1
Y+13       CAP_REMAIN        decimated words still to capture (countdown)
Y+14       CAP_DECIM_CTR     real-sample countdown between stored capture words
Y+15       CAP_DELAY_REMAIN  real samples to wait before capture starts (GATE>0)
Y+16       CAP_LEN_FINAL     final captured length in words
Y+17       BOUNCE_POS        current read/write offset into the captured buffer
Y+18       BOUNCE_DECIM_CTR  real-sample countdown for decimated-hold playback
Y+19       GAP_REMAIN        real samples until the next repeat restarts
Y+20       GAP_CUR           current inter-repeat gap, in real samples
Y+21       SAMPLES_REMAINING real samples left in the actively-streaming repeat
Y+22       DCAY_MULT         this block's DCAY scaled to its 0.99 ceiling
Y+23       ACCUM_LEVEL       running compounded level estimate
Y+24       REPEATS_FIRED     safety counter against MAXREPEATS (8192)
Y+25       HELD_WET          continuously-ramping interpolated wet output
Y+26       INTERP_STEP       per-sample increment ramping HELD_WET toward target
Y+27       REVERSE_FLAG      this trig's reverse-capture decision (0/1)
Y+28       RNG_STATE         24-bit Galois LFSR state driving REVERSE_FLAG's draw
Y+29       CAP_WINDOW_REMAIN real samples left in the fixed capture window
Y+30       PREV_WET_SNAPSHOT one-time copy of HELD_WET taken at trig time, for
                             layered capture (see §7) — HELD_WET itself gets
                             zeroed before CAP_STORE would otherwise read it
Y+31/32    unused (free)
```

`y_workset_words` in `NFXBO.json` is 30 (covers offsets 0..29 — Y+30's
use was added after that count was last set; re-verify before relying on
Y+30 if this file and the code ever disagree on that count again).

## 4. State machine: IDLE / ACTIVE, capture and bounce run concurrently

Only two phases — not the three-phase IDLE/CAPTURE/BOUNCE model this doc
originally proposed:

- **IDLE** (`PHASE=0`) — nothing triggered, or the previous train has
  fully decayed.
- **ACTIVE** (`PHASE=1`) — a trig has fired and the train hasn't fully
  decayed yet. Capture and bounce are **not** separate sub-phases of
  ACTIVE — both run concurrently from the moment of the trig, each gated
  only by its own independent state:
  - Capture runs until `CAP_WINDOW_REMAIN` (a fixed real-time countdown,
    `WINDOW_SAMPLES` samples, independent of GATE) reaches zero. GATE
    only changes *how many* of those samples actually get stored
    (`CAP_REMAIN`) and whether there's a start delay — never changes
    *when* the window itself starts or ends.
  - Bounce's gap countdown (`GAP_REMAIN`) starts counting down from the
    instant of the trig, not from whenever capture happens to finish —
    repeat 1 can start streaming while capture is still running.
    Capture's write-head and bounce's read-head advance at the identical
    per-sample rate once bounce starts, so the write-head (already ahead
    by however many samples elapsed before bounce began) stays ahead for
    the rest of the window — bounce can never read past what's actually
    been captured.

`TRIG` sets a one-shot flag; `RENDER` consumes it once per block,
resetting all per-trig state (including firing the layered-capture
snapshot, §7, and the RVRS draw, §7) and entering/re-entering ACTIVE.
This is "whatever was still playing is cancelled, starts completely
fresh" — the firmware's own anti-click fade (§1) handles the audible
smoothness of that cancellation; this machine's own state reset handles
the engine logic.

A repeat restart (gap expiring) re-checks `REPEATS_FIRED` against
`MAXREPEATS` and `ACCUM_LEVEL` against `LEVEL_THRESHOLD` (≈-72dB) — the
train stops (back to IDLE) when either trips, except the very first
restart (repeat 1) is exempt from the level check (it's the pristine
capture, nothing has decayed yet).

## 5. Playback: decimated hold with linear interpolation

Repeats stream one real sample at a time. A hard zero-order hold (repeat
the same value for `DECIM` samples then jump) was tried and rejected — it
produces a harsh, audible staircase and an instant jump at every restart.
Instead, `HELD_WET` continuously ramps toward whatever target was set at
the last decimated advance, nudged by `INTERP_STEP` every single sample
(hold or advance alike), so both ordinary decimation steps and
pass-restart jumps glide smoothly over `DECIM` samples instead of
jumping. `INTERP_STEP` is recomputed on every advance as
`(target - current) >> DECIM_SHIFT`, computed by subtracting in the full
accumulator first and shifting once at the end (not shifting each
operand independently before subtracting) — the double-truncation
version of this was a real, shipped bug that produced an audible
high-pitched ring on quiet signals (see TODO.md).

## 6. Fixed-point safety pattern used throughout

Any time two independently-bounded Q23 signals need to be combined, this
file uses one of two proven-safe shapes rather than a naive
subtract-then-truncate (which can silently wrap on exactly the kind of
sharp transient a drum hit produces):

- **Convex combination** (`a*(1-w) + b*w`, weights ≥0 summing to 1) for
  *blends* — NBAL's neighbour mix, the dry/wet output mix. Mathematically
  bounded by whichever input has the larger magnitude; cannot overflow.
- **Subtract/sum in the full accumulator, truncate once at the end** for
  *differences or sums that may legitimately exceed ±1.0* — the
  interpolation step (§5) and the layered-capture sum (§7, clamped rather
  than truncated, since a sum — unlike a scaled difference — isn't
  automatically bounded back into range).

## 7. Reverse capture (RVRS) and layered capture

Both run once per trig, in `RENDER`'s once-per-trig preamble (before
`GATE`'s own code, which needs `REVERSE_FLAG`'s... no — needs
`CAP_REMAIN`'s final value, set by GATE itself, to place `CAP_POS` for a
reversed capture; the two compose independently — direction vs. value).

**RVRS**: `p_reverse = (1-RVRS)/2` (computed in the full accumulator
first, since `1-RVRS` can reach 2.0 for RVRS near -1, then shifted once
— same pattern as §6). A 24-bit Galois LFSR (taps `x^24+x^23+x^22+x^17+1`,
`$c20001` — the same idiom MDS's own `pluck.asm56k` example uses for its
noise generator) advances `RNG_STATE`, unrolled by hand as 8 plain
sequential `lsl`/`bcc`/`eor` steps rather than wrapped in a hardware `do`
loop — the latter measured ~4600 EXTRA cycles on this toolchain/emulator
for reasons not fully root-caused, despite being the identical shape the
official example uses. The new state, masked to drop its sign bit
(`and #$7fffff`), becomes a unipolar fraction compared against
`p_reverse`. `RNG_STATE` is seeded nonzero in `INIT` and never reset
(including across IDLE stretches) — a zero seed is a fixed point for
this LFSR (it would never advance), and reusing the same seed every trig
would make the "random" draw repeat.

`REVERSE_FLAG=1` makes `CAP_POS` start at `CAP_REMAIN-1` and count DOWN
instead of starting at 0 and counting up. `BOUNCE` always reads forward
from `buffer[0]` unchanged either way — a reversed capture plays back
reversed with zero changes to playback logic.

**Layered capture**: `CAP_STORE` sums the dry sample with
`PREV_WET_SNAPSHOT` (not live `HELD_WET` — see Y+30's note in §3) and
clamps the sum back into Q23 range before storing, instead of storing
dry alone. When nothing was ringing (snapshot≈0) this is a no-op; when a
trig lands on a still-audible previous train, the new capture builds on
it. The snapshot is taken once, at trig time, not resampled live — a
fixed blend level for the whole capture, not a sample-accurate running
sum.

## 8. Cycle budget

Worst case measured via `dsp56300/cyclecheck/cyclecheck_nfxbo_v1.cpp`:
**3267/3951** (684 spare). The single most expensive scenario is a
bounce restart at `GAP_FLOOR` with the BEND-shrink branch active (4
restarts/block, the most this engine can produce once the gap clamp is
in effect). Re-run this harness after any change to `DECIM`, `GAP_FLOOR`,
or anything in the per-sample loop body — don't assume headroom carries
over from a different build.
