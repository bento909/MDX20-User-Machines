# MDX 2.0 User Machines

Custom DSP56300 "User Machines" for the Elektron Machinedrum, built against
MDX's X.20 ("MDX 2.0") USR-machine system — installable custom synthesis/
effects code that runs directly on the Machinedrum's own DSP.

Each machine lives in its own subfolder, with its own README covering what
it does, its parameters, build/install instructions, and status.

## Machines

- [`NFX-BO/`](NFX-BO/) — a bouncing-ball delay: captures a short, decimated
  blend of the two tracks before it on each trig, then plays it back as a
  series of discrete, decaying, bouncing echoes. In active development.
- [`NFX-UW/`](NFX-UW/) — a self-sampling overdub/freeze machine: each trig
  plays its own capture buffer through once, optionally blending a fresh
  live capture back in (REC) instead of a decaying repeat train. Built from
  NFX-BO's patterns; 12-bit sample packing doubles its capture length. In
  active development.

## `refs/`

Local-only reference material (disassembled stock Elektron NFX machines,
used as a gold standard for how to correctly structure an NFX-category
machine) — **not tracked in this repo** (see `.gitignore`); it's
disassembled from Elektron's proprietary factory firmware and isn't
redistributable. Useful to have alongside this repo when building a new
machine, but it travels separately, not with the git history.

## Build toolchain (external — not included in this repo)

Building any machine here from source needs three separate external tools,
cloned as sibling directories rather than vendored:

- [`kitbasher`](https://github.com/etcetc000/kitbasher) (GPLv3) — supplies
  the real DSP56300 cross-assembler used as the `.asm56k` front end.
- [`MDS`](https://github.com/jmamma/MDS) — supplies the packaging/sysex-
  conversion tools and the official Machine Dump Standard spec.
- [`dsp56300`](https://github.com/dsp56300/dsp56300) (GPLv3) — DSP56300
  emulator; only needed for cycle-checking/simulating, not required to
  build.

See each machine's own README for its exact build steps.

## License

TBD.
