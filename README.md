# MDX 2.0 User Machines

Custom DSP56300 "User Machines" for the Elektron Machinedrum, built against
MDX's X.20 ("MDX 2.0") USR-machine system — installable custom synthesis/
effects code that runs directly on the Machinedrum's own DSP.

Each machine lives in its own subfolder, with its own README covering what
it does, its parameters, build/install instructions, and status.

## Machines

- [`NFX-BO/`](NFX-BO/) — a bouncing-ball delay: captures a short, decimated
  blend of the two tracks before it on each trig, then plays it back as a
  series of discrete, decaying, bouncing echoes, 12-bit sample packing
  doubling capture length for a given `DECIM`. Confirmed working on real
  hardware. (Promoted 2026-11-09 from a sibling build then named NFX-B2,
  retiring an earlier 24-bit NFX-BO of the same behavior but half the
  capture length — see the machine's own README for that history.)
- [`NUW-JT/`](NUW-JT/) — a self-sampling overdub/freeze machine: each trig
  plays its own capture buffer through once, optionally blending a fresh
  live capture back in (REC) instead of a decaying repeat train. Built from
  NFX-BO's patterns; 12-bit sample packing doubles its capture length.
- [`NUW-TS/`](NUW-TS/) — forks of NUW-JT adding a
  bidirectional tape-speed/pitch-bend knob (SPED) on playback only

## `refs/`

Local-only reference material (disassembled stock Elektron NFX machines,
used as a gold standard for how to correctly structure an NFX-category
machine) — **not tracked in this repo** (see `.gitignore`); it's
disassembled from Elektron's proprietary factory firmware and isn't
redistributable. Useful to have alongside this repo when building a new
machine, but it travels separately, not with the git history.

## Build toolchain (external — not included in this repo)

Building any machine here from source needs three separate external tools,
cloned as sibling directories (next to this repo's own parent, under
`Machinedrum/`) rather than vendored:

- [`kitbasher`](https://github.com/etcetc000/kitbasher) (GPLv3) — supplies
  the real DSP56300 cross-assembler used as the `.asm56k` front end, plus
  `tools/mds_assemble.py` (the `.asm56k` → `.lod` step).
- [`mds-tools`](https://github.com/jmamma/mds-tools) (no explicit license —
  check before redistributing) — supplies `tools/mds_pack.py` (packaging +
  certification, `.json`+`.lod` → `.mds`) and `tools/mds_to_syx.py`
  (sysex-encoding, `.mds` → `.syx`), plus `build/mds-certifier.exe`, the
  cycle-accurate certifier `mds_pack.py --certify` calls out to. **Always
  use `mds-tools/tools/`, never the stale `MDS/tools/` copies** — the
  latter don't understand MDS 1.1's 3-way (MKII/MKI/MKI-SRAM) cycle
  declaration and will reject or mis-stamp a valid package.
- [`dsp56300`](https://github.com/dsp56300/dsp56300) (GPLv3) — DSP56300
  emulator; `mds-certifier.exe` is built against it. Only needed directly
  if you want to cycle-check/simulate outside the certifier.

### Running the build yourself

`build.py` in this repo's own root wraps all three steps for any one
machine:

```sh
python build.py NUW-TS              # full build: assemble, pack+certify, sysex-encode
python build.py NFX-BO --slot 1     # override the destination USR slot
python build.py SYN-PX --draft      # skip certify for a quick sanity check (produces an uninstallable DRAFT .mds, no .syx)
```

**`mds-certifier.exe` needs MinGW's `bin` directory on `PATH` at runtime**
(it's a MinGW-built binary, not MSVC — without this it fails silently with
`STATUS_DLL_NOT_FOUND`, exit code `-1073741511`). `build.py` sets this
itself; if you ever run the three steps by hand instead, set it first:

```sh
# bash/git-bash
export PATH="/c/Users/thisi/AI/Workspace/Tools/mingw64/bin:$PATH"
```
```powershell
# PowerShell
$env:PATH = "C:\Users\thisi\AI\Workspace\Tools\mingw64\bin;$env:PATH"
```

The manual three-step equivalent, run from inside a machine's own folder
(what `build.py` does under the hood — useful if you want to pass extra
flags `build.py` doesn't expose, like `mds_bitmap_export.py`'s round-trip
for hand-editing an icon in a real image editor):

```sh
# 1. assemble: .asm56k -> .lod
python ../../../../tools/mds_assemble.py <PREFIX>.asm56k --out <PREFIX>.lod --symbols-out <PREFIX>.symbols.json

# 2. package + certify + bundle the icon: .json + .lod -> .mds
python ../../../../mds-tools/tools/mds_pack.py <PREFIX>.json <PREFIX>.lod --format lod --bitmap <PREFIX>_icon.pbm --certify --report <PREFIX>_cert.json -o <PREFIX>.mds

# 3. sysex-encode: .mds -> .syx
python ../../../../mds-tools/tools/mds_to_syx.py <PREFIX>.mds --slot N -o <Display-Name>.syx
```

(`<PREFIX>` = the machine's folder name with its hyphen removed, e.g.
`NUW-TS` → `NUWTS` — holds for every machine in this repo so far.)

Step 2 is the slow one: a real exhaustive, cycle-accurate fuzz
certification, not a quick estimate — expect it to take several minutes,
longer if you're building more than one machine at once.

Flash the resulting `.syx` to the Machinedrum over MIDI to install it into
a USR machine slot (U01–U16). Only install machine code from sources you
trust — it runs directly on the DSP.

See each machine's own README for machine-specific build notes (its exact
slot convention, any extra build flags) beyond this general pipeline.

## License

TBD.
