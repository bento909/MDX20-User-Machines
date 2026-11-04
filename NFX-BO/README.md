# NFX-BO

A custom Elektron Machinedrum "User Machine" (NFX effect category) — on each
trig, captures a short blend of the two tracks before it and plays it back as
a series of discrete, decaying, bouncing-ball-style echoes. See `BRIEF.md` for
the design brief (what it should sound/feel like) and `DESIGN.md` for the
technical design (parameter transforms, memory layout, state machine).

## Status

v1 ships 7 parameters — **NBAL, GATE, RATE, BEND, DCAY, MIX, RVRS**
(reverse-capture probability) — implemented, assembled, packed, and
cycle-checked (worst case 3267/3951 cycles). **Hardware testing is in
progress**; see `TODO.md` (kept at `_authoring\resource\`, not alongside
this file) for the current round of fixes and what's still unverified by
ear.

TONE and ALFC (anti-aliasing filter knobs explored mid-project) were tried
and removed — the real fix for decimation aliasing turned out to be
`DECIM` itself (a compile-time constant in `NFXBO.asm56k`, not a knob), not
filtering. BITS was shelved early and never built. Pitch-bend is a known
future direction, deferred to its own round (needs resampling this
decimated-hold engine doesn't have yet).

## Parameters

| # | Knob | Range | What it does |
|---|------|-------|---------------|
| 1 | NBAL | unipolar | Neighbour blend: 0 = two tracks back (far), max = one track back (near). |
| 2 | GATE | bipolar | Shapes the capture window around center (full window): one side delays the start (keeps the tail), the other stops early (keeps the head). |
| 3 | RATE | unipolar, squared | Gap before the first repeat. |
| 4 | BEND | bipolar | Per-repeat gap multiplier: center = steady, one side shrinks the gap each repeat (speeding up), the other grows it (slowing down). |
| 5 | DCAY | unipolar | How much level survives each repeat (max ≈ 99%). |
| 6 | MIX | unipolar | Dry/wet. |
| 7 | RVRS | bipolar | Reverse-capture probability: one extreme always reverses this trig's capture, the other never does, center is a 50/50 coin flip (every value between is the probability). |

`DECIM` (capture/playback decimation — trades capture length for
fidelity) is **not a knob**, a compile-time constant near the top of
`NFXBO.asm56k` (currently 4, ≈139ms at full capture length). Raise it for
longer, more lo-fi captures; lower it for shorter, cleaner ones — edit and
rebuild. It was briefly a live knob but got dropped after a real bug (see
`TODO.md` Round 12); DECIM>8 combined with the stale interpolation-shift
bug made it misbehave badly above knob~64, so it's compile-time again.

A fresh trig's capture also layers in whatever bounce was still ringing
from the *previous* trig (summed and clamped, not a simple overwrite) —
hits that land close together build on each other instead of each always
starting from a clean slate. No knob for this; it's always on.

## Repo contents

- `BRIEF.md` — design brief
- `DESIGN.md` — technical design notes
- `NFXBO.asm56k` — DSP56300 assembly source (the machine itself)
- `NFXBO.json` — machine manifest (parameters, transforms, memory/import declarations)
- `NFXBO.lod` / `NFXBO.mds` / `NFX-BO.syx` — build outputs (see Build below)
- `NFXBO.symbols.json` — label/address table from the assembler

Open items and hardware-test history (`TODO.md`), plus test recordings
and reference images, now live in `_authoring\resource\`, not in this
folder.

## Build toolchain (external — not included in this repo)

Building from source needs three separate external tools, cloned as sibling
directories rather than vendored here:

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
python tools/mds_assemble.py NFXBO.asm56k --out NFXBO.lod --symbols-out NFXBO.symbols.json

# 2. package: .json + .lod -> .mds
python MDS/tools/mds_pack.py NFXBO.json NFXBO.lod --format lod -o NFXBO.mds

# 3. transfer-encode: .mds -> .syx
python MDS/tools/mds_to_syx.py NFXBO.mds --slot 1 -o NFX-BO.syx
```

(adjust paths to wherever you clone each dependency)

Flash the resulting `NFX-BO.syx` to the Machinedrum over MIDI to install it
into a USR machine slot (U01–U16). Only install machine code from sources you
trust — it runs directly on the DSP.

## Not included

This repo deliberately excludes any disassembled/extracted Elektron factory
firmware content used during development (see `.gitignore`) — that material
is proprietary and isn't redistributable.

## License

TBD.
