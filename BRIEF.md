# NFX-BO — Design Brief

## The idea in one sentence

On each trig, grab a short piece of whatever's playing on the two tracks
before this one, then play that piece back as a series of discrete,
bouncing-ball-style echoes — each one quieter, duller, and grittier than
the last, and the *gap* between echoes shrinking or growing like a ball
losing height (or settling down) with each bounce.

## What it should sound and feel like

Think of a physical ball dropped on a hard floor: it bounces fast at
first, each bounce a little quieter and the gaps between bounces a little
shorter, until it's a rapid flutter and then silence. NFX-BO is that, but
for a snippet of audio instead of a ball, with a knob to also run the
pattern in reverse (bounces slowing down and spreading out instead of
speeding up).

Each echo is not an independent, fresh copy of the original snippet being
replayed at a different volume — it's the **previous echo's own,
already-degraded output**, fed back through the same filtering/bit-crush/
level-loss chain again. So the tone darkening, the bit-crushing, and the
level loss all genuinely pile up bounce after bounce, rather than each
bounce independently fading from the same pristine source.

## Signal flow

1. **Trig happens.** Whatever was still playing from a previous trig is
   cancelled — this trig starts completely fresh.
2. **Capture.** For the the time between the start of a triggered step and the beginning of the next step
   (shaped to some degree by GATE), the machine listens
   to a blend of the two tracks immediately before it (set by NBAL) and
   records a low quality sample of that blend into its own small buffer. While capturing, it also
   passes that same audio straight through live (the "dry" side of MIX) —
   so with MIX set somewhere near halfway, you still hear the source material in
   real time while it's being captured in the background.
3. **Bounce.** Once the capture window closes, the recorded snippet starts
   replaying from the beginning. After a gap (set by RATE), it replays
   again — but this replay reads and overwrites the SAME buffer the first
   one just finished with, after passing it through TONE/DCAY/BITS. So
   bounce 2 is bounce 1's output, processed once more. Bounce 3 is bounce
   2's output, processed once more. And so on.
4. **The gap changes every bounce.** BEND adjusts the gap after each
   bounce — shrinking it (bounces speed up, true "bouncing ball" behavior)
   or growing it (bounces spread out and decelerate). A new trig always
   resets this back to RATE's starting gap.
5. **It eventually stops.** DCAY means every bounce loses some loudness,
   so in practice the train fades into silence on its own, no matter how long the decay is set for.

## The knobs

| Knob | What it controls |
|---|---|
| **NBAL** | Which of the two tracks before this one gets captured — low end of the knob is the far track (two back), the other end is the near track (one back), with a blend in between. |
| **GATE** | How much of the capture window is actually used. Middle = capture the whole window. To the right, start capturing later (skip the beginning of the window). To the left direction = stop capturing early (skip the end). |
| **RATE** | Initial gap between repeats — low values mean the first bounce comes almost immediately, high values mean a longer initial pause. |
| **BEND** | Multiplies the gap after every bounce. Shrinking (negative) = bounces accelerate, a classic bouncing-ball speed-up. Growing (positive) = bounces decelerate. Center = steady, unchanging gap. |
| **DCAY** | How much level survives each bounce. Always loses *some* level every bounce i.e. Max setting for Decay means that only as much as 99%
of the signal energy is passed to the next bounce — it can never sustain or loop forever, even at its max setting. |
| **MIX** | Dry/wet balance — how much of the live source vs. the bouncing echoes you hear. |
| **TONE** | A darkening (lowpass) filter applied to every bounce. Because it compounds, later bounces sound progressively duller/muffled compared to earlier ones. Maximum value of this knob => no filtering / Minimum value => more filtering|
| **BITS** | Bit-depth crushing applied to every bounce. Also compounds — later bounces get progressively grittier/lower-fi, not just the final captured snippet. |

## Known hard constraints (not bugs — physical limits of the hardware)

- **The capture buffer is small and fixed** — the Machinedrum only gives
  this machine a little over half a second of real-time buffer, at most,
  per track. To let GATE reach a musically useful fraction of a bar, the
  machine deliberately records and plays back at a reduced internal
  sample rate, stretching that time budget at the cost of some lo-fi/
  aliased character in what gets captured. This is intentional, not a
  defect — "more lo-fi, more time" was an explicit tradeoff made for this
  machine.
- **There's a floor on how fast bounces can repeat.** The shared
  processing budget across all 16 Machinedrum tracks means this engine
  can only check "is it time for the next bounce" so many times a second.
  Below a certain point, RATE/BEND settings that ask for faster bounces
  than the hardware can actually schedule will all sound the same (the
  fastest achievable rate), rather than continuing to get faster.

## What "working" looks like, concretely

- Turning RATE across its whole range should audibly and with smooth progression,
  change how long the first bounce takes to arrive — short at one end, long at the other —
  with no dead zone in the middle of the knob.
- Turning BEND should audibly change whether the bounce train speeds up,
  slows down, or stays steady, with smooth progression across the knob's full range including
  values on both sides of center.
- Across a single trig's bounce train, later bounces should be
  noticeably quieter (DCAY), duller (TONE), and grittier (BITS) than
  earlier ones in that same train — not uniform, and not silent after one
  bounce.
- A whole bounce train should run its natural course (shrinking in level
  until inaudible, or — with BEND set to spread out — the gaps growing
  until it feels like it's trailed off) rather than cutting off abruptly
  partway through, and rather than going on audibly forever.
