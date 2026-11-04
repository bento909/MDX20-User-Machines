# NFX-BO — Design Brief

*Updated 2026-11-04 to match the current build (v1, round 12) — the
original vision described a couple of knobs that were tried and dropped.
See "What changed since the original vision" below for the differences,
and `TODO.md` (`_authoring\resource\`) for the full round-by-round
history.*

## The idea in one sentence

On each trig, grab a short piece of whatever's playing on the two tracks
before this one, then play that piece back as a series of discrete,
bouncing-ball-style echoes — each one quieter than the last, and the
*gap* between echoes shrinking or growing like a ball losing height (or
settling down) with each bounce.

## What it should sound and feel like

Think of a physical ball dropped on a hard floor: it bounces fast at
first, each bounce a little quieter and the gaps between bounces a little
shorter, until it's a rapid flutter and then silence. NFX-BO is that, but
for a snippet of audio instead of a ball.

Each echo is not an independent, fresh copy of the original snippet being
replayed at a different volume — it's the **previous echo's own,
already-decayed output**, fed back through the same level-loss (DCAY)
stage again. So the level loss genuinely piles up bounce after bounce,
rather than each bounce independently fading from the same pristine
source.

## Signal flow

1. **Trig happens.** Whatever was still *playing* from a previous trig is
   cancelled — this trig's output starts completely fresh. (What was
   still *ringing*, though, doesn't just vanish — see "layered capture"
   in step 2.)
2. **Capture.** For a fixed real-time window (GATE only ever shapes WHAT
   inside that window gets kept, never WHEN anything happens — see
   `DESIGN.md` §4), the machine listens to a blend of the two tracks
   immediately before it (set by NBAL) and records a decimated (lo-fi by
   design — see "Known hard constraints") snippet of that blend into its
   own small buffer, while simultaneously passing that same live blend
   straight through as the dry side of MIX.
   - **Layered capture**: each captured word is summed with whatever
     bounce was still audible from the *previous* trig (clamped, not
     just overwritten) — so a trig that lands close on the heels of a
     still-ringing previous one builds on it instead of starting from a
     clean slate. Always on, no knob for it.
   - **RVRS** decides, once per trig, whether this capture gets written
     forward (plays back normally) or in reverse (plays back backward) —
     a knob-set *probability* of reversing, not an on/off switch.
3. **Bounce.** Capture and bounce run on independent clocks — bounce's
   gap-before-repeat-1 is counted from the trig itself, not from whenever
   the capture window happens to close, and can start streaming WHILE
   capture is still running. Once a repeat starts, it replays the
   recorded snippet from the beginning (or the end, if RVRS chose
   reverse). After a gap (set by RATE), it replays again — but this
   replay reads and overwrites the SAME buffer the first one just
   finished with, after passing it through DCAY. So bounce 2 is bounce
   1's output, processed once more. Bounce 3 is bounce 2's output,
   processed once more. And so on.
4. **The gap changes every bounce.** BEND adjusts the gap after each
   bounce — shrinking it (bounces speed up, true "bouncing ball"
   behavior) or growing it (bounces spread out and decelerate). A new
   trig always resets this back to RATE's starting gap.
5. **It eventually stops.** DCAY means every bounce loses some loudness,
   so in practice the train fades into silence on its own, no matter how
   long the decay is set for.

## The knobs

| Knob | What it controls |
|---|---|
| **NBAL** | Which of the two tracks before this one gets captured — low end of the knob is the far track (two back), the other end is the near track (one back), with a blend in between. |
| **GATE** | How much of the capture window is actually used. Middle = capture the whole window. To one side, start capturing later (skip the beginning). To the other, stop capturing early (skip the end). |
| **RATE** | Initial gap between repeats — low values mean the first bounce comes almost immediately, high values mean a longer initial pause. |
| **BEND** | Multiplies the gap after every bounce. Shrinking = bounces accelerate, a classic bouncing-ball speed-up. Growing = bounces decelerate. Center = steady, unchanging gap. |
| **DCAY** | How much level survives each bounce. Always loses *some* level every bounce — max setting still only passes about 99% of the signal energy to the next bounce, so it can never sustain or loop forever. |
| **MIX** | Dry/wet balance — how much of the live source vs. the bouncing echoes you hear. |
| **RVRS** | Reverse-capture probability: one extreme ALWAYS reverses this trig's capture, the other NEVER does, center is a 50/50 coin flip — every value between is the probability of reversing. |

## What changed since the original vision

(Kept here deliberately, so this brief doesn't silently drift out of sync
with the build again — if you're reading this far in the future, check
`NFXBO.asm56k`'s own header comment against this list before trusting
either blindly.)

- **TONE** (a darkening filter meant to compound bounce-to-bounce, like
  DCAY does for level) and **BITS** (bit-depth crushing, same compounding
  idea) were both explored at different points and ultimately removed,
  not shipped. TONE was briefly repurposed as a highpass for an unrelated
  low-frequency screech report, then dropped — along with **ALFC** (an
  anti-alias lowpass added to fight decimation aliasing) — once the REAL
  fix for that aliasing was found: a kick's pitch sweeps across whatever
  Nyquist the decimation sets, and no FIXED filter cutoff can suppress a
  sweep at the exact instant it's crossing. Lowering DECIM (below) raises
  that Nyquist directly, which filtering alone can never do. **DCAY is
  the only thing that compounds bounce-to-bounce now.**
- **DECIM** (the capture/playback decimation factor — how many real
  samples get skipped per stored word, trading fidelity for how much
  real time the fixed-size buffer can hold) is **not a knob**. It's a
  plain constant near the top of `NFXBO.asm56k` (currently 4, ≈139ms of
  full-length capture) — edit it and rebuild for longer/more lo-fi
  captures, or shorter/cleaner ones. It was briefly a live knob, but a
  real bug in how its interpolation math scaled at high settings made it
  malfunction above roughly 2/3 of the knob's travel; rather than fix and
  reverify that, it went back to compile-time.
- **RVRS** is new — it fills the parameter slot TONE/ALFC/the short-lived
  live DECIM knob used to occupy.
- **Layered capture** (step 2 above) is new and always-on.
- **Pitch-bend** (BEND affecting the captured sample's actual pitch, not
  just repeat timing) was discussed as a future direction but never
  built — it needs fractional-rate resampling this decimated-hold engine
  doesn't have, and would likely land as its own machine built from this
  one rather than a change to NFX-BO itself.

## Known hard constraints (not bugs — physical limits of the hardware)

- **The capture buffer is small and fixed** — the Machinedrum only gives
  this machine a little over half a second of real-time buffer, at most,
  per track. To let a capture reach a musically useful duration, the
  machine deliberately records and plays back at a reduced internal
  sample rate (DECIM, above), stretching that time budget at the cost of
  some lo-fi/aliased character in what gets captured. This is
  intentional, not a defect — "more lo-fi, more time" was an explicit
  tradeoff made for this machine, and DECIM's exact value is a deliberate
  compile-time choice, not something meant to be dialed per-performance.
- **There's a floor on how fast bounces can repeat.** The shared
  processing budget across all 16 Machinedrum tracks means this engine
  can only check "is it time for the next bounce" so many times a
  second. Below a certain point, RATE/BEND settings that ask for faster
  bounces than the hardware can actually schedule will all sound the
  same (the fastest achievable rate), rather than continuing to get
  faster.

## What "working" looks like, concretely

- Turning RATE across its whole range should audibly and with smooth
  progression change how long the first bounce takes to arrive — short
  at one end, long at the other — with no dead zone in the middle of the
  knob.
- Turning BEND should audibly change whether the bounce train speeds up,
  slows down, or stays steady, with smooth progression across the knob's
  full range including values on both sides of center.
- Turning RVRS from one extreme to the other should reliably flip
  whether captures play forward or backward, with a genuinely-varying
  (not stuck, not repeating) coin-flip in between — not a knob that only
  seems to do something at its two ends.
- Across a single trig's bounce train, later bounces should be
  noticeably quieter (DCAY) than earlier ones in that same train — not
  uniform, and not silent after one bounce.
- A whole bounce train should run its natural course (shrinking in level
  until inaudible, or — with BEND set to spread out — the gaps growing
  until it feels like it's trailed off) rather than cutting off abruptly
  partway through, and rather than going on audibly forever.
