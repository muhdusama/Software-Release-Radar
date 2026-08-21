from __future__ import annotations

import json
import sys
from pathlib import Path


# These are reviewed, intentional findings. The allowlist is deliberately tied
# to file, test ID and line so new uses of the same API still fail the gate.
# If a line moves, review it again before updating this list.
ALLOWED_FINDINGS: dict[tuple[str, str, int], str] = {
    ("radar/github.py", "B310", 60): "Destination is the fixed https://api.github.com API.",
    ("radar/notifications.py", "B310", 111): "Destination is the fixed https://api.pushover.net API.",
    ("radar/portainer.py", "B323", 54): "TLS verification bypass is an explicit opt-in for self-signed Portainer and defaults to verification enabled.",
    ("radar/portainer.py", "B310", 81): "Portainer base URLs are validated as complete HTTP(S) URLs; local-network access is an intended integration feature.",
    ("radar/inventory_providers.py", "B323", 95): "TLS verification bypass is an explicit opt-in for self-signed Dockhand and defaults to verification enabled.",
    ("radar/inventory_providers.py", "B310", 97): "Dockhand base URLs are validated as complete HTTP(S) URLs; local-network access is an intended integration feature.",
    ("radar/presentation.py", "B704", 80): "All source text is html.escape() encoded before the renderer adds its own fixed markup subset.",
    ("radar/probes.py", "B310", 86): "Probe URLs are constructed only from the validated http/https scheme, validated host, validated port and a path.",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: check_bandit.py BANDIT.json", file=sys.stderr)
        return 2

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    unexpected: list[dict] = []
    reviewed: list[tuple[tuple[str, str, int], str]] = []

    for result in payload.get("results", []):
        severity = str(result.get("issue_severity") or "").upper()
        confidence = str(result.get("issue_confidence") or "").upper()
        if severity not in {"MEDIUM", "HIGH"} or confidence != "HIGH":
            continue

        filename = str(result.get("filename") or "").replace("\\", "/")
        line = int(result.get("line_number") or 0)
        test_id = str(result.get("test_id") or "")
        key = (filename, test_id, line)
        reason = ALLOWED_FINDINGS.get(key)
        if reason is None:
            unexpected.append(result)
        else:
            reviewed.append((key, reason))

    for key, reason in reviewed:
        print(f"REVIEWED: {key[0]}:{key[2]} {key[1]} - {reason}")

    if unexpected:
        print("\nFAIL: unexpected medium/high severity, high-confidence Bandit findings:", file=sys.stderr)
        for result in unexpected:
            print(
                f"- {result.get('filename')}:{result.get('line_number')} "
                f"{result.get('test_id')} {result.get('issue_text')}",
                file=sys.stderr,
            )
        return 1

    print("PASS: no unexpected medium/high severity, high-confidence Bandit findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
