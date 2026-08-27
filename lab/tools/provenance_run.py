"""Provenance-gated official job runner (reviewer directive 2026-08-27).

Wraps any `lab.tools.*` entry point and produces an automatic provenance
manifest alongside the job's outputs. The gate REFUSES to run unless the
source checkout is exactly reconstructible, and REFUSES to certify the
run unless nothing consumed changed while it ran:

  pre-flight (hard failures):
    - the checkout is a git worktree with ZERO uncommitted changes
      (`git status --porcelain` empty) at a recorded commit SHA;
    - the output directory lies OUTSIDE the source checkout;
  during: the target module runs in-process (runpy), so every import is
    observable;
  post-run (hard failures, manifest written with certified=false):
    - `git status --porcelain` still empty and HEAD unchanged;
    - every *.py under lab/ plus the requirements file hashes identically
      to its pre-launch snapshot;
    - every loaded lab.* module was imported from THIS checkout (no
      mutable alternate path).

Manifest contents: git SHA + status, platform + hostname, interpreter and
exact dependency versions (torch reported as its full version string,
e.g. 2.13.0+cu130), the exact command line, whitelisted environment
variables, start/end UTC times, the pre/post source-hash census, the
loaded-module census with per-file hashes, sha256 of every file in the
declared input dirs and of every file the job wrote to the output dir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import runpy
import subprocess
import sys
import time

ENV_WHITELIST_PREFIXES = ("PYTHON", "OMP_", "MKL_", "OPENBLAS_",
                          "CUDA_VISIBLE_DEVICES", "TORCH", "LC_", "LANG",
                          "TZ")
DEP_MODULES = ("torch", "stable_baselines3", "gymnasium", "numpy",
               "pandas", "lightgbm", "pyarrow", "sklearn", "age")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(root: str, *args: str) -> str:
    return subprocess.run(["git", "-C", root, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def source_census(root: str) -> dict[str, str]:
    out = {}
    for dirpath, _dirnames, filenames in os.walk(os.path.join(root, "lab")):
        for fn in filenames:
            if fn.endswith(".py"):
                p = os.path.join(dirpath, fn)
                out[os.path.relpath(p, root)] = sha256_file(p)
    req = os.path.join(root, "requirements.txt")
    if os.path.isfile(req):
        out["requirements.txt"] = sha256_file(req)
    return out


def dir_census(path: str) -> dict[str, str]:
    out = {}
    if not os.path.isdir(path):
        return out
    for dirpath, _d, filenames in os.walk(path):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            out[os.path.relpath(p, path)] = sha256_file(p)
    return out


def dep_versions() -> dict[str, str]:
    vers = {"python": sys.version.replace("\n", " ")}
    for m in DEP_MODULES:
        try:
            vers[m] = getattr(__import__(m), "__version__", "?")
        except Exception:                                  # noqa: BLE001
            vers[m] = "not installed"
    return vers


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser(
        description="provenance-gated runner: provenance_run.py "
                    "--module lab.tools.X --out-dir D [--input-dir D ...] "
                    "-- <module args>")
    ap.add_argument("--module", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--input-dir", action="append", default=[])
    ap.add_argument("--manifest-name", default=None)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    module_args = args.rest[1:] if args.rest[:1] == ["--"] else args.rest

    root = os.path.abspath(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # ---- pre-flight gate -------------------------------------------------
    sha = git(root, "rev-parse", "HEAD")
    status = git(root, "status", "--porcelain")
    if status:
        raise SystemExit(f"PROVENANCE GATE: uncommitted changes in {root}:"
                         f"\n{status}")
    if (out_dir + os.sep).startswith(root + os.sep):
        raise SystemExit("PROVENANCE GATE: out-dir must lie OUTSIDE the "
                         "source checkout")
    pre_census = source_census(root)
    inputs = {d: dir_census(d) for d in args.input_dir}

    manifest = {
        "gate": "provenance_run v1 (reviewer directive 2026-08-27)",
        "git": {"root": root, "commit": sha, "status_porcelain_pre": "",
                "describe": git(root, "log", "-1", "--format=%H %ci %s")},
        "host": {"hostname": platform.node(),
                 "platform": platform.platform(),
                 "cpu_count": os.cpu_count()},
        "dependencies": dep_versions(),
        "command": {"module": args.module, "args": module_args,
                    "wrapper_argv": sys.argv},
        "environment": {k: v for k, v in sorted(os.environ.items())
                        if k.startswith(ENV_WHITELIST_PREFIXES)},
        "inputs": {d: {"n_files": len(c),
                       "census_sha256": hashlib.sha256(json.dumps(
                           c, sort_keys=True).encode()).hexdigest(),
                       "files": c}
                   for d, c in inputs.items()},
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # ---- run in-process so imports are observable ------------------------
    old_argv = sys.argv
    sys.argv = [args.module] + module_args
    t0 = time.time()
    error = None
    try:
        runpy.run_module(args.module, run_name="__main__")
    except SystemExit as e:
        if e.code not in (0, None):
            error = f"SystemExit({e.code})"
    except BaseException as e:                             # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    finally:
        sys.argv = old_argv
    manifest["ended_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime())
    manifest["elapsed_seconds"] = round(time.time() - t0, 1)
    manifest["error"] = error

    # ---- post-run certification ------------------------------------------
    problems = []
    status_post = git(root, "status", "--porcelain")
    manifest["git"]["status_porcelain_post"] = status_post
    if status_post:
        problems.append("working tree changed during the run")
    if git(root, "rev-parse", "HEAD") != sha:
        problems.append("HEAD moved during the run")
    post_census = source_census(root)
    changed = sorted(p for p in set(pre_census) | set(post_census)
                     if pre_census.get(p) != post_census.get(p))
    if changed:
        problems.append(f"source files changed during the run: {changed}")
    manifest["source_census"] = {
        "n_files": len(pre_census),
        "census_sha256_pre": hashlib.sha256(json.dumps(
            pre_census, sort_keys=True).encode()).hexdigest(),
        "census_sha256_post": hashlib.sha256(json.dumps(
            post_census, sort_keys=True).encode()).hexdigest(),
        "changed_during_run": changed,
        "files": pre_census,
    }
    loaded, foreign = {}, []
    for name, mod in sorted(sys.modules.items()):
        if not (name == "lab" or name.startswith("lab.")):
            continue
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        f = os.path.abspath(f)
        loaded[name] = {"file": os.path.relpath(f, root)
                        if f.startswith(root + os.sep) else f,
                        "sha256": sha256_file(f) if os.path.isfile(f)
                        else None}
        if not f.startswith(root + os.sep):
            foreign.append(f"{name} <- {f}")
    if foreign:
        problems.append(f"lab modules imported OUTSIDE the checkout: "
                        f"{foreign}")
    manifest["loaded_lab_modules"] = loaded
    if error:
        problems.append(f"job error: {error}")

    outputs = dir_census(out_dir)
    mname = args.manifest_name or \
        f"PROVENANCE_{args.module.rsplit('.', 1)[-1]}.json"
    outputs.pop(mname, None)
    manifest["outputs"] = {"dir": out_dir, "n_files": len(outputs),
                           "files": outputs}
    manifest["certified"] = not problems
    manifest["problems"] = problems

    mpath = os.path.join(out_dir, mname)
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"provenance manifest: {mpath}")
    print(f"CERTIFIED={manifest['certified']}"
          + (f" problems={problems}" if problems else ""))
    if problems:
        raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover
    main()
