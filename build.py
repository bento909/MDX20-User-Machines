#!/usr/bin/env python3
"""Build one machine in this repo: assemble -> pack+certify -> sysex-encode.

Usage (run from this repo's root, i.e. the folder this file is in):
    python build.py NUW-TS
    python build.py NFX-BO --slot 1
    python build.py SYN-PX --draft          # skip certify, quick sanity check only

Looks for <machine>/<PREFIX>.asm56k, .json and (if present) _icon.pbm,
where PREFIX is the machine folder name with its hyphen removed
(NUW-TS -> NUWTS, NFX-BO -> NFXBO, SYN-PX -> SYNPX) -- matches this
repo's own naming convention for every machine folder so far.

See README.md's own "Build toolchain" section for the manual three-step
version of this pipeline and the external tools it depends on.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MACHINEDRUM_ROOT = REPO_ROOT.parent.parent.parent  # Machines -> _authoring -> USR-Machines -> Machinedrum
TOOLS = MACHINEDRUM_ROOT / "tools"
MDS_TOOLS = MACHINEDRUM_ROOT / "mds-tools" / "tools"
MINGW_BIN = r"C:\Users\thisi\AI\Workspace\Tools\mingw64\bin"  # mds-certifier needs this on PATH


def run(cmd, env=None):
    print("+ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, env=env)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("machine", help="machine folder name, e.g. NUW-TS")
    ap.add_argument("--slot", type=int, default=1, help="destination USR slot, 1..16 (default: 1 -- you choose the real destination at install time in C6 anyway)")
    ap.add_argument("--draft", action="store_true", help="skip --certify (fast, but the resulting .mds is a DRAFT and cannot be installed)")
    args = ap.parse_args()

    machine_dir = REPO_ROOT / args.machine
    if not machine_dir.is_dir():
        sys.exit(f"no such machine folder: {machine_dir}")

    prefix = args.machine.replace("-", "").replace(" ", "")
    slot = args.slot

    asm = machine_dir / f"{prefix}.asm56k"
    lod = machine_dir / f"{prefix}.lod"
    symbols = machine_dir / f"{prefix}.symbols.json"
    manifest = machine_dir / f"{prefix}.json"
    mds = machine_dir / f"{prefix}.mds"
    cert = machine_dir / f"{prefix}_cert.json"
    icon = machine_dir / f"{prefix}_icon.pbm"
    syx = machine_dir / f"{args.machine}.syx"

    for required in (asm, manifest):
        if not required.exists():
            sys.exit(f"missing expected file: {required}")

    env = os.environ.copy()
    env["PATH"] = MINGW_BIN + os.pathsep + env.get("PATH", "")

    # 1. assemble: .asm56k -> .lod
    run(["python", TOOLS / "mds_assemble.py", asm, "--out", lod, "--symbols-out", symbols])

    # 2. package (+ certify, + bundle the icon if one exists): .json + .lod -> .mds
    pack_cmd = ["python", MDS_TOOLS / "mds_pack.py", manifest, lod, "--format", "lod", "-o", mds]
    if icon.exists():
        pack_cmd += ["--bitmap", icon]
    if not args.draft:
        pack_cmd += ["--certify", "--report", cert]
    run(pack_cmd, env=env)

    if args.draft:
        print(f"\nDone (DRAFT): {mds}")
        print("Draft packages have no certified cycle budget and mds_to_syx.py")
        print("refuses to sysex-encode them -- rerun without --draft to get a real .syx.")
        return

    # 3. sysex-encode: .mds -> .syx
    run(["python", MDS_TOOLS / "mds_to_syx.py", mds, "--slot", slot, "-o", syx])

    print(f"\nDone: {syx}")


if __name__ == "__main__":
    main()
