# NUW-G8 — Technical Design

Status: design pass only, not yet implemented. Everything below is a
concrete proposal, not yet assembled/certified/hardware-tested. See
`BRIEF.md` for how the concept itself got here.

## 1. What's genuinely new here vs. the rest of the NUW family

NUW-G8 reuses real, proven pieces of NUW-JT/PT/TS (12-bit pack/unpack,
`CAP_DELAY_REMAIN`'s delay math, `STEP_SIZE_Q8`/`PB_FRAC` fractional
playback, NUW-PT's semitone-table derivation, the `HELD_WET` ramp idea)
but combines them into a structurally different engine in three ways
that need real design work, not just parameter renaming:

1. **`DECIM=1`** — capture happens on EVERY real sample, not 1-in-4.
   NUW-JT/TS's `RENDER_LOOP` only does capture work at group-local
   position 3 of its 4-position bulk pass (matching `DECIM=4`); that
   shape doesn't exist here. See §3.
2. **REC is a convex-combination crossfade**, not NUW-JT/TS's additive
   blend. See §4.
3. **Grain playback reads via `(SHFT + loop_pos*GRAN) mod
   LOGICAL_BUFLEN`**, not a direct position read. `LOGICAL_BUFLEN` isn't
   a power of 2, so this wrap needs real bounds work. See §6.

## 2. Y-memory parameter layout

Following the established per-track workset convention (param slots
first, in manifest order, then internal state):

| Offset | Name | Transform | Role |
|---|---|---|---|
| Y+1 | NBAL | unipolar_q23 | neighbour blend for the fresh capture |
| Y+2 | GATE | **unipolar_q23** (not bipolar — see §1 above) | delay before capture starts, 0=immediate |
| Y+3 | REC | unipolar_q23 | dry/old-content crossfade, 127=capture disabled |
| Y+4 | GRAN | unipolar_q23 | stride (samples skipped per grain step) |
| Y+5 | SHFT | unipolar_q23 | phase offset into the stride pattern |
| Y+6 | PITCH | bipolar_q23 | ±1 octave, half-semitone-quantized |
| Y+7 | FADE | unipolar_q23 | grain-boundary crossfade amount |
| Y+8 | MIX | unipolar_q23 | dry/wet monitor (capture-independent, same as the rest of the family) |

Internal state (offsets TBD during implementation, listed here for the
set of distinct values needed, mirroring how NUW-JT/TS document theirs):

- `CAPTURE_ENABLED`, `REC_SCALE`, `ONE_MINUS_REC_SCALE` — latched once
  per trig from REC (§4).
- `CAP_DELAY_REMAIN` — real samples to wait before capture starts (§5).
- `LOGICAL_POS` — capture write position, 0..LOGICAL_BUFLEN-1 (unlike
  NUW-JT/TS, always forward — no RVRS in this machine's knob set, so no
  REVERSE_FLAG/direction state needed at all).
- `GRAIN_LEN` — cached once per trig: `ceil(LOGICAL_BUFLEN / GRAN)`, the
  number of strided samples in one full grain cycle (§6).
- `LOOP_POS`, `PB_FRAC` — grain-space playback position + fractional
  accumulator (reuses NUW-PT/TS's own pair, just indexing grain-space
  instead of buffer-space — see §6).
- `STEP_SIZE_Q8`, `RAMP_FRACTION` — PITCH's own per-trig derived values
  (§7, direct reuse of NUW-PT's existing derivation shape).
- `HELD_WET`, `INTERP_STEP` — the boundary-crossfade ramp (§8).
- No `PHASE`/`WINDOW_REMAIN` expiry — see §3.4, sustain is indefinite.

## 3. Capture: DECIM=1 and the RENDER_LOOP shape

### 3.1 Why DECIM=1 doesn't fit the existing bulk-pass template

NUW-JT/TS's `RENDER_LOOP` runs `do #8` over a 4-position unrolled body,
with capture work hardcoded into ONLY position 3 of each group of 4 —
correct because `DECIM=4` means exactly 1-in-4 real samples is a
capture event, and the old proof ("two counters with identical seed and
period can never drift apart") relies on that fixed 4-sample cadence.

At `DECIM=1`, every real sample is a capture event. There's no "3 plain
positions + 1 capture position" split left — all 4 positions in the
bulk pass need to do capture work. This isn't a parameter tweak, it's
removing the position-3-only gating entirely and duplicating the
capture body into all 4 positions (same "duplicate the body, don't use
a real loop inside a loop" discipline this whole project already uses
for the Jcc-inside-hardware-DO-loop hazard — just now the capture body
is one of the things duplicated 4x instead of being the thing confined
to 1-in-4).

### 3.2 Cycle-budget consequence (flagged, not yet measured)

Capture work running on every sample instead of 1-in-4 is a real cost
increase versus NUW-JT/TS's own per-block capture cost — expect this
machine's real certified numbers to look different from the rest of
the family for that reason alone, independent of anything else new
here. Not estimated numerically yet; that's what certification is for
once this is actually assembled.

### 3.3 What capture actually writes, per real sample

Simpler than NUW-JT/TS in one real way: no `CAP_REMAIN` countdown.
NUW-JT/TS's `CAP_REMAIN` existed because GATE could shrink how much of
the buffer gets freshly written, leaving the remainder holding stale
content from a previous trig. G8's GATE (§5) only delays the START —
once capture begins, it always runs to completion (`LOGICAL_BUFLEN`
samples, `DECIM=1` so that's `LOGICAL_BUFLEN` real samples, ~70-95ms).
So: capture is gated only by `CAPTURE_ENABLED` (REC<127) and
`CAP_DELAY_REMAIN` (GATE); once both clear, every real sample writes
until `LOGICAL_POS` wraps back to 0 (one full lap), then capture simply
stops for the rest of this trig (same "falls through to skip from then
on" idiom NUW-JT/TS already use once their own countdown expires).

**REAL BUG, found on real hardware 2026-11-10 (direct user report:
"it doesn't play anything on subsequent triggers")**: this paragraph
described the INTENDED behavior, but the first implementation pass
never actually coded the stop — `LOGICAL_POS` just wrapped and kept
writing forever, for as long as `PHASE` stayed active (which is
forever, per Sec 3.4). Between two trigs several steps apart, capture
kept re-writing the buffer the whole time from whatever was on the
neighbour tracks, so a later trig's own fresh reset landed on top of
whatever had been captured most recently — including silence, if
nothing was playing on the neighbour tracks at that moment. Fixed by
adding `CAP_REMAIN` (seeded to `LOGICAL_BUFLEN` at trig time,
decremented once per actual capture-write event, gating all further
writes once it reaches 0) — now actually enforcing the one-lap stop
this paragraph always claimed.

Still reuses the 12-bit write-pairing mechanism unchanged (a buffer
word is only committed once both logical halves of a pair are ready,
via `PENDING_HALF`) — `DECIM=1` doesn't change the pairing logic at
all, just how often the surrounding capture body runs.

### 3.4 No PHASE/WINDOW_REMAIN expiry

Per `BRIEF.md`'s own settled decision (the Machinedrum's per-track
envelope now owns note-shaping), this machine's PLAYBACK does not
expire on its own — once a trig starts it, it keeps looping the grain
until the next trig restarts the whole process. No `WINDOW_REMAIN`
countdown, no `PHASE=IDLE` auto-stop. This also sidesteps the entire
"pass duration must scale with speed" problem NUW-PT/TS's own
`WINDOW_REMAIN` fix had to solve — there's no fixed pass duration here
to scale in the first place.

## 4. REC: convex-combination crossfade

```
REC raw >= $7f0000 (127)  =>  CAPTURE_ENABLED = 0  (pure playback, same
                                cutoff convention as NUW-JT/TS)
otherwise:
  REC_SCALE           = REC's own raw value, as a true Q23 fraction
  ONE_MINUS_REC_SCALE = $7fffff - REC_SCALE   (same "1-x" idiom NBAL/
                        MIX already use elsewhere in this family)
  CAPTURE_ENABLED = 1
```

Per-sample write (replacing NUW-JT/TS's `write = dry +
REC_SCALE*old_sample`):

```
write = ONE_MINUS_REC_SCALE*dry + REC_SCALE*old_sample
```

Both weights are non-negative and sum to exactly `$7fffff` (true 1.0) —
a convex combination, same proof NBAL's own neighbour-blend already
relies on: bounded by whichever input has the larger magnitude, cannot
overflow Q23 full scale. **No hard clamp needed for this blend at
all** — unlike NUW-JT/TS, which needed one (and needed a -2dB headroom
fix on top of that, see that engine's own history).

Still worth a small-signal gate near `REC=126` (reusing the
`FEEDBACK_GATE` idea, same tiny ~-66dB threshold): at that extreme,
`ONE_MINUS_REC_SCALE` is near zero and almost the entire write is
`old_sample` re-written back into itself — a genuine feedback loop.
Overflow isn't a risk (the convex combination guarantees that), but DC
bias or quantization noise can still slowly accumulate over many trigs
without it. Gate the `old_sample` contribution the same way NUW-JT/TS
gate theirs, just applied to a differently-shaped formula.

## 5. GATE: unipolar delay-only

Per the correction in the session notes above — NOT a reuse of NUW-JT/
TS's bipolar GATE (whose negative half shrinks `CAP_REMAIN` toward
zero, the opposite of "immediate + full duration"). Instead:

```
GATE raw, unipolar_q23 (0 = hard left = immediate)
delay_fraction = GATE's own raw value, as a true Q23 fraction
CAP_DELAY_REMAIN = delay_fraction * (some real-sample delay ceiling)
```

Open number: the delay ceiling. Proposing `LOGICAL_BUFLEN` itself
(i.e. GATE's full range spans "no delay" to "delay by one whole
capture-length's worth of real time") as the starting point — gives a
clearly audible, musically sensible range (you can slide the capture
to grab material up to ~70-95ms after the trig) without needing to
know anything about actual next-trig timing, which this machine can't
see in advance. Revisit once this is actually heard.

`CAP_REMAIN` doesn't exist in this design at all (see §3.3) — GATE only
ever delays the start, never shrinks the capture once it begins.

## 6. Grain assembly: GRAN/SHFT stride addressing

### 6.1 The address calculation

Instead of PLAYBACK reading `loop_pos` directly (NUW-JT/PT/TS's own
convention), G8 reads:

```
real_addr = (SHFT + loop_pos * GRAN) mod LOGICAL_BUFLEN
```

`GRAIN_LEN` (cached once per trig) = `ceil(LOGICAL_BUFLEN / GRAN)` — the
number of distinct `loop_pos` values before the stride pattern has
covered the whole buffer and starts repeating addresses. `loop_pos`
itself wraps `0..GRAIN_LEN-1` (this is the "grain" — one full lap of
the stride pattern across the captured buffer).

### 6.2 The wrap problem, worked through

`LOGICAL_BUFLEN=3072` is not a power of 2 (`3072 = 1024*3`), so `mod
LOGICAL_BUFLEN` can't be a cheap bitmask — same situation NUW-JT/PT/TS
already solved for their own `+1`-per-sample position wraps, via
explicit compare-and-subtract. The difference here: those wraps are
bounded to "at most one `LOGICAL_BUFLEN` out of range" by construction
(the position only ever moves by a small, bounded step each sample).
`SHFT + loop_pos*GRAN` is NOT bounded that cheaply in general —
`loop_pos` ranges up to `GRAIN_LEN-1 ≈ LOGICAL_BUFLEN/GRAN`, so
`loop_pos*GRAN` ranges up to roughly `LOGICAL_BUFLEN - GRAN` by
construction of `GRAIN_LEN` itself (the whole point of capping
`loop_pos` at `GRAIN_LEN-1` is to keep the raw product inside one
buffer-length). So the actual bound is:

```
0 <= loop_pos*GRAN <= LOGICAL_BUFLEN - 1   (by GRAIN_LEN's own definition)
0 <= SHFT < GRAN                            (SHFT only needs to select
                                              within ONE stride step,
                                              not the whole buffer)
=> 0 <= SHFT + loop_pos*GRAN < LOGICAL_BUFLEN + GRAN - 1
```

So the raw sum can exceed `LOGICAL_BUFLEN` by at most `GRAN-1` — a
single bounded excess, not an unbounded one. That means the EXACT same
"at most one wrap" discipline NUW-PT/TS's own `PB_ADDR_OK` already
uses (`cmp #>LOGICAL_BUFLEN,a` / `blt ok` / `sub #>LOGICAL_BUFLEN,a`)
still applies here directly, with no loop needed — it just needed this
explicit bound checked, not assumed. Good: confirms the stride approach
doesn't need new wrap machinery, just the existing one-off pattern
applied to a multiply-then-add address instead of a plain accumulator.

`SHFT` itself should be range-limited to `[0, GRAN)` at the parameter
level (not the full `[0, LOGICAL_BUFLEN)` a naive unipolar_q23 mapping
would give it) specifically to keep the bound above true — needs
`GRAN`'s own current value available when deriving `SHFT`'s effective
range, so `SHFT`'s derivation must run AFTER `GRAN`'s each trig, not
independently.

### 6.3 GRAN's own range (open number)

Needs a concrete min/max before implementation. Proposing a minimum of
`GRAN=1` (no striding at all — degenerates to reading the buffer
directly, lowest pitch/densest grain, full `LOGICAL_BUFLEN`-sample
grain) up to some maximum worth picking so the grain doesn't shrink to
an inaudibly-short handful of samples. Revisit with real numbers once
basic playback is working — this is a "listen and tune" constant, not
something derivable from first principles alone.

## 7. PITCH: half-semitone-quantized, reusing NUW-PT's table

NUW-PT's own semitone-table derivation (13-entry table of `2^(n/12)/4`
ratios, octave-shift, `murdenihcam`-style decomposition — see that
machine's own README/DESIGN.md for the full derivation writeup) already
does exactly the exact-semitone-ratio math this needs. The only real
change: **quantize the raw knob to half-semitone steps BEFORE the table
lookup**, and skip the interpolation between adjacent table entries
entirely (there's nothing to interpolate between once the input is
already quantized to a fixed grid) — simpler AND cheaper than NUW-PT's
own version of this same lookup, not just a straight port.

Range: ±1 octave (settled in `BRIEF.md`, narrower than NUW-PT/TS's own
±2 octaves) — recalibrate the raw-to-semitone-count scaling factor
accordingly (NUW-PT's own `raw*6144` constant was derived for ±24
semitones; this needs ±12 semitones' worth of range instead, i.e. half
that scaling constant).

Feeds the existing `STEP_SIZE_Q8`/`PB_FRAC`/`RAMP_FRACTION` playback
accumulator machinery unchanged — PITCH's output is still "a rate to
advance `loop_pos` at," exactly like NUW-PT/TS's own SPED/STEP_SIZE_Q8,
just now advancing through grain-space (§6) instead of buffer-space
directly, and quantized rather than continuous.

## 8. FADE: grain-boundary crossfade

Proposing direct reuse of the `HELD_WET` ramp idea (NUW-JT/PT/TS's own
proven de-click mechanism for exactly this kind of boundary
discontinuity): instead of jumping straight to the newly-read sample at
each `loop_pos` step, ramp `HELD_WET` toward it over some number of
samples, with `FADE` controlling how many (0 = instant/hard cut, higher
= smoother but blurrier edge). Needs the ramp TIME tied to `FADE`
directly (a knob-controlled ramp length) rather than NUW-PT/TS's own
fixed-by-`STEP_SIZE_Q8` ramp length, since here the "crossing rate" is
`GRAN`/`PITCH`-driven, not something FADE should silently also change.
Exact derivation (how `FADE`'s raw value maps to a ramp-sample-count or
a per-sample ramp-fraction) not worked out yet — this is the one piece
of `BRIEF.md`'s "still open" list that genuinely needs its own small
design pass before implementation, separate from everything resolved
above.

## 9. What's still open before implementation can start

- §5's delay ceiling (proposed: `LOGICAL_BUFLEN`, not yet confirmed by
  ear)
- §6.3's `GRAN` min/max range (proposed: 1 as the minimum, max TBD)
- §8's `FADE` derivation (the one piece with no concrete proposal yet)
- Real cycle-budget measurement once assembled — §3.2's "every sample
  is a capture event" cost is flagged but not yet numeric
