# NFX-BO — Technical Design (12-bit packing backport)

*NOTE added 2026-11-09: this machine was promoted to be the mainline
NFX-BO that day, retiring the original 24-bit build of the same name
(this file was written under this machine's own former name, NFX-B2,
and is otherwise unchanged below — every "NFX-BO" mention from here on
refers to that now-retired original, not to this file's own machine).*

*This file covers ONLY what's different from the original 24-bit
NFX-BO. For the base architecture (RATE/BEND/DCAY timing, the
concurrent capture/bounce state machine, the layered-capture blend,
every fixed-point/overflow fact already established) see that
original's own now-archived DESIGN.md (no longer present in this repo
now that it's retired — check git history, or NFX-BO's git-tracked
state as of 2026-11-09, if you need it) — none of that changed here.*

**Status**: implemented, assembled, packed, certified, functionally
verified. `NFXBO.asm56k` + `NFXBO.json` build to `NFXBO.mds` →
`NFX-BO.syx` (535 program words, 1 import, real `mds-certifier`
worst-case measured at **MKII 7400 / MKI 9500 / MKI-SRAM 9036** —
well over the real ~3000-cycle 16-track-safe ceiling, a structural
cost, not a fixable bug; see §9). History of hardware reports and
fixes: §7-8 cover two early rounds (a hardware-illegal `Jcc`-inside-
hardware-DO-loop instruction, found and fixed), §10-11 cover the
"crunched into harsh noise" / "harsh aliasing" reports and their TWO
real, independent root causes (§10: a residual-accumulator-extension
leak in `BOUNCE_ADVANCE`'s TOP path, a rare corruption under
GATE=0+fast-RATE; §11: a register clobber corrupting exactly 1
sample in every 4, ALWAYS, which turned out to be the dominant,
actually-audible cause — a periodic corruption at a fixed rate is
textbook aliasing). Both found and fixed 2026-11-07. **Not yet
re-tested on real hardware with the §10 fix.**

## 1. What changed: 12-bit sample packing

Backported from NUW-JT (2026-11-04), direct user request: "we
definitely need to update NFX-BO to use 12-bit sampling as well, if it
will give us longer sample times." Two signed 12-bit samples now share
one 24-bit Y-memory word, doubling effective capture length for the
same `DECIM`: `LOGICAL_BUFLEN = BUFLEN*2 = 3072` logical positions
instead of 1536 plain words. `CAP_POS`, `CAP_REMAIN`, `CAP_LEN_FINAL`,
and `BOUNCE_POS` are now all in LOGICAL units; `word-index =
logical>>1`, `sub-phase = logical&1` (0=top 12 bits, 1=bottom 12).
Quantize via `asr #12` (already sign-extended); pack by masking each
quantized half to `#$fff` and shifting the first left 12 before
adding; unpack by shifting to reposition (bottom half only) then
sign-extending (`asr #12`) then rescaling back to Q23 range (`asl
#12`, bottom 12 bits now zero — the SP-1200/S900-style quantization
floor this packing trades for 2x capacity).

Same critical toolchain fact this depends on, confirmed on NUW-JT
first and reused here as established, not re-verified from scratch:
two consecutive immediate-shift instructions naming the SAME register
silently merge into one net shift — every unpack sequence alternates
registers (shift on `b`, `move b1,a`, shift on `a`).

## 2. CAP_STORE: write-pairing (new logic, reused verbatim from NUW-JT)

