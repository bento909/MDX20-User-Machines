# NUW-G8 (Neighbour User Wave Granulator) — Design Brief

## The idea in one sentence

Freeze a short 12-bit snippet of the two tracks before this one, then
assemble a looping synthesis grain by striding across that snippet at
an adjustable interval — a granular synth voice built on the same
self-sampling neighbour-capture foundation as NUW-JT/TS, not another
delay/overdub machine.

## What it should sound and feel like

Trig it, and it grabs a short piece of whatever's playing — then
instead of just replaying that piece once (NUW-JT) or stretching it
through a tape-speed knob (NUW-TS), it strides across the whole
snippet picking every Nth sample and loops the result as a pitched,
held tone. The stride itself sets a base pitch/density; `SHFT` lets you
slide which specific samples get picked at that same stride, so the
same fundamental can have noticeably different textures living inside
it. `PITCH` then fine-tunes ±1 octave on top, stepped at the
half-semitone so it can be p-locked into a bassline or melody across a
pattern, landing cleanly on a note every time.

## Signal flow

1. **Trig happens.** `REC` controls a true crossfade between fresh
   dry input and the existing captured content — DIFFERENT from NUW-
   JT/TS's own REC (which always keeps dry at full level and ADDS
   scaled old content on top): here, `write = (1-REC_SCALE)*dry +
   REC_SCALE*old_content`. `REC=0` = pure dry, no overdub at all.
   `REC=126` = pure old-content, no dry at all — fully "self-feeding"
   (what's captured becomes what gets fed back next time, a real
   feedback loop). `REC=127` = capture disabled entirely, pure
   playback, same cutoff convention as NUW-JT/TS. Because both weights
   are non-negative and sum to exactly 1, this is a convex combination
   and CANNOT overflow Q23 full scale — no hard clamp needed for this
   blend at all, unlike NUW-JT/TS's own formula (which needed one, and
   needed a headroom fix on top of that). Still worth a small-signal
   gate (reusing the `FEEDBACK_GATE` idea) near `REC=126` though — a
   near-total feedback loop will still slowly accumulate DC bias/
   quantization noise over many trigs even without an overflow risk.
2. **Capture.** `DECIM=1` (no decimation at all, unlike NUW-JT/TS's
   `DECIM=4`) over the SAME buffer size the rest of the family already
   uses (`LOGICAL_BUFLEN`=3072 12-bit samples) — no buffer-size
   restructuring needed, just that one constant. That gives a real-time
   capture window of roughly 70-95ms (depending on the deck's actual
   sample rate) of undecimated 12-bit audio: comfortably more than one
   grain needs (a melodic grain only needs to span one to a few periods
   of the target pitch — a low note around 55Hz needs ~800 samples per
   period, a note an octave or two up needs well under 200), leaving
   room for `GATE` and `GRAN`/`SHFT` to land on genuinely different
   material within the one capture. `GATE` carries over from NUW-JT/TS
   completely unchanged (same `CAP_DELAY_REMAIN` code already does
   exactly "delay capture start" — nothing new to build there) —
   repurposed here as picking WHEN within the trig-to-trig window the
   short capture starts, hard left = immediate/default.
3. **Grain assembly (no STRT/LOOP).** Rather than picking a contiguous
   window, the grain is assembled by striding across the ENTIRE short
   captured buffer: `GRAN` sets how many samples to skip each step (the
   stride), and `SHFT` picks which of the `GRAN` possible interleaved
   sample-subsets gets used (same stride/base pitch, different specific
   samples -> different texture at the same fundamental). Mechanically:
   the playback read address becomes `(SHFT + loop_pos*GRAN) mod
   buffer_length` instead of reading `loop_pos` directly — no separate
   grain buffer or copy pass needed, just that one address calculation
   change on top of the otherwise unchanged loop/playback machinery.
