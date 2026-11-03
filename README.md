# NFX-BO

A custom Elektron Machinedrum "User Machine" (NFX effect category) — on each
trig, captures a short blend of the two tracks before it and plays it back as
a series of discrete, decaying, bouncing-ball-style echoes. See `BRIEF.md` for
the design brief (what it should sound/feel like) and `DESIGN.md` for the
technical design (parameter transforms, memory layout, state machine).

## Status

v1 (NBAL/GATE/RATE/BEND/DCAY/MIX — TONE/BITS deferred) is implemented,
assembled, packed, and cycle-checked. **Hardware testing is in progress**; see
`TODO.md` for the current round of fixes and what's still unverified by ear.

## Repo contents

- `BRIEF.md` — design brief
- `DESIGN.md` — technical design notes
- `NFXBO.asm56k` — DSP56300 assembly source (the machine itself)
- `NFXBO.json` — machine manifest (parameters, transforms, memory/import declarations)
- `NFXBO.lod` / `NFXBO.mds` / `NFX-BO.syx` — build outputs (see Build below)
- `NFXBO.symbols.json` — label/address table from the assembler
- `TODO.md` — open items and hardware-test history

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
