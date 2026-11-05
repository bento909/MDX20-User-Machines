# NFX-UWO — Design Brief

## The idea in one sentence

On each trig, grab a short piece of whatever's playing on the two tracks
before this one AND this one (with certain caveats), then having saved that sample, play it back on subsequent steps, with additional features such as reverse and whatever else is possible

## What it should sound and feel like

It should be possible to sample one step and then repeat the sound captured in that step on subsequent steps.

## Signal flow

1. **Trig happens.** Depending on the value of a REC parameter, either record the balance of the two previous neighbours,
or the two previous neighbours and the previously captured sample, OR , don't record anything and just play the previously recorded sample.
2. **Capture.** For the the time between the start of a triggered step and the beginning of the next step
   (shaped to some degree by GATE), the machine listens
   to a blend of the two tracks immediately before it,(SET BY NBAL) and the existing captured sample (set by REC - 0 value is Only Record Neighbour tracks, 1 is record neighbour tracks and play Previous sample at minimum volume, thus capturing a blend of neighbour tracks and existing sample; 126 is record neighbour tracks and play Previous sample at max volume, thus capturing a blend of neighbour tracks and existing sample, 127 is DO NOT RECORD over sample, but play it at max volume) - notwithstanding NBAL Dry/Wet knob (MIX)
   records a low quality sample of that blend into its own small buffer. While capturing, it also
   passes that same audio straight through live (the "dry" side of MIX) —
   so with MIX set somewhere near halfway, you still hear the source material in
   real time while it's being captured in the background.
3. **REPLAY.** Once the capture window closes, the recorded snippet may be played again on another trig (and optionally resampled)
4. Reversability - employ the same technique as NFX-BO - RVRS knob at -ve max gives 100% chance of reversal, at +ve max 0% chance of reversal, and progressively all values in between


## The knobs

| Knob | What it controls |
|---|---|
| **NBAL** | Which of the two tracks before this one gets captured — low end of the knob is the far track (two back), the other end is the near track (one back), with a blend in between. |
| **GATE** | How much of the capture window is actually used. Middle = capture the whole window. To the right, start capturing later (skip the beginning of the window). To the left direction = stop capturing early (skip the end). |
| **REC** | 0 value means only record NBAL - max value means do not record, only playback sample, 1-126 to progressively blend existing sample, and resample the resultant blend of the sample and the neighbours |
| **BITS** | just an idea for now - allow longer sampling time by optionally reducing bitrate / sample rate |
| **RVRS** | probability of the sample being reversed at capture - from 100% to 0% progressively from 0-127.
| **MIX** | Dry/wet balance — how much of the live source you hear through this channel - does not apply to what is recorded though! |
| Any other ideas we come up with on the way

## Known hard constraints (not bugs — physical limits of the hardware)

- **The capture buffer is small and fixed** — the Machinedrum only gives
  this machine a little over half a second of real-time buffer, at most,
  per track. To let GATE reach a musically useful fraction of a bar, the
  machine deliberately records and plays back at a reduced internal
  sample rate, stretching that time budget at the cost of some lo-fi/
  aliased character in what gets captured. This is intentional, not a
  defect — "more lo-fi, more time" was an explicit tradeoff made for this
  machine.

## What "working" looks like, concretely

Sample steps of 2 neighbours- play it back - oversample the original sample with reversals / new samples - create unpredicability

-Reversal of recorded samples? grain tabling? pitch shifting? IDeas
