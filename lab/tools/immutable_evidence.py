"""Write immutable-release evidence (delta review correction A).

Called by the ingestion workflow after probing GitHub's AUTHORITATIVE
endpoint GET /repos/{owner}/{repo}/immutable-releases:

  200     -> ENABLED
  404     -> NOT ENABLED (or unavailable to the token)
  other   -> UNVERIFIED — never inferred as enabled

Usage: python -m lab.tools.immutable_evidence STATUS BODY_FILE INTERP OUT
"""
from __future__ import annotations

import json
import os
import sys
import time


def main() -> None:
    status, body_file, interp, out = sys.argv[1:5]
    body = None
    try:
        with open(body_file) as f:
            body = json.load(f)
    except (OSError, json.JSONDecodeError):
        try:
            with open(body_file) as f:
                body = f.read()[:2000] or None
        except OSError:
            body = None
    evidence = {
        "endpoint": "GET /repos/{owner}/{repo}/immutable-releases",
        "http_status": status,
        "response_body": body,
        "utc_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "workflow_commit": os.environ.get("GITHUB_SHA"),
        "interpretation": interp,
    }
    with open(out, "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True)
    print("evidence:", status, "-", interp)


if __name__ == "__main__":
    main()
