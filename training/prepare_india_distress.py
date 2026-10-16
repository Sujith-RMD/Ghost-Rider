"""Extract and clean the India subset of RDD2022, into a usable distress dataset.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Answers three things the plan asks for (final plan 4.2):

* **India-first distress data.** RDD2022's India subset extracted only - the other
  five countries are left in the archive.
* **Negatives.** Roughly half the Indian images carry no damage annotation. Crack-Seg
  supplies 1 negative in 4,029 and CRKWH100 supplies none, so this is the first real
  source of intact-road images and the only way a false-alarm rate can be measured.
* **A frozen held-out split.** The shipped RDD *test* split is entirely unlabelled
  (verified: 40 of 40 sampled images have empty ``objects``), so it cannot be used
  for evaluation. A train/development split is cut here instead.

What this does **not** give: pixel masks. Every annotation is a bounding rectangle,
so this feeds a *detection* baseline (task E10) and the India claim - it cannot
measure precise defect area, which is why the Crack-Seg segmentation model still
matters.

Usage::

    python -m training.prepare_india_distress \\
        --tar data/external/rdd2022-DatasetNinja.tar \\
        --out data/external/rdd2022_india

    # dry run: parse only, no extraction
    python -m training.prepare_india_distress --tar <path> --out data/external/rdd2022_india --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import tarfile
from collections import Counter
from pathlib import Path

# Only the India-tagged images are wanted.
COUNTRY_PREFIX = "India_"
DEV_FRACTION = 0.2
RANDOM_SEED = 0

CLASS_TITLES = [
    "alligator crack",
    "block crack",
    "longitudinal crack",
    "other corruption",
    "pothole",
    "repair",
    "transverse crack",
]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _class_id_to_title(meta: dict) -> dict[int, str]:
    return {int(c["id"]): str(c["title"]) for c in meta.get("classes", [])}


def parse_annotation(
    data: dict, id_to_title: dict[int, str]
) -> list[dict]:
    """Convert a DatasetNinja annotation into a flat list of box records.

    The ``points`` field carries the two exterior corners of a rectangle in
    ``{"exterior": [[x1, y1], [x2, y2]]}`` form. ``geometryType`` is asserted to be
    ``rectangle`` rather than assumed, because a non-rectangle geometry arriving here
    would silently change what a box means.
    """
    objects = []
    for obj in data.get("objects", []):
        geometry_type = str(obj.get("geometryType", ""))
        if geometry_type != "rectangle":
            raise ValueError(
                f"unexpected geometryType {geometry_type!r}; this parser handles "
                "rectangles only, and accepting other shapes silently would change "
                "the meaning of a box"
            )
        exterior = obj["points"]["exterior"]
        (x1, y1), (x2, y2) = exterior[0], exterior[1]
        x_lo, x_hi = sorted((float(x1), float(x2)))
        y_lo, y_hi = sorted((float(y1), float(y2)))
        if x_hi <= x_lo or y_hi <= y_lo:
            # Degenerate box: zero or negative area. Recorded, not silently kept.
            continue
        class_id = int(obj["classId"])
        objects.append(
            {
                "class_title": id_to_title.get(class_id, obj.get("classTitle", "unknown")),
                "class_id": class_id,
                "x_min": x_lo,
                "y_min": y_lo,
                "x_max": x_hi,
                "y_max": y_hi,
                "area_frac": ((x_hi - x_lo) * (y_hi - y_lo))
                / float(data["size"]["height"] * data["size"]["width"]),
            }
        )
    return objects


def build(tar_path: Path, out_root: Path, dry_run: bool = False) -> dict:
    if not tar_path.is_file():
        raise FileNotFoundError(tar_path)

    with tarfile.open(tar_path, "r") as tf:
        names = tf.getnames()

        # --- read the small metadata files first ---
        meta = json.load(tf.extractfile("meta.json"))
        id_to_title = _class_id_to_title(meta)

        # --- locate the India image/annotation pairs ---
        ann_members = [
            n
            for n in names
            if n.startswith("train/ann/")
            and "/" not in n[len("train/ann/") :]
            and Path(n).name.startswith(COUNTRY_PREFIX)
            and n.endswith(".json")
        ]
        image_members = {
            Path(n).name: n
            for n in names
            if n.startswith("train/img/")
            and "/" not in n[len("train/img/") :]
            and Path(n).name.startswith(COUNTRY_PREFIX)
        }

        # The test split is entirely unlabelled, so it is deliberately skipped.
        test_ann = [
            n
            for n in names
            if n.startswith("test/ann/")
            and Path(n).name.startswith(COUNTRY_PREFIX)
        ]

        records = []
        class_counts: Counter = Counter()
        empty = 0
        sizes: Counter = Counter()
        degenerate_boxes = 0

        for ann_name in sorted(ann_members):
            image_name = Path(ann_name).name[:-5]  # strip .json
            image_member = image_members.get(image_name)
            if image_member is None:
                continue
            data = json.load(tf.extractfile(ann_name))
            sizes[(data["size"]["height"], data["size"]["width"])] += 1
            boxes = parse_annotation(data, id_to_title)
            if not boxes:
                empty += 1
            for box in boxes:
                class_counts[box["class_title"]] += 1
            records.append(
                {
                    "sample_id": image_name[:-4],
                    "image_member": image_member,
                    "height": int(data["size"]["height"]),
                    "width": int(data["size"]["width"]),
                    "boxes": boxes,
                    "is_negative": not boxes,
                    "country_tag": "India",
                }
            )

    total = len(records)
    if total == 0:
        raise ValueError("no India images found; check the archive layout")

    # --- grouped split ---
    # No road/session identifier ships with RDD2022, so a seeded random split is
    # all that is available. This is labelled honestly as random-held-out, not as
    # road-held-out, because those are different claims (final plan 6.2).
    rng = random.Random(RANDOM_SEED)
    order = list(range(total))
    rng.shuffle(order)
    n_dev = max(1, int(round(total * DEV_FRACTION)))
    dev_ids = {records[i]["sample_id"] for i in order[:n_dev]}
    for record in records:
        record["split"] = "dev" if record["sample_id"] in dev_ids else "train"

    train_n = sum(1 for r in records if r["split"] == "train")
    dev_n = total - train_n
    train_neg = sum(1 for r in records if r["split"] == "train" and r["is_negative"])
    dev_neg = sum(1 for r in records if r["split"] == "dev" and r["is_negative"])

    extracted = 0
    if not dry_run:
        img_dir = out_root / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        to_extract = {r["image_member"] for r in records}
        with tarfile.open(tar_path, "r") as tf:
            for member_name in sorted(to_extract):
                target = img_dir / Path(member_name).name
                if target.exists():
                    continue
                try:
                    src = tf.extractfile(member_name)
                    if src is None:
                        continue
                    target.write_bytes(src.read())
                    extracted += 1
                except KeyError:
                    continue
        if extracted:
            # Train images never enter the dev split by construction: each sample
            # is assigned a single split before extraction.
            pass

    manifest = {
        "manifest_version": 1,
        "dataset": "rdd2022_india",
        "source": "RDD2022, the Multi-National Road Damage Dataset 2022",
        "official_source": "https://crddc2022.sekilab.global/rules/",
        "license": "CC BY-SA 4.0",
        "repackaged_by": "DatasetNinja",
        "repackaging_caveat": (
            "This is the DatasetNinja repackaging, not the archive published at "
            "sekilab/RoadDamageDetector. Annotations were converted to DatasetNinja's "
            "JSON box format. Ancestry therefore runs one step through a third party, "
            "which final plan 4.2 requires be recorded."
        ),
        "geometry": "bounding rectangles only, no pixel masks",
        "size_note": (
            "Boxes feed a detection baseline (E10) and the India claim. Precise "
            "defect-area measurement still needs the Crack-Seg segmentation model."
        ),
        "splits_note": (
            "The shipped RDD test split is 100% unlabelled (verified by sampling) and "
            "is deliberately unused. Train/development are cut here from the annotated "
            "train images. No road or session id ships with RDD2022, so this is a "
            "seeded random split, i.e. random-held-out, not verified road-held-out."
        ),
        "n_images": total,
        "n_train": train_n,
        "n_dev": dev_n,
        "n_dev_fraction": DEV_FRACTION,
        "random_seed": RANDOM_SEED,
        "n_negatives": empty,
        "negative_rate": empty / total,
        "negative_significance": (
            "First source of intact-road images in the project. Crack-Seg supplies 1 "
            "negative in 4,029; CRKWH100 supplies 0. Without these, no false-alarm "
            "rate could be measured at all."
        ),
        "n_boxes": int(sum(class_counts.values())),
        "class_counts": dict(class_counts),
        "distinct_boxes_observed": sorted(class_counts),
        "classes_declared_but_unobserved": sorted(set(CLASS_TITLES) - set(class_counts)),
        "image_sizes": [list(k) for k in sizes],
        "skipped_test_images": len(test_ann),
        "dry_run": bool(dry_run),
        "images_extracted": extracted,
        "records": records,
    }

    out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "manifest": str(manifest_path),
        "n_images": total,
        "n_train": train_n,
        "n_dev": dev_n,
        "n_negatives": empty,
        "negative_rate": round(empty / total, 4),
        "n_boxes": int(sum(class_counts.values())),
        "class_counts": dict(class_counts),
        "image_sizes": [list(k) for k in sizes],
        "images_extracted": extracted,
        "dry_run": bool(dry_run),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tar", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    summary = build(Path(args.tar), Path(args.out), args.dry_run)
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
