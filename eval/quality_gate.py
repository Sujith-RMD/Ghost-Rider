"""Run the image-validity gate over a directory and summarise the verdicts.

Owned by the ML role (``docs/ML_ROLE.md`` section 1). The verdict logic and its
tests live in ``backend/quality/validity.py``; this is the thin runner that turns
a directory of images into an auditable count.

Final plan section 7.2 requires reject/suppress decisions to be visible rather
than silent, and section 13.3 requires the rejected set to be *audited*: a
pipeline that rejects difficult frames cannot be scored only on the frames that
survive. So the output reports the accepted count, the rejected count and the
reason-code histogram together, never the accepted count alone.

The report always carries ``thresholds_calibrated``. While that is ``false``
(task C11 is blocked on camera access) these numbers describe a provisional
policy, not a validated one.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import cv2

from backend.quality import QualityPolicy, classify_quality

__all__ = ["run_gate"]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def run_gate(
    root: Path,
    policy: QualityPolicy | None = None,
    has_scale: bool = False,
    max_listed: int = 20,
) -> dict:
    """Classify every image under ``root`` and summarise the verdicts.

    ``has_scale`` defaults to ``False``: none of the sources admitted so far has a
    verified ground sampling distance, so a default of ``True`` would silently
    promote unscaled imagery to metric evidence.
    """
    if max_listed < 0:
        raise ValueError("max_listed must be >= 0")
    root = Path(root)
    policy = policy or QualityPolicy()
    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not paths:
        raise SystemExit(f"no images found under {root}")

    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    rows = []
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        report = classify_quality(image, policy=policy, has_scale=has_scale)
        status_counts[report.status] += 1
        for code in report.reason_codes:
            reason_counts[code] += 1
        rows.append(
            {
                "file": str(path.relative_to(root)),
                "status": report.status,
                "reason_codes": list(report.reason_codes),
                "laplacian_variance": report.metrics.get("laplacian_variance"),
                "dynamic_range": report.metrics.get("dynamic_range"),
                "clipped_high_fraction": report.metrics.get("clipped_high_fraction"),
            }
        )

    return {
        "directory": str(root),
        "policy_version": policy.policy_version,
        "thresholds_calibrated": policy.thresholds_calibrated,
        "has_scale": bool(has_scale),
        "note": (
            ("calibrated policy; " if policy.thresholds_calibrated else
             "provisional policy - thresholds are engineering defaults, not a ")
            + ("" if policy.thresholds_calibrated else
               "validated per-rig rejection policy (final plan section 7.2); ")
            +
            "accepted and rejected counts are reported together on purpose"
        ),
        "images": len(paths),
        "status_counts": dict(status_counts),
        "reason_counts": dict(reason_counts),
        "rejected_or_limited_examples": [
            row for row in rows if row["status"] != "accepted"
        ][: int(max_listed)],
        "per_image": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Image validity gate over a directory")
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--min-source-px", type=int, default=None)
    parser.add_argument(
        "--has-scale",
        action="store_true",
        help="treat the source as scaled (default: no, because no source is yet verified)",
    )
    args = parser.parse_args()

    policy = QualityPolicy()
    if args.min_source_px is not None:
        policy = QualityPolicy(min_source_px=args.min_source_px)

    report = run_gate(args.path, policy=policy, has_scale=args.has_scale)
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
        print(
            f"images {report['images']} | status {report['status_counts']} | "
            f"reasons {report['reason_counts']}"
        )
    else:
        print(text)


if __name__ == "__main__":
    main()
