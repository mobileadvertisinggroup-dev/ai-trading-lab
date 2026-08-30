"""Generate data/manifests/model_manifest_v5.json (D72 §E).

ONE exact, current model manifest at the location the authorization
gate resolves (`data/manifests/`), describing the frozen model set a
Checkpoint-2 authorization would consume after the D72 funding
correction: the retained B/C/E boosters + selections and the RETRAINED
SB3 family — every file pinned by sha256. The stale draft-era
data/models/model_manifest.json (whose arm_f section still describes
the invalidated CEM) remains preserved history and is never named by
an authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--model-dir", required=True,
                    help="retained frozen B/C/E artifacts")
    ap.add_argument("--sb3-dir", required=True,
                    help="RETRAINED (funding-corrected) SB3 artifacts")
    args = ap.parse_args()

    def pin(root, names):
        out = {}
        for n in names:
            p = os.path.join(root, n)
            out[n] = {"sha256": sha256_file(p),
                      "bytes": os.path.getsize(p)}
        return out

    with open(os.path.join(args.model_dir,
                           "bc_train_selection.json")) as f:
        fin = json.load(f)
    with open(os.path.join(args.model_dir,
                           "arm_e_portfolio_selection.json")) as f:
        e_sel = json.load(f)
    with open(os.path.join(args.sb3_dir, "arm_f_sb3_manifest.json")) as f:
        sb3m = json.load(f)
    sel_seed = int(sb3m["selected_seed"])

    manifest = {
        "version": "model-manifest-v5 (D72 funding-corrected)",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
        "retained_supervised": pin(args.model_dir, [
            "arm_b.txt", "arm_c.txt", "arm_e.txt", "arm_e_cuts.npz",
            "bc_train_selection.json"]),
        "arm_e_portfolio_selection": {
            **pin(args.model_dir,
                  ["arm_e_portfolio_selection.json"])
            ["arm_e_portfolio_selection.json"],
            "selected_mapping": e_sel["selected_mapping"],
            "correction": "D72: re-selected with funding applied"},
        "arm_f_sb3": {
            "manifest": pin(args.sb3_dir, ["arm_f_sb3_manifest.json"])
            ["arm_f_sb3_manifest.json"],
            "selected_seed": sel_seed,
            "selected_zip": pin(args.sb3_dir,
                                [f"arm_f_sb3_seed{sel_seed}.zip"])
            [f"arm_f_sb3_seed{sel_seed}.zip"],
            "all_seed_zips": pin(args.sb3_dir,
                                 [f"arm_f_sb3_seed{s}.zip"
                                  for s in range(1, 11)]),
            "correction": "D72: all 10 official seeds RETRAINED with "
                          "funding; selection rule unchanged"},
        "selections": {"arm_b_threshold":
                       fin["arm_b"]["selected_threshold"],
                       "arm_c_top_k": fin["arm_c"]["selected_top_k"],
                       "arm_e_mapping": e_sel["selected_mapping"],
                       "arm_f_seed": sel_seed},
        "superseded_history": {
            "no_funding_sb3_family":
                "/home/user/lake-work/official_v2/models_sb3 (+ git "
                "history of data/models_sb3) — preserved unmodified",
            "no_funding_e_selection":
                "/home/user/lake-work/official_v4/arm_e (+ git history)",
            "draft_model_manifest": "data/models/model_manifest.json "
                                    "(arm_f section = invalidated CEM)"},
    }
    out = os.path.join(args.repo_root, "data", "manifests",
                       "model_manifest_v5.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"wrote {out}\nsha256 {sha256_file(out)}")


if __name__ == "__main__":  # pragma: no cover
    main()
