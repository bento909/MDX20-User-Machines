# NFX-BO v1 — Design (from BRIEF.md + GOLD_STANDARD.md, from scratch)

Status, 2026-11-03 (round 12): **implemented, assembled, packed, and
cycle-checked**. `NFXBO.asm56k`/`NFXBO.json` build cleanly to
`NFXBO.mds` → `NFX-BO.syx` (453 program words, 1 import, structurally
validated via `mds_validate.js`, worst-case measured at 3267/3951
cycles). v1 now ships 7 knobs (NBAL/GATE/RATE/BEND/DCAY/MIX/RVRS, not the
6 this doc was originally written for — TONE/BITS/ALFC were all tried
and dropped again at various points; RVRS and a layered-capture change
were added round 12; see TODO.md for the full history). **This specific
build has not yet been tested on real hardware** — this design doc
originally pinned down terminology/structure before any code was written
(lesson learned the hard way on the previous attempt — see
`../bounce-delay/`), and is kept below as the record of that original
reasoning. It is NOT kept in sync with every later round — `TODO.md` is
the authoritative current-state record; treat anything below that
conflicts with it as historical context, not current spec.

**v1 originally shipped with six active knobs — NBAL, GATE, RATE, BEND,
DCAY, MIX.** TONE and BITS were shelved for the initial build ("the least
important ones, added as an afterthought... shelve them while the others get
sorted"). **TONE was reinstated in round 7** as a tunable highpass (NOT the
tone-shaping idea described below — repurposed after real hardware testing
found a low-frequency screech; see TODO.md). BITS remains shelved. Sections
below that still discuss the original TONE concept or a 6-knob scope are
historical — kept for the reasoning trail, superseded by TODO.md where they
conflict.

## 1. Machine declaration

```json
{
  "id": "<tbd — reverse-DNS style, CONFIRM a namespace>",
  "display_name": "NFX-BO",
  "category": "NFX",
  "short_label": "BO",
  "tonal": false,
  "neighbour": true,
  "stereo_pair": false,
  "retrigger": "restart"
}
```

- `neighbour: true` is required to read the "one back" / "two back" buffers NBAL
  needs (spec §3). `stereo_pair` stays false — nothing in the brief needs it, and
  setting it would reserve Y+9 for role info instead of our own state (spec: "Do
  not write Y+9... when stereo_pair is set" — doesn't apply to us, but noting why).
- `retrigger: "restart"` (the default) means the **firmware's own ANTI-CLICK engine
  setting fades the previous block's audio out before calling TRIG** (spec
  "Retriggering" section) — so the brief's requirement #1 ("whatever was still
  playing is cancelled, starts completely fresh") gets its *click-free* cancellation
  for free from the firmware. Our own TRIG/RENDER still has to reset the *internal
  state machine* (phase, pointers, gap) — the firmware only smooths the audible
  jump, it doesn't know about our bounce engine's state.

## 2. Parameter transforms (firmware-side, per spec §1)

**v1 declares only 6 parameters** (NBAL, GATE, RATE, BEND, DCAY, MIX) — TONE and
BITS are shelved per the user's decision (see table after this one).