`CAP_STORE` only ever writes a COMPLETE word once, after both logical
positions sharing it are ready — the exact write-pairing mechanism
NUW-JT already built and fixed a real reverse-specific bug in: each
event positions its OWN quantized value into its correct 12-bit slot
first (direction-independent), then separately decides whether it's
the first or second half of its pair based on direction:
`first_of_pair = (sub_phase == REVERSE_FLAG)`. The first event of a
pair is stashed in a new state word, `PENDING_HALF` (Y+31, reusing the
slot that held `SHIFT_EXP_CUR` during NFX-BO's own short-lived
live-DECIM-knob round); the second is combined with it (`add`, since
the two positioned halves never overlap in bits) and the complete word
is written. This reuses NUW-JT's already-proven fix directly — not
re-derived, since the bug class (reverse's start point being ODD when
`LOGICAL_BUFLEN` is even, scrambling a hardcoded "phase0 is always
first" assumption) is identical here.

## 3. REAL BUG FOUND (pre-existing in NFX-BO, NOT caused by 12-bit
## packing): the capture window dropped its last word

Found while testing the backport, using the exact "check the precise
last word" discipline NUW-JT's own round 2 established. NFX-BO's
`CAP_WINDOW_REMAIN` close-check was `ble` (branch if `<=0`) — the SAME
off-by-one NUW-JT had: when the countdown hits EXACTLY 0, `ble` ends
capture on that SAME sample, before the final decimated event (which
would fire on that exact sample) gets a chance to run, silently
dropping the very last logical sample of every single capture.

This bug is **independent of 12-bit packing** — it was present in the
original 24-bit NFX-BO the whole time, through all 12 rounds of
hardware testing, just never caught: losing one word out of 1536 at
the very tail of a long, `GATE`/`RATE`/`BEND`-variable capture is easy
to miss by ear. It was only surfaced here because adapting NUW-JT's
own "verify the exact last word, not just the first few" probe
discipline to NFX-BO happened to land on the identical edge.

Fixed the same way NUW-JT's own was: `ble` → `blt` (strictly negative),
letting `CAP_WINDOW_REMAIN` reach exactly 0 on a still-valid sample and
only ending the pass once it goes negative. Confirmed via
`probe_nfxbo.cpp`: forward capture's last logical word (1535) came
back as `0` (never written) before this fix, `7337727` (correct, dry
value) after.

**Worth considering separately**: since this is a real, independent
correctness bug, it may be worth backporting just this one-line fix to
NFX-BO's own main (24-bit) build too, rather than only fixing it here.
Not done as part of this round — flagged for a deliberate, separate
decision rather than silently also patching the other file.

## 4. BOUNCE_ADVANCE: read-modify-write, not write-once-per-pair

This is the part that genuinely differs in KIND from NUW-JT's own
12-bit work, not just a reused pattern: `BOUNCE_ADVANCE` reads AND
writes the SAME logical position every single decimated step,
compounding decay in place (there is no separate full-precision
"shadow" buffer — the packed buffer IS the only place a ringing
train's value lives between bounces). Unlike `CAP_STORE`'s
write-once-after-both-halves-ready pairing, this needs a genuine
read-modify-write every time: unpack OUR half, decay-multiply it,
quantize back to 12-bit, then preserve the OTHER half's original bits
(via a mask against the freshly re-read word) before writing the
complete word back.

**A new characteristic this introduces, worth knowing about**: decay
now re-quantizes to 12-bit on EVERY repeat, not just once at capture
time. `DCAY_MULT` already shrinks the signal every repeat and
`ACCUM_LEVEL`/`LEVEL_THRESHOLD` already bound how long a train can
ring, so this seems unlikely to be audible as more than "a bit more
lo-fi per repeat, same spirit as the 12-bit capture already trades for"
— but it hasn't been confirmed by ear, unlike most of NFX-BO's other
characteristics after 12 hardware-tested rounds.

### Architecture: branch once, not twice (and why)

The first working version branched on `sub_phase` TWICE — once to pick
the unpack shape, once (later) to pick the pack/preserve shape, with a
cached `n2` register carrying the decision between them. Restructured
(2026-11-04) into two full duplicated paths (`BOUNCE_ADVANCE`'s
fall-through for TOP, a separate `BOUNCE_BOTTOM` label for BOTTOM),
branching on `sub_phase` only ONCE, each path inlining its own
unpack→decay→quantize→pack→preserve sequence, converging only at the
shared `BOUNCE_COMBINE` (and sharing `BOUNCE_ADVANCE_FIRST`, since the
no-write first-pass case doesn't care about `sub_phase` at all).

This was a direct, measured response to a cycle-budget overage — see
§5. The two paths are a few small instructions larger in total code
size than the single-branch-twice version, but removing the SECOND
branch measured as worth real cycles on this emulator, more than the
duplicated instructions cost. A **separate** attempt — eliminating a
redundant Y-memory re-read instead of a redundant branch — measured
**zero** improvement (and on reflection, that attempt actually traded
one memory read for two register moves, a net instruction-count
increase, explaining the lack of gain). Lesson reinforced from NUW-JT's
own round 3: on this emulator, **branches are the expensive resource,
not memory reads** — don't assume otherwise, measure.

## 5. Cycle budget

Backporting 12-bit packing pushed the worst case well over budget
before optimization — NFX-BO's own pre-backport worst case was
3267/3951 (684 spare); the first working 12-bit version measured
**4084/3951**, 133 over. Closed via, in order:

1. **A test-harness bug, not a real one, found first**: every
   "continuing capture" cycle-check scenario was giving IDENTICAL
   numbers regardless of what should have differed — traced to
   `CAP_WINDOW_REMAIN` never being seeded by the harness at all
   (defaulting to 0 via Y-memory zero-init), so the window-close branch
   fired on EVERY sample regardless of other fields, silently
   short-circuiting capture's entire cost in every non-fresh-trig
   scenario. This gap existed in NFX-BO's OWN original harness too —
   never caught because BOUNCE's own worst case has always been higher
   regardless, so it never affected the REPORTED ceiling. Fixed by
   adding the missing field; capture scenarios then differentiated
   correctly.
2. **Caching `DCAY_MULT`** (computed once per block already, but
   re-read from Y-memory on every `BOUNCE_ADVANCE` event — up to
   8/block — and every restart's `ACCUM_LEVEL` check — up to 4/block)
   into a spare register (`n4`) instead. Combined with merging the
   pack/preserve branches (item 3 of this list, done in the same pass):
   4084 → 4017.
3. **An attempt to eliminate a redundant Y-memory read** (reading
   `BOUNCE_POS`/`CAP_POS` twice — once for word-index, once for
   sub_phase — instead of once with a register backup) measured
   **zero improvement** and was reverted — it traded 1 memory read for
   2 register moves, a net instruction increase, not a decrease.
4. **Splitting `BOUNCE_ADVANCE` into full TOP/BOTTOM duplicated paths**
   (§4 above), removing a second redundant branch entirely rather than
   just avoiding a redundant read: 4017 → **3932**, clearing budget
   with 19 spare.

19 cycles of margin is tight by this project's own historical
standards (NFX-BO's own rounds typically shipped with hundreds to
over a thousand spare) but within precedent already accepted —
NFX-BO's own round 9 shipped at ~41 spare and round 10 shipped at ~5
spare, both on direct user instruction to ship-and-test rather than
keep optimizing blind. Re-run `cyclecheck_nfxbo_v1.cpp` after any
further change to `DECIM`, the pack/unpack layer, or anything in
`CAP_STORE`/`BOUNCE_ADVANCE`.

## 6. Functional verification

`probe_nfxbo.cpp` confirms: forward capture packs correctly (exact
match against NUW-JT's own proven constant-dry value, `7337727`);
the window-boundary fix (§3) — the last logical word is no longer
dropped; reverse capture's write-pairing packs all 1536 words
correctly (same check as NUW-JT's own Test 5); and a precise
single-step `BOUNCE_ADVANCE` check (seed two DISTINCT known 12-bit
halves, force exactly one decimated step at each `sub_phase`, confirm
OUR half decayed in the expected direction and the OTHER half is
preserved EXACTLY) for both parities.

**A test-methodology trap worth recording**: an earlier version of
that single-step check used `SAMPLES_REMAINING=500`, intending "stream
long enough to not stop mid-test" — but `RENDER` always processes a
FULL 32-sample block per call, and with `DECIM=4` that means ~8
`BOUNCE_ADVANCE` events fire within ONE call, not one. The result
looked exactly like a real preserve-bug (the "preserved" half came back
changed) until direct in-ASM debug dumps (same technique as earlier
rounds' own `probe_rvrs.cpp`/`probe_mix_tone.cpp` false alarms) traced
it to 8 compounded events touching different positions, not a logic
error. Fixed by setting `SAMPLES_REMAINING=1`, so streaming (and
`BOUNCE_ADVANCE`) stops after sample 0 of the block — a genuine single
step. Same lesson as those earlier false alarms: when a result looks
impossible given otherwise-correct-looking code, suspect the TEST's
own state/timing assumptions before re-deriving the production logic
again.

## 7. First hardware test: "screeching noise, utterly unusable" — triage (2026-11-05)

The build described above (3932/3951, all probes passing) was NFX-BO's
first-ever real-hardware test, and it came back reported as "screeching
noise, utterly unusable" — a severe, total-failure report, not a subtle
quality complaint. This section records the triage, since none of it
was obvious from re-reading the source alone.

**Step 1 — local toolchain had silently broken.** Re-running the
existing probes (`probe_nfxbo.cpp`, `cyclecheck_nfxbo_v1.cpp`) failed
immediately with a Windows `STATUS_DLL_NOT_FOUND`. Root cause: this
project's C++ probes are compiled against a specific MinGW toolchain at
`C:/Users/thisi/AI/Workspace/Tools/mingw64/bin` (confirmed via
`dsp56300/build/CMakeCache.txt`'s `CMAKE_CXX_COMPILER`), which is NOT on
PATH by default — a prior session had it on PATH; this one didn't. Every
previously-built `.exe` that links `dsp56kEmu`/`assembler.h` needs that
directory's `libstdc++-6.dll`/`libgcc_s_seh-1.dll`/`libwinpthread-1.dll`
at *run* time, not just compile time. Fixed by rebuilding from source
with that compiler + the already-built static libs
(`dsp56kEmu`/`dsp56kBase`/`asmjit`/`vtuneSdk`, all under `dsp56300/build`)
and adding that directory to PATH before running. **Lesson for future
sessions**: if a previously-working probe/cyclecheck `.exe` suddenly
won't run, check this before assuming the binary or the source is
wrong — it's very likely just this PATH.

**Step 2 — the leading hypothesis (shift fusion in the TOP write-back
path) was investigated and DISPROVEN by direct execution.** Code review
of `BOUNCE_ADVANCE`'s TOP-half write-back spotted `asr #12,a,a` …
`and #>$fff,a` … `asl #12,a,a` — two immediate shifts naming the SAME
register (`a`), split only by a non-shift `and`, which looks like an
exact match for this project's own documented "two consecutive
immediate-shift instructions naming the same register silently merge,
regardless of what sits between them" hazard (the reason every unpack
sequence elsewhere alternates `b`→`a`). If it had fused, the quantize
and reposition steps would cancel to a net zero shift and corrupt every
TOP-half decay write. **This was wrong.** After fixing the toolchain
PATH (step 1) and rebuilding `probe_nfxbo.cpp`, the single-step test
printed a mathematically exact result (`TOP=1000 → 495` with
`DCAY_MULT≈0.495`, `1000*0.495=495`), proving the fusion does NOT occur
here. The apparent contradiction with `CAP_STORE`'s own safe-looking
code (which also has an `asr`/`asl` pair on `a`, just ~27 instructions
and a branch apart) suggests the real trigger condition is narrower
than the header comment's "regardless of what sits between them"
literally claims — most likely true back-to-back adjacency within a
straight-line run, not "anywhere in the same function." Not fully
pinned down, but empirically moot for this code path.

**Step 3 — a long-run dynamic trace confirmed the decay/stop machinery
itself is sound.** A new throwaway probe fired one trig at the JSON's
own default params (`RATE=32`, `DCAY=80`, `BEND=64`→steady,
`MIX=127`→isolate wet) and read `ACCUM_LEVEL`/`REPEATS_FIRED`/`PHASE`
directly every block. Result: `ACCUM_LEVEL` decayed smoothly and
monotonically from `8388607` to `1481` over exactly 19 repeats (matching
`DCAY_MULT≈0.495` and `LEVEL_THRESHOLD=2048` by hand calculation), then
`PHASE` correctly dropped to `0` (IDLE) at block 32734 — no divergence,
no runaway, no 12-bit value anywhere in the buffer exceeding the
±2047 range the packing format allows. (An earlier, shorter version of
this same test — 20000 blocks instead of ~33000 — looked like a
"never goes idle" runaway; it wasn't, it just hadn't run long enough at
this GATE/RATE combination's real ~55131-sample gap. Yet another
instance of this project's own recurring lesson: check the test's own
timing assumptions before trusting an alarming-looking result.)

**Step 4 — no definitive root cause found; one real risk-reduction fix
applied anyway.** Static + dynamic verification came back clean on
every hypothesis tried. One thing DID stand out as genuinely
unprecedented, independent of whether it's the actual cause:
`BOUNCE_ADVANCE` read the same indexed address (`y:(r3+n3)`) TWICE per
event — once to unpack, again later to recover the half it needs to
preserve — before writing it once. NFX-BO's own original (24-bit,
12-rounds-hardware-proven) `BOUNCE_ADVANCE` only ever reads a given
indexed address ONCE and writes it ONCE; this double-read-same-address
shape had never been exercised on real DSP56300 silicon anywhere in
this project. Fixed by stashing the original word into a free register
(`n5`) right after the first read, in both the TOP and BOTTOM paths,
and using that instead of re-reading memory — restoring the
single-read-single-write shape NFX-BO's own history has actually
proven. As expected from this project's own prior finding that
redundant memory reads aren't the costly resource on this emulator, the
cycle cost barely moved (3932 → 3934/3951, still 17 spare) — this was a
hardware-risk-reduction move, not an optimization, and functional
re-verification (both the single-step and the long-run decay-to-IDLE
probes) confirmed it changed nothing observable.

Also worth flagging as contributing risk, even though neither was
directly implicated: this was NFX-BO's first-ever hardware test of ANY
kind, and it shipped with only 19 (now 17) spare cycles against the
3951 budget — the tightest margin this project has shipped on NEW,
never-hardware-tested code (the two prior instances of ~41 and ~5 spare
cycles were both on NFX-BO's OWN already-12-rounds-proven logic, a much
lower-risk situation). If real silicon's cycle cost for any instruction
in the 12-bit pack/unpack layer differs from the emulator's model by
even a handful of cycles — plausible, given this project has already
found at least one case (the hardware do-loop + conditional branch
combination noted in the RVRS comment) where this emulator's cycle
accounting was surprising relative to naive expectation — a chronic
every-block overrun is a textbook cause of continuous, "utterly
unusable" audio corruption, distinct from an occasional glitch. This
remains unconfirmed and unfalsified; flagged for the user rather than
acted on blindly.

## 8. Second hardware test: "still unusable" AND "crashes the unit" (2026-11-06) — the real fix

User's follow-up report sharpened the picture considerably: not just
bad audio, but the unit **freezes and needs a power cycle**, after some
trigs/repeats (not immediately), with other tracks also running. A
full unit freeze is a qualitatively different failure class from
corrupted audio — it points at something disrupting the DSP's own
control flow or hardware state, not a wrong value in a calculation.

**Root cause, this time found with real confidence, not just "nothing
else turned up":** re-auditing every instruction mnemonic that appears
in `NFXBO.asm56k` but nowhere in NFX-BO's own 12-rounds-hardware-proven
`NFXBO.asm56k` (a targeted diff, not a re-read) turned up exactly one —
the `jeq >SKIP_BOUNCE` absolute/long jump inside `RENDER_LOOP`'s
hardware `do #32,RENDER_END` loop, introduced only because the 12-bit
packing backport's extra code pushed the branch distance past the
short-branch ±255-word range (see the comment this replaced, still
visible in version history). This was flagged as a candidate during
the FIRST triage (§7) too, but at the time there was no authoritative
basis to act on it beyond "no precedent in this project's history" —
this round found one.

**Confirmed via the official Motorola DSP56000 Assembler Reference
Manual** (`DSPASMRM.pdf`, the one the user supplied earlier — see
[[reference_dsp56300_official_docs]] — Appendix C, "Assembler Messages
— Errors"), quoted directly: *"Instruction cannot appear at last
address of a DO loop... within last 2/3 words of a DO loop. Some
instructions are restricted within a variable range of the DO
instruction loop address. These instructions include DO, ENDDO, JMP,
**Jcc**, JCLR, JSET, and moves to or from particular control
registers."* The same manual separately confirms `Jcc` is a **two-word
instruction**, grouped with `JMP`/`JSET`/`JCLR`/`JSR` as instructions
that cannot even be used with the `REP` directive for the same
pipeline reason. Plain short branches (`Bcc` — `beq`/`bra`/etc.) appear
in **neither** restricted list. This is a real, documented hardware
asymmetry between `Jcc` and `Bcc` regarding DO-loop interaction — not
pattern-matching or coincidence.

This `jeq`'s own position (near the top of `RENDER_LOOP`, nowhere near
`RENDER_END`) didn't technically trigger the manual's literal "last
2/3 words" case. That doesn't clear it: the `kitbasher` assembler used
to build this file is a third-party reimplementation of the Motorola
toolchain, not the genuine article, and this project has already found
one case this same week where the `dsp56300` emulator's own modeling of
a hardware-do-loop interaction diverged sharply from whatever real
silicon actually does (the ~4600-cycle do-loop/conditional-branch
anomaly noted in the RVRS header comment) — so neither "the assembler
didn't complain" nor "the emulator's cyclecheck/probes came back clean"
is proof this was safe on real hardware. Treating either as proof would
have been exactly the kind of unverified-against-real-hardware
assumption this project's whole discipline exists to catch.

**Fix**: replaced the single `jeq >SKIP_BOUNCE` with a two-hop
short-branch RELAY — `beq <RENDER_LOOP_SKIP_RELAY`, landing at a new
label placed within range of both the gate check and `SKIP_BOUNCE`,
which itself does a plain `bra <SKIP_BOUNCE`. Both hops use only the
`Bcc`/`Bra` short-branch form already proven throughout this file and
NFX-BO's own 12-round history — no instruction from either of the
manual's restricted lists appears anywhere in this file any more
(confirmed via grep: zero `jXX`/`jsr`/`jmp` instructions remain).

**Re-verified after the fix, not just reasoned about**: reassembled
clean (526 words, unchanged — the relay costs the same word count the
long jump did), cycle-checked (**3934/3951, 17 spare, unchanged** —
expected, since this only replaces one instruction's encoding shape,
not the logic), and both the single-step `BOUNCE_ADVANCE` probe and the
long-run decay-to-IDLE trace (§7's Step 3) came back byte-for-byte
identical to every prior run. Repacked and revalidated (`NFX-BO.syx`,
526 program words, cycles 3934/3951, slot U02).

This is now a well-evidenced fix, not a shot in the dark — but it still
hasn't been confirmed on the real hardware that reported the freeze.
If the freeze recurs after this fix, the cycle-margin risk flagged at
the end of §7 (17 spare cycles on first-ever-hardware-tested code) is
the next thing to pursue.

**Superseded by §9's real certifier finding below**: the real cycle
cost was never close to 3934/3951 at all -- the whole §5 cycle-budget
analysis used `dsp56300/cyclecheck`'s own emulator-timing model, which
this project later found badly underestimates real memory-wait-state
cost (see [[reference_mds_certifier_real_cycle_costs]]). The "17 spare
cycles" margin and its associated risk never applied to real hardware
in the first place -- the machine was always running several thousand
cycles over its real budget, a far more likely explanation for the
freeze than a razor-thin margin on an otherwise-correct measurement.

## 9. Round 2 (2026-11-06): fresh rebuild from NFX-BO's current build,
## and the real certified cost

Direct user request: "try and implement NFX-BO in 12 bit again." Not a
continuation of this file's own history above -- NFX-BO's own 24-bit
build had moved on since the original NFX-BO attempt forked from it
(picking up the FIRST_GAP_FLOOR stacking guard and DCAY_MULT register
caching, neither present in the version this backport originally
started from, plus the real `mds-certifier` methodology itself, which
didn't exist yet when §1-8 above were written). Rebuilt from scratch:
copied NFX-BO's CURRENT `NFXBO.asm56k` and re-applied the exact same
12-bit backport diff as before (LOGICAL_BUFLEN replacing BUFLEN for
all capture/bounce position/length tracking, CAP_STORE's write-pairing,
BOUNCE_ADVANCE's TOP/BOTTOM dual-path read-modify-write, both reused
VERBATIM from this file's own already-proven mechanism, not re-derived)
-- the original, shelved file is kept as a full folder snapshot in the
sibling `NFX-BO 12 Bit_pre_rebuild_backup/` directory, untouched.

**Lessons from the original attempt applied proactively, not
rediscovered**: `y_workset_words` was set to 32 (not 31) from the
start, and the shared PHASE=0 gate check at the top of `RENDER_LOOP`
was routed through a short-branch relay (`beq`->`bra`, same two-hop
shape as §8's own fix) from the FIRST assembly attempt, not added after
a hardware freeze. The relay turned out to be genuinely necessary again
(the gate check and `SKIP_BOUNCE` ended up 280 words apart, over the
+/-255-word short-branch range) -- confirms this isn't a one-off quirk
of the original code's exact shape, but a real, repeatable consequence
of how much extra code the 12-bit packing backport adds inside this
particular hardware `do` loop.

**Functionally re-verified via `probe_nfxbo.cpp`** (the same probe,
unchanged, run against the new build): CAP_POS advances at the exact
predicted rate, the window-boundary edge is captured correctly (last
LOGICAL word, 1535, packs to the same proven constant as NUW-JT's own),
reverse capture packs all 1536 words identically to forward, and the
precise single-step `BOUNCE_ADVANCE` check confirms both parities exactly
(TOP decays from 1000 to 495 at ~0.5 DCAY while BOTTOM stays EXACTLY at
-500, and the mirror case) -- all pass, matching the original attempt's
own functional correctness exactly.

**Real cost, this time measured with the actual authoritative tool from
the very first measurement** (quick dev-mode first, then the full
exhaustive `mds-certifier` run): quick MKII 6954 (consistent with the
original attempt's own quick estimate of ~6945, confirming this rebuild
is cycle-equivalent, not accidentally cheaper or more expensive), full
worst case **MKII 7393 / MKI-DRAM 9491 / MKI-SRAM 9029** -- still far
over the real 3000-cycle (MKII) 16-track-safe ceiling. Properly
certified and stamped via `mds_pack.py --certify`; `NFXBO.mds`/
`NFX-BO.syx` now carry this real MDS 1.1 header.

**Conclusion, same as the original attempt's own (§ Status update)
but now on solid footing from the start, not discovered after a
hardware incident**: this backport's real cost is structural (dual-
buffer NBAL blend, 12-bit pack/unpack on both capture and the decay-
compounding bounce path, every decimated step), not a fixable
implementation bug. Unlike NUW-JT (see that project's own DESIGN.md
Sec 14), this machine's bounce-restart timing is data-dependent (driven
by RATE/BEND, not a fixed compile-time stride), so the bulk-pass
restructuring that cut NUW-JT's own real cost by ~10% doesn't carry
over directly -- a future attempt at closing THIS machine's gap would
need a different, more involved design, or the same class of feature-
level cut NFX-BO's own 24-bit build is still waiting on. Not attempted
this round.

## 10. Round 3 (2026-11-07): the REAL noise bug, found and fixed

Hardware report after the round-9 rebuild: "whatever is sampled is
crunched into harsh noise." Two hypotheses were investigated and
BOTH ruled out before the real cause was found:

1. **Decay-stuck hypothesis** -- a dedicated decay-trajectory probe
   first seemed to confirm the value freezing at a nonzero level, but
   the probe itself had a bug (`GAP_REMAIN` never re-armed between
   iterations, letting an unintended internal restart corrupt the
   measurement). Once fixed, the original code decayed cleanly to
   exactly 0 (457 steps, matching the ~460-step theoretical estimate
   within 1%). Ruled out.
2. **Capture/bounce word-sharing race** -- 12-bit packing means two
   logical positions share one physical word, unlike NFX-BO's 24-bit
   original where every position has its own dedicated word. Given
   `GATE=0`+fastest-`RATE` keeps both capture and bounce active near
   position 0 for an extended stretch, this looked like a strong
   candidate: a dedicated test (`probe_nfxbo.cpp` Test 4b) scanning
   the buffer after 50 blocks found real, mathematically-impossible
   corruption (negative values from decaying a positive constant).
   But a FOLLOW-UP test (Test 7) reproduced the EXACT SAME corruption
   with capture completely disabled (`CAP_REMAIN=0`) -- a pure,
   isolated sequence of alternating TOP/BOTTOM `BOUNCE_ADVANCE` visits
   to one word, no capture involved at all. Ruled out.

**The real cause**: `BOUNCE_ADVANCE`'s TOP-half quantize/reposition
sequence --
```
asr #12,a,a   ; quantize
and #>$fff,a
asl #12,a,a   ; reposition into the top 12-bit slot
```
-- leaks residual accumulator-extension state (surviving from the
`mpy` a few instructions earlier) into the positioned value's own LOW
12 bits, confirmed via direct in-ASM debug taps (expected a clean
value with zeros below bit 12, got nonzero garbage there instead).
This is harmless when the SAME half repeatedly decays alone (the next
unpack re-shifts those stray bits away before anything ever reads
them) -- which is exactly why the single-half decay-trajectory probe
above found nothing wrong. But the moment `BOUNCE_COMBINE` ORs this
"positioned" value against the PRESERVED other half (exactly what
happens as `BOUNCE_POS` walks forward through consecutive words, or
revisits early words after a fast restart), the leaked bits silently
corrupt it, compounding worse with every further visit -- directly
matching the user's own description ("whatever is sampled is
crunched into harsh noise").

This is precisely the same-register-double-shift hazard already
documented at the top of this file and already fixed elsewhere in
this codebase (GATE/BEND/RVRS's own exact-extreme handling) --
`and` does not perform a full register reload the way a genuine
cross-register `move` does, so residual extension-bit state survives
through it. An EARLIER attempt at this exact fix (inserting the same
reload) had been tried and REVERTED mid-investigation, because the
test that seemed to validate it (the decay-trajectory probe) was
itself still running on the BUGGY `GAP_REMAIN`-unarmed harness at the
time -- once that harness bug was separately fixed, the reverted fix
looked unnecessary by comparison. In hindsight the harness bug masked
a real, separate, smaller inaccuracy (the fix also corrects the
single-half decay rate itself -- see below) on top of the catastrophic
alternating-visit corruption it was actually needed for.

**Fix**: force a genuine reload through a different register (`move
a1,b` / `move b1,a`) between the `and` and the `asl`, same proven
idiom already used by the unpack code immediately above this exact
function. Confirmed via `probe_nfxbo.cpp`'s Test 7 (the alternating-
visit injection): every value now decays monotonically, symmetrically,
and stays positive for a positive input -- no sign flips, no garbage.

**A secondary, smaller effect of the same bug, also now corrected**:
the single-half decay-trajectory probe's own step-to-zero count
changed from 457 to 233 (DCAY=max) and from 18 to 15 (DCAY=default).
The leaked low-bit garbage was ALSO introducing a tiny systematic
rounding bias in the single-half case (an occasional spurious +1,
exactly as the original -- since-superseded -- bug writeup had
hypothesized), slowing convergence to zero by roughly 2x versus the
mathematically correct rate. The pre-fix 457-step result wasn't proof
of correctness -- it was a coincidence landing close to the rough
~460-step theoretical estimate, while the genuinely correct rate (233
steps) is meaningfully faster. Not independently audible as a
separate symptom (the catastrophic alternating-visit corruption
dominates), but worth knowing the "stuck decay" dead-end from round 2
wasn't entirely a false lead after all -- just not THIS bug's main
symptom.

**Re-certified after the fix**: cycle cost is UNCHANGED --
**MKII 7393 / MKI 9491 / MKI-SRAM 9029**, identical to the pre-fix
build. The two added instructions (`move a1,b` / `move b1,a`) sit
off the certifier's own identified worst-case path (a trigger-
transition block), so they add zero cost to the declared ceiling
despite fixing a severe, audible correctness bug. Program size grew
by 2 words (531->533, including the .mds header's own import word).
Repacked and re-validated: `NFXBO.mds`, `NFX-BO.syx` (slot U02).

## 11. Round 4 (2026-11-07, same day): the REAL dominant cause --
## "harsh aliasing noise", still present after §10's fix

User's follow-up, after installing the §10 fix: "B2 has the same harsh
aliasing noise... as BO did and we fixed." That phrasing was the key
clue -- NFX-BO's own real historical fix (see `NFX-BO/DESIGN.md`,
"Decimated-hold playback with LINEAR INTERPOLATION... a hard zero-
order hold... is a classic source of harsh aliasing") was specifically
about the decimated-hold PLAYBACK path, not the decay/corruption path
§10 had just fixed. That immediately exposed a real gap in EVERY probe
test this file has ever used: all of them fed a CONSTANT dry signal,
which can never reveal a staircase/hard-hold bug (a constant value
"ramping smoothly" and "held flat" are indistinguishable when there's
nothing to interpolate between).

Built a new test (`probe_nfxbo.cpp` Test 8) that direct-injects a
genuinely RAMPED buffer and traces the real per-sample playback output
one real sample at a time (same proven injection technique as Test
5/6). The result immediately showed the real bug: a perfectly smooth
ramp for 3 out of every 4 samples, with the 4th (the exact sample
where `BOUNCE_ADVANCE` fires) replaced by wildly inconsistent,
uncorrelated garbage.

**Root cause**: the wet-output accumulator (`b`, set once per sample
at the top of the bounce-streaming code to "this sample's wet output")
gets reused as scratch INSIDE `BOUNCE_ADVANCE` itself -- both the TOP
path's own unpack (`move y:(r3+n3),b`) and especially `BOUNCE_BOTTOM`'s
4-step shift dance overwrite it repeatedly while unpacking/requantizing
the 12-bit sample. `BOUNCE_ADVANCE` never restores `b` before falling
through to `SKIP_BOUNCE`'s shared output-combine code, which reads
`b1` assuming it still holds the value set at entry. On the 3-in-4
samples that DON'T fire an advance (just hold/ramp), `b` is never
touched after being set, so those samples are correct -- which is
exactly why the single-half decay tests, the alternating-visit test,
and every other test up to this point never caught it: none of them
ever inspected a REAL per-sample PLAYBACK trace with a non-constant
signal. A sample getting replaced by unrelated data at a perfectly
fixed, periodic rate (1-in-DECIM, i.e. 1-in-4, forever) is textbook
digital aliasing -- a tone at Fs/DECIM (~11kHz) and its harmonics
riding on top of whatever's actually playing, far more severe and
far more constantly present than §10's own rare GATE=0+fast-RATE
corruption. This is almost certainly what the user has actually been
hearing as "harsh noise" / "harsh aliasing" the whole time.

**Fix**: stash `b1` into `n6` (confirmed genuinely free scratch, per
this file's own NBAL/MIX-caching comment) immediately after it's set,
and restore `b` from `n6` right before falling into `SKIP_BOUNCE` --
but ONLY on the `BOUNCE_ADVANCE` path specifically (the other path,
which never touches `b` again, needs no restore and gets none).

**Verified**: re-ran Test 8 against the fixed build -- the per-sample
trace is now a single, perfectly smooth, unbroken ramp across all 24
samples traced, zero discontinuities. Re-ran the FULL probe suite
(Tests 1-8) -- all pass, no regressions, decay trajectories unchanged
from §10's own fix. Re-certified: **MKII 7393->7400 / MKI 9491->9500 /
MKI-SRAM 9029->9036** (+7-9 cycles, the two added instructions costing
almost nothing). Repacked and revalidated: `NFXBO.mds`, `NFX-BO.syx`
(535 words, slot U02).

**Not yet re-tested on real hardware with this fix.**

**Checked NFX-BO's current build for the same clobber shape**: it
doesn't have it, and can't -- `NFXBO.asm56k`'s own `BOUNCE_ADVANCE`
reads the buffer via a single plain `move y:(r3+n3),x0` (24-bit, no
pack/unpack needed), never touching `b` at all. The 12-bit backport's
own multi-step unpack dance (needed to recover a signed 12-bit half
from a packed word) is what requires `b` as scratch in the first
place -- this bug is specific to NFX-BO, not a latent issue in
NFX-BO's own 24-bit original.
