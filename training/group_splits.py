"""Metadata-only group splits; never reads images, creates crops, or infers independence.

Run ``python -m training.group_splits INPUT.json OUTPUT.json --seed 42``.
Input: {"samples": [{"sample_id": ..., "source_id": ..., "parent_id": ...}],
"near_duplicate_links": [[sample_id, sample_id]],
"frozen_assignments": {sample_id: "train" | "development" | "test"}}.

Grouping fields below accept nonempty strings (null means unavailable). IDs are
scoped by source_id, which should identify the provenance namespace, not a local
folder. Shared physical identities across sources must be supplied as explicit
links; duplicate cluster names are not assumed globally unique. Links may encode
reviewed adjacent-frame/ancestry relationships as well as near duplicates.
Every sample needs grouping metadata or an explicit link. Filename similarity
and low image correlation are deliberately not evidence of independence.

Optional sample evaluation_role is one of EVALUATION_ROLES and forces test.
Roles cannot differ within a connected component, even across source datasets.
Frozen assignments can also be supplied via sample split fields or a previous
output's assignments map. Percentages are targets, not a class-support guarantee.
The resulting manifest records supplied evidence, not verified road independence
or completion of real-data admission, labeling, or independent acceptance gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SPLITS = ("train", "development", "test")
GROUP_FIELDS = ("parent_id", "site_id", "road_id", "session_id", "sequence_id", "duplicate_group_id")
EVALUATION_ROLES = (
    "foreign_crosssource_test", "aggregate_public_test", "distress_india_test",
    "india_challenge_test", "live_india_acceptance",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def build_manifest(data: dict, seed: int = 42, frozen_assignments: dict | None = None) -> dict:
    """Build canonical connected groups and deterministic group-count allocation.

    ``frozen_assignments`` may be a previous manifest's assignments mapping.
    New evidence joining formerly separate frozen splits is an error, not a
    license to move exposed test samples. All three splits must remain nonempty.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise ValueError("input must contain a samples list")
    samples = {}
    for row in data["samples"]:
        if not isinstance(row, dict):
            raise ValueError("each sample must be an object")
        sid = _text(row.get("sample_id"), "sample_id")
        _text(row.get("source_id"), f"{sid}: source_id")
        if sid in samples:
            raise ValueError(f"duplicate sample_id: {sid}")
        samples[sid] = dict(row)
    parent = {sid: sid for sid in samples}

    def find(sid):
        while parent[sid] != sid:
            parent[sid] = parent[parent[sid]]
            sid = parent[sid]
        return sid

    def union(left, right):
        a, b = sorted((find(left), find(right)))
        parent[b] = a

    evidence = set()
    owners = {}
    for sid, row in sorted(samples.items()):
        for field in GROUP_FIELDS:
            value = row.get(field)
            if value is None:
                continue
            _text(value, f"{sid}: {field}")
            key = (row["source_id"], field, value)
            if key in owners:
                union(sid, owners[key])
            owners[key] = sid
            evidence.add(sid)
    links = data.get("near_duplicate_links", [])
    if not isinstance(links, list):
        raise ValueError("near_duplicate_links must be a list")
    normalized_links = set()
    for link in links:
        if not isinstance(link, (list, tuple)) or len(link) != 2:
            raise ValueError("each near_duplicate link must contain two sample IDs")
        left, right = link
        _text(left, "link sample_id")
        _text(right, "link sample_id")
        if left not in samples or right not in samples:
            raise ValueError(f"unknown sample in near_duplicate link: {link}")
        if left == right:
            raise ValueError("self links are not grouping evidence")
        union(left, right)
        evidence.update((left, right))
        normalized_links.add(tuple(sorted((left, right))))
    missing = sorted(set(samples) - evidence)
    if missing:
        raise ValueError(f"missing grouping evidence: {missing}")

    components = {}
    for sid in sorted(samples):
        components.setdefault(find(sid), []).append(sid)
    groups = []
    for members in components.values():
        groups.append({"group_id": "group_" + _digest(members), "sample_ids": members})
    groups.sort(key=lambda g: g["group_id"])
    n = len(groups)
    if n < 3:
        raise ValueError(f"at least 3 connected groups required; found {n}")

    frozen = {}
    for mapping in (data.get("frozen_assignments", {}), frozen_assignments or {},
                    {sid: row["split"] for sid, row in samples.items() if "split" in row}):
        if not isinstance(mapping, dict):
            raise ValueError("frozen_assignments must be an object")
        for sid, split in mapping.items():
            if sid not in samples:
                raise ValueError(f"unknown frozen sample: {sid}")
            if split not in SPLITS:
                raise ValueError(f"invalid split for {sid}: {split}")
            if sid in frozen and frozen[sid] != split:
                raise ValueError(f"conflicting frozen assignments: {sid}")
            frozen[sid] = split
    counts = dict.fromkeys(SPLITS, 0)
    pending = []
    for group in groups:
        roles = {samples[sid].get("evaluation_role") for sid in group["sample_ids"]}
        roles.discard(None)
        if any(role not in EVALUATION_ROLES for role in roles):
            raise ValueError(f"invalid evaluation role: {roles}")
        if len(roles) > 1:
            raise ValueError("connected group crosses separate evaluation roles")
        fixed = {frozen[sid] for sid in group["sample_ids"] if sid in frozen}
        if roles:
            fixed.add("test")
        if len(fixed) > 1:
            raise ValueError("cross-split group leak: conflicting frozen assignments or evaluation role")
        group["evaluation_role"] = next(iter(roles), None)
        if fixed:
            group["split"] = next(iter(fixed))
            counts[group["split"]] += 1
        else:
            pending.append(group)
    empty = sum(count == 0 for count in counts.values())
    if len(pending) < empty:
        raise ValueError("frozen assignments/evaluation roles prevent nonempty train/development/test")
    # Largest target deficit first; reserve the last free groups for empty splits.
    targets = dict(zip(SPLITS, (n * .6, n * .2, n * .2)))
    pending.sort(key=lambda g: _digest([seed, g["group_id"]]))
    for index, group in enumerate(pending):
        vacant = [split for split in SPLITS if counts[split] == 0]
        choices = vacant if len(pending) - index == len(vacant) else SPLITS
        split = max(choices, key=lambda s: targets[s] - counts[s])
        group["split"] = split
        counts[split] += 1
    assignments = {sid: group["split"] for group in groups for sid in group["sample_ids"]}
    role_manifests = {role: sorted(sid for group in groups if group["evaluation_role"] == role
                                 for sid in group["sample_ids"]) for role in EVALUATION_ROLES}
    result = {
        "schema_version": 1, "seed": seed,
        "grouping_basis": "explicit_metadata_only_not_verified_road_independence",
        "target_group_fractions": dict(zip(SPLITS, (.6, .2, .2))),
        "samples": [samples[sid] for sid in sorted(samples)],
        "near_duplicate_links": [list(link) for link in sorted(normalized_links)],
        "frozen_assignments": dict(sorted(frozen.items())),
        "groups": groups, "assignments": dict(sorted(assignments.items())),
        "evaluation_manifests": role_manifests,
        "stats": {
            "samples": len(samples), "groups": n,
            "splits": {split: {"groups": counts[split],
                               "samples": sum(s == split for s in assignments.values()),
                               "group_fraction": counts[split] / n} for split in SPLITS},
            "evaluation_roles": {role: {"samples": len(ids), "groups": sum(
                g["evaluation_role"] == role for g in groups)} for role, ids in role_manifests.items()},
        },
    }
    result["checksum_sha256"] = _digest(result)
    return result


def write_manifest(manifest: dict, path: Path, overwrite: bool = False) -> None:
    """Persist with exclusive creation by default; checksum covers all other fields."""
    payload = dict(manifest)
    checksum = payload.pop("checksum_sha256", None)
    if checksum != _digest(payload):
        raise ValueError("manifest checksum mismatch")
    with Path(path).open("w" if overwrite else "x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--frozen-manifest", type=Path, help="Preserve assignments from a previous output (checksum checked)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        frozen = None
        if args.frozen_manifest:
            previous = json.loads(args.frozen_manifest.read_text(encoding="utf-8"))
            checksum = previous.pop("checksum_sha256", None)
            if checksum != _digest(previous):
                raise ValueError("frozen manifest checksum mismatch")
            frozen = previous["assignments"]
        data = json.loads(args.input.read_text(encoding="utf-8"))
        manifest = build_manifest(data, args.seed, frozen)
        write_manifest(manifest, args.output, args.overwrite)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(manifest["stats"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