| # | Knob | Transform | Why | Status |
|---|------|-----------|-----|---------|
| 1 | NBAL | `unipolar_q23` | Blend coefficient 0..1 between "two back" and "one back". | **RESOLVED — carried forward from the old build.** Its NBAL code is a clean, simple linear crossfade — `a = two_back + NBAL*(one_back - two_back)` (old `NFXBO.fixed.asm56k` lines ~261-269, a `mac` against the difference) — confirmed-good on real hardware per the user, and the implementation is clean enough to reuse as-is rather than re-derive. |
| 2 | GATE | `bipolar_q23` | Center (64) = 0 = full window. One side trims the end, the other delays the start — inherently a signed-around-center control. | Open — no reuse question, not yet implemented. |
| 3 | RATE | `unipolar_q23` or `unipolar_square_q23` | Monotonic initial-gap control. Squared gives more of the knob's travel to small gap values (finer control at the fast end). | Open — plain vs. squared curve. **Old build hit a granularity bug here, fixed with a hard cycle-budget floor (`GAP_SAFETY_FLOOR`) — that floor is a measured hardware fact (see §5), applies regardless of curve choice.** |
| 4 | BEND | `bipolar_q23` | Center (64) = 0 = steady gap. | **RESOLVED — confirmed exponential/compounding by design.** User wants the full range to span from very slow (1-2 repeats per bar) at one extreme through to a rapid multi-per-second flurry at the other, and the same both directions (shrink or grow). Repeated multiplication of a constant per-bounce factor is inherently exponential/geometric in bounce-index, which already matches this — remaining work is picking a multiplier range wide enough that compounding across a musically small number of bounces can traverse that whole span (down near the `GAP_SAFETY_FLOOR`, or up to bar-length). **Needs numeric tuning against real playback, not just a formula choice.** |
| 5 | DCAY | own hand-rolled per-bounce multiplier, NOT the firmware `decay` transform | "How much level survives each discrete repeat" (brief's own semantics) — a once-per-bounce-event multiplier. | **RESOLVED.** The firmware's native `decay` transform is a *per-sample* coefficient (built for continuous envelopes) — a mismatched grain for an event that only changes once per bounce. **Decision: implement DCAY manually (own ceiling logic, like the old build's `DCAY_CEIL`) for v1; revisit the native `decay` transform as a possible simplification only after v1 is tested on hardware**, per the user. |
| 6 | MIX | `unipolar_q23` | Standard dry/wet. | Open — not yet implemented. |

**Shelved for v1 (v2, per user decision — "least important, added as an afterthought... shelve them while the others get sorted"):**

| Knob | Would-be transform | Note |
|------|---------------------|------|
| TONE | `unipolar_q23` | Brief's polarity is inverted from the usual convention (max = *no* filtering, min = *more* filtering) — would invert in code (`1 - param`) rather than fight the transform, when this is picked back up. |
| BITS | `index` or `unipolar_q23` | `index` fits a discrete bit-depth selector; `unipolar_q23` fits a continuous crush amount (what the old build used). Decision deferred. |

## 3. Memory layout (per-track 64-word X/Y blocks, R6-relative)

```
Y+0        reserved (do not touch)
Y+1..Y+6   NBAL GATE RATE BEND DCAY MIX   (firmware-converted, read-only; only
           6 params declared for v1 — TONE/BITS shelved, see §2)
Y+7..Y+8   unused for v1 (free Y-param slots if TONE/BITS are reinstated later)
Y+9        TRACK_BUFFERS base pointer for this track (computed once in INIT,
           exactly EN's confirmed pattern: r1*1536, rounded to a 512-word
           boundary — GOLD_STANDARD §3)
Y+10       phase: 0=IDLE 1=CAPTURE 2=BOUNCE
Y+11..?    bounce state: write/read position in buffer, current gap/countdown,
           repeats-fired counter, decimation phase accumulator, GATE-derived
           capture start/end sample counts, "just triggered" flag, DCAY's
           running per-bounce level multiplier
X+0..63    free — DCAY's own ceiling/coefficient math, etc. (TONE filter
           history and BITS state deferred along with those knobs)
```

Exact word assignments beyond Y+9/Y+10 TBD during implementation — listed here
only to confirm the shape (one phase byte + a handful of bounce-engine state
words) fits comfortably inside the free 54 Y-words + 64 X-words, which it does
with enormous headroom (the old build used far fewer than this before even
needing `TEMP_X`).

## 4. State machine (fresh design, not copied from the old build)

Three phases, matching the brief's own description exactly:

- **IDLE** — silent, nothing captured. Entered on first INIT and after a bounce
  train fully decays.
- **CAPTURE** — reads the NBAL-blended neighbour signal, writes it into the
  `TRACK_BUFFERS` region at reduced internal sample rate (decimated, per the
  brief's explicit "more lo-fi, more time" tradeoff), and simultaneously feeds
  that same live signal to the dry side of MIX. GATE shapes which portion of the
  nominal capture window (trig-to-next-trig) actually gets recorded.
- **BOUNCE** — replays the captured buffer from its start; each full pass
  through the buffer re-processes the *buffer's own current contents* through
  DCAY's per-bounce level multiplier (TONE/BITS stages removed for v1, slot
  left in the signal chain for when they're reinstated) and writes the result
  back into the same buffer before advancing the gap (per BEND) and repeating.
  Ends when DCAY has reduced the signal below an inaudibility threshold, or the
  buffer has decayed for some bounded max-repeats safety limit (whichever comes
  first) — matching the brief's "runs its natural course" requirement.

**TRIG** sets a one-shot flag (CH's idiom, not EN's no-op — we need the flag; a
continuous-processor no-op TRIG like EN's doesn't fit a trig-gated capture
window). **RENDER** consumes that flag once, cancels whatever phase it was in,
and re-enters CAPTURE fresh — this is the "whatever was playing is cancelled"
behavior, done in our own state (separately from the firmware's audio-level
anti-click fade from §1).

**Explicitly avoiding the old build's confirmed Bug 1** (gap timer only running
during an idle sub-phase, so capture length leaked into perceived repeat rate):
this design has only three phases total, with no separate "waiting" sub-state —
the gap countdown is part of BOUNCE's own per-sample bookkeeping from the start,
not bolted on after the fact.

## 5. Hard constraints carried forward as physical facts, not reused code

These aren't "old build decisions we're choosing to reuse" — they're measured
properties of the DSP56303 hardware/budget that apply to any implementation:

- **A gap-restart check finer than block-rate (32 samples) is real work, and
  checking it every single sample for every one of a block's 32 samples, worst
  case, is measurably expensive** (the old build measured this at 5,584 cycles,
  over the 3,951 ceiling, before adding a floor). Budget for this from the start
  rather than discovering it late.
- **Declared cycle budgets across all 9 real stock NFX machines top out around
  3,528** (GOLD_STANDARD §4) — a useful sanity ceiling: if NFX-BO's measured cost
  approaches 3,900+, something is probably over-engineered relative to what any
  shipped machine needed.

## 6. Resolved by the user, 2026-10-29

- **NBAL**: carried forward from the old build's clean linear-crossfade
  implementation (confirmed good on hardware).
- **DCAY**: stays a hand-rolled once-per-bounce level multiplier (brief's
  original semantics), not the firmware's native `decay` transform — that idea
  is shelved as a possible v2 simplification to try only after v1 is tested.
- **BEND**: exponential/compounding multiply confirmed as the right shape;
  needs real-playback tuning of the multiplier range (not a formula question).
- **TONE and BITS**: shelved entirely for v1 — not declared as parameters, no
  signal-chain stages for them. Revisit once NBAL/GATE/RATE/BEND/DCAY/MIX are
  tested.

## 7. Settled, 2026-10-29

### GATE — resolved by derivation, no open number left

The brief's literal wording ("the time between the start of a triggered step
and the beginning of the next step") sounds self-timed, but self-timing a
*future* interval is exactly the flaw already confirmed fatal in the old
project (it estimates window length from the wrong interval on non-contiguous
patterns — see [[project_bounce_usr_machine]]). The fix: don't estimate a
future window at all.

- **WINDOW = the capture buffer's fixed maximum decimated length** (a function
  of `TRACK_BUFFERS` size and the chosen decimation factor, settled during
  implementation, not a knob-feel number). This is the hard ceiling regardless
  of pattern spacing.
- **An actual next TRIG still cancels capture early** — that's just the
  existing flag-driven "cancel whatever was playing, start fresh" behavior
  from §4, not something GATE needs to predict.
- **GATE shapes WINDOW itself, linearly, symmetric around center:**
  - `g` = GATE's bipolar value, `g ∈ [-1, +1]`, center knob = 0.
  - `g > 0` ("right, start later/skip beginning"): capture start delayed by
    `g * WINDOW` samples; captured length = `WINDOW * (1 - g)`; keeps the
    *tail* of the window.
  - `g < 0` ("left, stop early/skip end"): capture forced to stop at
    `(1 + g) * WINDOW` samples; captured length = `WINDOW * (1 + g)`; keeps
    the *head* of the window.
  - Both extremes (`g = ±1`) converge to capturing nothing — a clean,
    symmetric reading of "middle = whole window, each direction skips more of
    one side," with no separate magic constant to pick.

### RATE — curve settled, numeric range is a starting default only

- **Curve: `unipolar_square_q23`.** Squaring gives more of the knob's travel
  to small gap values — standard practice for a time/rate control where short
  settings are perceptually far more sensitive than long ones (the difference
  between a 10ms and 20ms gap is huge rhythmically; 1000ms vs. 1010ms is
  nothing). This is independent of the old project's granularity bug
  (`GAP_SAFETY_FLOOR`, §5) — that floor applies to the achievable minimum
  regardless of which curve maps the knob to it.
- **Range: floor = `GAP_SAFETY_FLOOR` (re-measured fresh for this codebase,
  not assumed to still be exactly 8 samples), ceiling = 1 second (44,100
  samples) as a starting default for "a longer initial pause."** This ceiling
  is a tunable constant, not a structural decision — adjust by ear once audio
  is actually playing, same as BEND's multiplier range (§6).

### DCAY — already specified by the brief itself, not an open question

The brief states the ceiling explicitly: *"Max setting for Decay means that
only as much as 99% of the signal energy is passed to the next bounce."*
**Ceiling = 0.99 per-bounce level multiplier** (Q23 ≈ `$7D70A4`) — not the old
build's ~0.9375 `DCAY_CEIL`, which was a different number chosen for a
different (now-superseded) reason. Treating "99% of signal energy" as a direct
amplitude multiplier (not power/RMS, which would be `sqrt(0.99) ≈ 0.995`) —
flagged here in case the user meant the stricter energy sense, but amplitude
is the natural reading for a "how much level survives" control.
