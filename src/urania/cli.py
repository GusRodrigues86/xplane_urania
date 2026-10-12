"""
cli.py - Command line interface. Without a command, Urania opens the window (gui.py).

    urania                                   open the window
    urania check [--xplane DIR] [--out DIR]  check this computer and find the input files
    urania build --stars F --milkyway F [--xplane DIR | --xsa F --dat F] [--out ZIP] [options]
    urania verify FILE.dat                   decode each row like the shader
    urania info FILE.xsa                     show the gains in a Urania shader
    urania decompile --xsa F --out DIR       write the stock GLSL (study only; do not publish)
"""
import argparse
import sys
import zipfile

from urania import __version__, inputs, pipeline, syscheck, xplane
from urania.engine import night_sky, shaders, spirv
from urania.errors import UraniaError

MARK = {syscheck.OK: "ok  ", syscheck.WARN: "warn", syscheck.FAIL: "FAIL"}


def cmd_check(args):
    items = syscheck.run_all(args.out, args.tools)
    for it in items:
        print(f"[{MARK[it.status]}] {it.name}: {it.detail}")
        if it.fix:
            print(f"        fix: {it.fix}")
    roots = [args.xplane] if args.xplane else xplane.find_installs()
    if not roots:
        print("[warn] X-Plane 12: no install found. Use --xplane DIR.")
    for root in roots:
        c = inputs.validate_xplane(root)
        print(f"[{'ok  ' if c.ok else 'FAIL'}] X-Plane folder {root}: {c.message}")
        if c.warning:
            print(f"        note: {c.warning}")
        if c.ok:
            for key, (path, note) in inputs.autodetect(root).items():
                print(f"        {key}: {path or 'NOT FOUND'} ({note})")
    return 1 if syscheck.blocking(items) else 0


def cmd_build(args):
    root = args.xplane
    if not root and not (args.xsa and args.dat):
        found = xplane.find_installs()
        if not found:
            raise UraniaError("No X-Plane 12 install found. Use --xplane DIR (or --xsa and --dat).")
        root = found[0]
        print(f"X-Plane folder: {root}")
    overrides = shaders.parse_set_pairs(args.set)
    if args.screen_height:
        overrides["VIEWPORT_H"] = args.screen_height
    if args.no_moon:
        overrides["MOON"] = 0
    req = pipeline.BuildRequest(stars=args.stars, milkyway=args.milkyway, out_zip=args.out, xplane_root=root,
                                xsa=args.xsa, dat=args.dat, overrides=overrides, airglow=args.airglow,
                                allow_any_version=args.allow_any_version, tools_dir=args.tools,
                                keep_work=args.keep_work)

    def step(n, total, title):
        print(f"== {n}/{total} {title}", flush=True)

    r = pipeline.run_build(req, log=lambda t: print(t, flush=True), step=step)
    print(f"\nDone: {r.zip_path}\nSHA-256 {r.zip_sha256}\nReport: {r.report_path}")
    print("Install: close X-Plane, extract the zip into the X-Plane 12 folder (the folder with \"Resources\").")
    return 0


def cmd_verify(args):
    r = night_sky.verify(args.file)
    for key in sorted(r.counts):
        print(f"  {key:14s} {r.counts[key]:7d} rows")
    for e in r.errors[:50]:
        print(f"  {e}")
    print(f"  errors: {len(r.errors)}")
    return 1 if r.errors else 0


def cmd_info(args):
    print(f"patched: {spirv.is_patched(args.file)}")
    for name, value in spirv.read_gains(args.file).items():
        print(f"  {name} = {value:g}")
    return 0


def cmd_decompile(args):
    shaders.decompile_xsa(args.xsa, args.out, args.tools, log=print)
    return 0


def parser():
    ap = argparse.ArgumentParser(prog="urania", description=f"Urania {__version__}: night sky for X-Plane 12.4.4+.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--version", action="version", version=f"Urania {__version__}")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("check", help="check this computer and find the input files")
    p.add_argument("--xplane", help="X-Plane 12 folder (default: all installs that X-Plane lists)")
    p.add_argument("--out", help="output folder for the zip (checks space and write access)")
    p.add_argument("--tools", help="folder with glslangValidator, spirv-val and spirv-cross")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("build", help="build the install zip")
    p.add_argument("--stars", required=True, help="stars.8.json, or the d3-celestial-0.7.35.tgz")
    p.add_argument("--milkyway", required=True, help="milkyway_2020_4k.exr")
    p.add_argument("--xplane", help="X-Plane 12 folder (default: the first install that X-Plane lists)")
    p.add_argument("--xsa", help="original astronomical.xsa (default: from the X-Plane folder)")
    p.add_argument("--dat", help="original earth_astro.dat (default: from the X-Plane folder)")
    p.add_argument("--out", default=pipeline.DEFAULT_ZIP_NAME, help=f"zip to write (default {pipeline.DEFAULT_ZIP_NAME})")
    p.add_argument("--screen-height", type=int, help="screen height in px (VIEWPORT_H, default 1080)")
    p.add_argument("--airglow", action="store_true", help="add a faint glow over the full sky")
    p.add_argument("--no-moon", action="store_true",
                   help="keep the X-Plane moon (no moonlit sky glow, no moon phase light law)")
    p.add_argument("--set", action="append", metavar="NAME=VALUE", help="change a shader setting (repeat for more)")
    p.add_argument("--allow-any-version", action="store_true", help="build also for X-Plane older than 12.4.4")
    p.add_argument("--tools", help="folder with glslangValidator, spirv-val and spirv-cross")
    p.add_argument("--keep-work", action="store_true", help="keep the work folder (for debugging)")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("verify", help="decode each row of a star file like the shader")
    p.add_argument("file")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("info", help="show the gains in a Urania astronomical.xsa")
    p.add_argument("file")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("decompile", help="write the stock GLSL of all 9 stages (study only; do not publish)")
    p.add_argument("--xsa", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--tools")
    p.set_defaults(func=cmd_decompile)
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parser().parse_args(argv)
    if not args.command:
        from urania import gui
        return gui.main()
    try:
        return args.func(args)
    except (UraniaError, OSError, zipfile.BadZipFile) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