4. **Pitch.** `GRAN`'s own stride sets a base pitch/density on its own
   (a larger stride means fewer samples survive per loop, so it plays
   back faster/higher once looped); `PITCH` is a SEPARATE knob riding
   on top of that, fine-tuning ±1 octave, quantized to half-semitone
   steps (not continuous) so every knob position lands exactly on a
   pitch. Built from NUW-PT's own (shelved) semitone-table-ratio
   derivation, repurposed — quantizing to discrete half-semitone steps
   means no interpolation between table entries is needed, which should
   make this simpler and cheaper than NUW-PT's own version of the same
   table lookup.

## The knobs (settled, v1 — 8 of 8 slots used)

| Knob | What it controls |
|---|---|
| **NBAL** | Neighbour blend for the fresh capture, same meaning as NUW-JT/TS. |
| **GATE** | When within the trig-to-trig window the short capture starts — hard left = immediate, carries over NUW-JT/TS's existing `CAP_DELAY_REMAIN` code unchanged. |
| **REC** | Crossfade between fresh dry input and existing captured content (see Signal flow §1) — `0`=pure dry, `126`=pure self-feeding overdub, `127`=capture disabled, pure playback. A genuinely different blend formula from NUW-JT/TS's own REC. |
| **GRAN** | Stride (every Nth sample) used to assemble the synthesis grain from the captured snippet — sets a base pitch/density. |
| **SHFT** | Which of the `GRAN` possible interleaved sample-subsets gets used — same stride/pitch, different texture. |
| **PITCH** | ±1 octave, half-semitone-quantized fine-tuning on top of whatever `GRAN` produces — the melodic/p-lockable knob. |
| **FADE** | Grain-edge crossfade/window amount — smooths the click a hard-cut loop boundary would otherwise have. |
| **MIX** | Dry/wet monitor balance, same monitor-only meaning as the rest of the family (doesn't affect what's captured). |

All 8 slots now used.

## Settled design decisions

- **Capture length**: `DECIM=1` over the existing 3072-sample buffer
  (~70-95ms) — no buffer-size restructuring, see Signal flow §2 above.
- **Sustain**: the tone holds indefinitely once triggered — no onboard
  decay/envelope knob needed. The Machinedrum's own newer per-track
  envelope handles note-shaping at the track level now, so this
  machine doesn't need to duplicate that itself.
- **Grain-boundary clicking**: handled by the `FADE` knob rather than
  left as a hard cut. Worth checking whether this can reuse NUW-JT/TS's
  own `HELD_WET`-style ramp idea (already proven, already cycle-costed)
  rather than inventing a new crossfade mechanism from scratch.
- **REC's blend formula**: a true convex-combination crossfade (see
  Signal flow §1), not NUW-JT/TS's own additive formula — mathematically
  can't overflow, so no hard clamp needed for this blend at all (avoids
  the whole overflow/headroom bug class those three machines needed a
  fix for). A small-signal gate near `REC=126`'s near-total feedback is
  still worth carrying over from `FEEDBACK_GATE`'s own idea, to stop DC
  bias/quantization noise slowly accumulating over many trigs — that
  risk doesn't go away just because overflow isn't possible anymore.

## Still open for the design pass (not yet settled)

- **The stride/wrap math**: `(SHFT + loop_pos*GRAN) mod buffer_length`
  needs real design work — `LOGICAL_BUFLEN`=3072 isn't a power of 2, so
  the wrap can't be a cheap bitmask; it needs the same explicit
  compare-and-subtract wrap already used elsewhere in this engine
  (e.g. `PB_ADDR_OK`), with the bounds reasoning redone for a
  multiply-by-stride address rather than a +1-per-sample one (need to
  confirm the result never drifts more than one buffer-length out of
  range, the same "at most one wrap" discipline this codebase already
  relies on elsewhere, or handle the multi-wrap case explicitly if it
  can't be bounded that cheaply).
- **`GRAN`'s own range/units**: how many distinct stride values, and
  what's a musically sensible min/max (too small a stride barely
  changes anything; too large and the grain shrinks to almost nothing)?
- **`FADE`'s exact mechanism**: confirm the `HELD_WET`-ramp reuse idea
  actually fits this grain-loop context before committing to it.
