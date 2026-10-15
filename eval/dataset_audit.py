"""Dataset admission audit (final plan section 6.1).

Owned by the ML role (``docs/ML_ROLE.md`` section 1). Reusable across every
candidate source, so it is a kept tool rather than a throwaway script.

What it checks, and why each check exists:

1. **Inventory** - file counts per split, extensions and bytes. Catches an
   archive whose shipped counts disagree with its own YAML/docs.
2. **Decode** - opens *every* image. A viewer failure is not proof of corrupt
   bytes; this reports real decode results per file (final plan section 4.4).
3. **Label integrity** - parses YOLO polygons, validates coordinates, class ids
   and point counts, and reports empty label files as possible valid negatives
   rather than deleting them (section 6.1 item 3).
4. **Pairing** - every image has a label and vice versa.
5. **Label geometry class** - estimates mean polygon stroke width from
   ``2 * area / perimeter``. This is the section 4.3 requirement to distinguish
   real-width masks from centerline labels: a centerline collapses to ~1 px.
6. **Parent lineage** - groups files by their pre-``.rf.`` source id, the
   Roboflow export convention. A single parent appearing in two splits is
   leakage regardless of file hashes (section 6.2).
7. **Duplicate ancestry** - exact sha256 duplicates plus cross-split perceptual
   near-duplicates (dHash, Hamming distance). Similarity thresholds are
   detectors, not guarantees (section 6.1 item 4).

It does **not** decide admission. It produces evidence for a human decision,
because "verified download" is not a completed byte-level audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
SPLIT_NAMES = ("train", "val", "valid", "test")
ROBOFLOW_PREFIX = re.compile(r"^(?P<parent>.+?)\.rf\.[0-9a-f]{8,}$")


# --------------------------------------------------------------------- helpers


def _iter_images(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def _split_of(path: Path, root: Path, splits_by_dir: dict[str, str] | None = None) -> str:
    """Best-effort split label from the path, or ``"unknown"``.

    Never guesses: an image that cannot be placed in a split is reported as
    ``unknown`` so it cannot silently inflate a held-out set.
    """
    parts = [part.lower() for part in path.relative_to(root).parts[:-1]]
    if splits_by_dir:
        for part in parts:
            if part in splits_by_dir:
                return splits_by_dir[part]
    for part in parts:
        for split in SPLIT_NAMES:
            if part == split or part.startswith(split + "_"):
                return "val" if split == "valid" else split
    return "unknown"


def _find_label(image: Path) -> Path | None:
    """Locate the YOLO label for an image by convention (images/ <-> labels/)."""
    parts = list(image.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index].lower() == "images":
            parts[index] = "labels"
            candidate = Path(*parts).with_suffix(".txt")
            if candidate.is_file():
                return candidate
            break
    sibling = image.with_suffix(".txt")
    return sibling if sibling.is_file() else None


def parse_yolo_segment_label(path: Path) -> dict:
    """Parse a YOLO instance-segmentation label file.

    Returns counts plus validation problems. Empty files have no polygons or validation problems: they are possible
    valid negatives, not errors.
    """
    polygons = 0
    points_total = 0
    out_of_range = 0
    too_few_points = 0
    unparsable_lines = 0
    classes: Counter[int] = Counter()
    coordinates: list[np.ndarray] = []

    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        try:
            values = [float(token) for token in tokens]
        except ValueError:
            unparsable_lines += 1
            continue
        if not all(np.isfinite(value) for value in values):
            unparsable_lines += 1
            continue
        if values[0] < 0 or not values[0].is_integer():
            unparsable_lines += 1
            continue
        class_id = int(values[0])
        coords = values[1:]
        if len(coords) < 6 or len(coords) % 2 != 0:
            too_few_points += 1
            continue
        array = np.asarray(coords, dtype=np.float64).reshape(-1, 2)
        classes[class_id] += 1
        polygons += 1
        points_total += len(array)
        if np.any(array < -1e-6) or np.any(array > 1.0 + 1e-6):
            out_of_range += 1
        coordinates.append(array)

    return {
        "polygons": polygons,
        "points_total": points_total,
        "unparsable_lines": unparsable_lines,
        "too_few_points": too_few_points,
        "out_of_range_polygons": out_of_range,
        "classes": {str(k): v for k, v in sorted(classes.items())},
        "coordinates": coordinates,
    }


def polygon_stroke_width_px(polygons: list[np.ndarray], width: int, height: int) -> list[float]:
    """Mean stroke width of each polygon, estimated as ``2 * area / perimeter``.

    A filled outline of a real crack returns its true width. A centerline label
    degenerates to about one pixel.
    """
    widths: list[float] = []
    for normalised in polygons:
        coords = np.column_stack(
            (
                np.clip(normalised[:, 0] * width, 0, width - 1),
                np.clip(normalised[:, 1] * height, 0, height - 1),
            )
        ).astype(np.float32)
        if len(coords) < 3:
            continue
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [np.round(coords).astype(np.int32)], 1)
        area = float(mask.sum())
        perimeter = float(cv2.arcLength(coords.reshape(-1, 1, 2), True))
        if area > 0 and perimeter > 0:
            widths.append(2.0 * area / perimeter)
    return widths


def dhash(image: np.ndarray, size: int = 8) -> np.uint64:
    """Difference hash of a grayscale image as a 64-bit value."""
    small = cv2.resize(image, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    value = np.uint64(0)
    for bit in bits.flatten():
        value = np.uint64((int(value) << 1) | int(bit))
    return value


def confirm_pairs(
    root: Path,
    paths: list[str],
    pairs: list[tuple[int, int, int]],
    work_size: int = 64,
    confirmed_at: float = 0.98,
    probable_at: float = 0.95,
) -> list[dict]:
    """Second-stage confirmation of dHash candidates by pixel correlation.

    A 64-bit dHash is a coarse detector, so a Hamming hit is only a *candidate*.
    Each candidate is downscaled to ``work_size`` grayscale, mean-centred and
    correlated. Without this stage a loose threshold produces false leakage
    alarms, which are as damaging as missing real ones.
    """
    results: list[dict] = []
    for index_a, index_b, distance in pairs:
        image_a = cv2.imread(str(root / paths[index_a]), cv2.IMREAD_GRAYSCALE)
        image_b = cv2.imread(str(root / paths[index_b]), cv2.IMREAD_GRAYSCALE)
        if image_a is None or image_b is None:
            continue
        vector_a = cv2.resize(
            image_a, (work_size, work_size), interpolation=cv2.INTER_AREA
        ).astype(np.float64).ravel()
        vector_b = cv2.resize(
            image_b, (work_size, work_size), interpolation=cv2.INTER_AREA
        ).astype(np.float64).ravel()
        vector_a -= vector_a.mean()
        vector_b -= vector_b.mean()
        denominator = float(np.linalg.norm(vector_a) * np.linalg.norm(vector_b))
        correlation = float(vector_a @ vector_b / denominator) if denominator > 0 else 0.0
        verdict = (
            "confirmed"
            if correlation >= confirmed_at
            else ("probable" if correlation >= probable_at else "rejected")
        )
        results.append(
            {
                "a": paths[index_a],
                "b": paths[index_b],
                "hamming": distance,
                "correlation": round(correlation, 4),
                "verdict": verdict,
            }
        )
    return results


def find_near_duplicate_pairs(
    hashes: np.ndarray, splits: list[str], max_distance: int, chunk: int = 256
) -> list[tuple[int, int, int]]:
    """Cross-split pairs of dHashes within ``max_distance`` Hamming distance."""
    pairs: list[tuple[int, int, int]] = []
    count = len(hashes)
    for start in range(0, count, chunk):
        stop = min(start + chunk, count)
        xor = hashes[start:stop, None] ^ hashes[None, :]
        # NumPy 1.x is supported by the project and has no bitwise_count.
        distances = np.unpackbits(
            xor.view(np.uint8).reshape(stop - start, count, 8), axis=2
        ).sum(axis=2)
        for local_row in range(stop - start):
            row = start + local_row
            columns = np.nonzero(distances[local_row] <= max_distance)[0]
            for column in columns:
                if row >= int(column):
                    continue
                if splits[row] != splits[int(column)]:
                    pairs.append((row, int(column), int(distances[local_row][column])))
    return pairs


# ------------------------------------------------------------------------ main


def audit(root: Path, name: str, roi_dir: str | None = None, max_hamming: int = 6) -> dict:
    images = _iter_images(root)
    if not images:
        raise SystemExit(f"no images found under {root}")

    split_counts: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    total_bytes = 0
    decode_failures: list[str] = []
    resolutions: Counter[str] = Counter()
    channels: Counter[int] = Counter()

    label_missing: list[str] = []
    orphan_labels: list[str] = []
    empty_labels = 0
    total_polygons = 0
    total_points = 0
    class_counts: Counter[str] = Counter()
    label_problems: Counter[str] = Counter()
    stroke_widths: list[float] = []
    widths_sampled = 0

    splits: list[str] = []
    hashes: list[int] = []
    sha_by_path: dict[str, str] = {}
    parents_by_split: dict[str, set[str]] = defaultdict(set)
    paths: list[str] = []

    matched_labels: set[Path] = set()
    decoded_indices: list[int] = []

    for index, image_path in enumerate(images):
        split = _split_of(image_path, root)
        splits.append(split)
        split_counts[split] += 1
        extension_counts[image_path.suffix.lower()] += 1
        size = image_path.stat().st_size
        total_bytes += size
        paths.append(str(image_path.relative_to(root)))

        sha_by_path[paths[-1]] = hashlib.sha256(image_path.read_bytes()).hexdigest()

        match = ROBOFLOW_PREFIX.match(image_path.stem)
        if match:
            parents_by_split[split].add(match.group("parent"))

        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            decode_failures.append(paths[-1])
        else:
            decoded_indices.append(index)
            if image.ndim == 2:
                channels[1] += 1
            else:
                channels[image.shape[2]] += 1
            resolutions[f"{image.shape[1]}x{image.shape[0]}"] += 1
            gray = image if image.ndim == 2 else cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
            hashes.append(int(dhash(gray)))

        label_path = _find_label(image_path)
        if label_path is None:
            label_missing.append(paths[-1])
            continue
        matched_labels.add(label_path)
        parsed = parse_yolo_segment_label(label_path)
        if (parsed["polygons"] == 0 and parsed["unparsable_lines"] == 0
                and parsed["too_few_points"] == 0):
            empty_labels += 1
        total_polygons += parsed["polygons"]
        total_points += parsed["points_total"]
        for key, value in parsed["classes"].items():
            class_counts[key] += value
        label_problems["unparsable_lines"] += parsed["unparsable_lines"]
        label_problems["too_few_points"] += parsed["too_few_points"]
        label_problems["out_of_range_polygons"] += parsed["out_of_range_polygons"]

        # Stroke width is estimated on a bounded sample to keep the audit fast.
        if image is not None and parsed["coordinates"] and widths_sampled < 400:
            widths_sampled += 1
            stroke_widths.extend(
                polygon_stroke_width_px(parsed["coordinates"], image.shape[1], image.shape[0])
            )

    for label_path in sorted(root.rglob("*.txt")):
        if (label_path.is_file()
                and "labels" in [part.lower() for part in label_path.relative_to(root).parts[:-1]]
                and label_path not in matched_labels):
            orphan_labels.append(str(label_path.relative_to(root)))

    duplicated_parents = {}
    all_parents = set().union(*parents_by_split.values()) if parents_by_split else set()
    for parent in sorted(all_parents):
        owning = [split for split, values in parents_by_split.items() if parent in values]
        if len(owning) > 1:
            duplicated_parents[parent] = owning

    hash_array = np.asarray(hashes, dtype=np.uint64)
    valid_pairs = find_near_duplicate_pairs(
        hash_array, [splits[i] for i in decoded_indices], max_hamming
    )
    near_pairs = [(decoded_indices[a], decoded_indices[b], distance)
                  for a, b, distance in valid_pairs]
    confirmed = confirm_pairs(root, paths, near_pairs)
    verdict_counts = Counter(entry["verdict"] for entry in confirmed)
    exact_pairs: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for relative, digest in sha_by_path.items():
        if digest in seen:
            exact_pairs.append((seen[digest], relative))
        else:
            seen[digest] = relative

    report = {
        "dataset": name,
        "root": str(root),
        "image_count": len(images),
        "split_counts": dict(sorted(split_counts.items())),
        "extension_counts": dict(sorted(extension_counts.items())),
        "total_bytes": total_bytes,
        "total_mib": round(total_bytes / (1024 * 1024), 2),
        "decode": {
            "decoded_ok": len(images) - len(decode_failures),
            "failures": len(decode_failures),
            "failure_examples": decode_failures[:20],
            "channel_counts": {str(k): v for k, v in sorted(channels.items())},
            "resolutions": dict(resolutions.most_common(15)),
            "distinct_resolutions": len(resolutions),
        },
        "labels": {
            "images_without_label": len(label_missing),
            "images_without_label_examples": label_missing[:20],
            "orphan_label_files": len(orphan_labels),
            "orphan_label_examples": orphan_labels[:20],
            "empty_label_files": empty_labels,
            "total_polygons": total_polygons,
            "total_polygon_points": total_points,
            "mean_points_per_polygon": round(total_points / total_polygons, 2) if total_polygons else None,
            "class_counts": dict(sorted(class_counts.items())),
            "problems": {k: v for k, v in sorted(label_problems.items()) if v},
        },
        "label_geometry": {
            "stroke_width_sampled_images": widths_sampled,
            "median_stroke_width_px": round(float(np.median(stroke_widths)), 3) if stroke_widths else None,
            "p10_stroke_width_px": round(float(np.percentile(stroke_widths, 10)), 3) if stroke_widths else None,
            "p90_stroke_width_px": round(float(np.percentile(stroke_widths, 90)), 3) if stroke_widths else None,
            "interpretation": (
                "median >= ~2 px is consistent with real-width outlines; "
                "near 1 px indicates centerline-only labels"
            ),
        },
        "leakage": {
            "roboflow_parent_prefixes": len(all_parents),
            "parents_spanning_multiple_splits": len(duplicated_parents),
            "parent_examples": dict(list(duplicated_parents.items())[:20]),
            "exact_duplicate_pairs": len(exact_pairs),
            "exact_duplicate_examples": exact_pairs[:10],
            "cross_split_near_duplicate_candidates": len(near_pairs),
            "near_duplicate_max_hamming": max_hamming,
            "candidate_verdicts": dict(sorted(verdict_counts.items())),
            "confirmed_pairs": [e for e in confirmed if e["verdict"] == "confirmed"],
            "probable_pairs": [e for e in confirmed if e["verdict"] == "probable"],
            "rejected_candidates": [e for e in confirmed if e["verdict"] == "rejected"],
        },
    }
    if roi_dir:
        report["roi_filter"] = roi_dir
    return report


def select_annotation_patches(
    n_images: int,
    count: int = 10,
    crop_px: int = 256,
    image_size: tuple[int, int] = (512, 512),
    seed: int = 0,
) -> list[dict]:
    """Deterministic patch locations for the double-annotation review.

    Final plan section 5.1 step 4 asks for 10 patches annotated twice without
    model suggestions. Two annotators can only produce a disagreement floor if
    they label the *same* patches, so locations are a pure function of the seed
    rather than a fresh random draw each run. Patches are spread across distinct
    source images, because several crops from one image are not independent
    evidence (section 6.2).
    """
    height, width = int(image_size[0]), int(image_size[1])
    count = int(count)
    n_images = int(n_images)
    crop_px = int(crop_px)
    if count < 1:
        raise ValueError("count must be >= 1")
    if n_images < count:
        raise ValueError(f"need at least {count} images, got {n_images}")
    if crop_px < 1 or crop_px > min(height, width):
        raise ValueError(
            f"crop_px must be in [1, {min(height, width)}], got {crop_px}"
        )

    indices = np.unique(np.linspace(0, n_images - 1, count).astype(int))
    rng = np.random.default_rng(int(seed))
    max_top = height - crop_px
    max_left = width - crop_px
    patches = []
    for position, image_index in enumerate(indices.tolist()):
        patches.append(
            {
                "patch_id": f"P{position + 1:02d}",
                "image_index": int(image_index),
                "top": int(rng.integers(0, max_top + 1)) if max_top > 0 else 0,
                "left": int(rng.integers(0, max_left + 1)) if max_left > 0 else 0,
                "crop_px": crop_px,
            }
        )
    return patches


def write_annotation_patches(
    root: Path,
    out_path: Path,
    count: int = 10,
    crop_px: int = 256,
    columns: int = 2,
    seed: int = 0,
    caption: str | None = None,
) -> dict:
    """Write the numbered patch sheet the two human annotators label.

    Tiles are native-resolution crops, **never resized and never overlaid with a
    model prediction**: final plan section 6.3 requires the unaided pilot to come
    before any model proposal, so this artifact deliberately shows raw pixels
    only. Each tile is labelled with its patch id and source filename, and the
    corresponding coordinates are written to the CSV template so a count can be
    traced back to the exact pixels it came from.
    """
    images = _iter_images(root)
    if not images:
        raise SystemExit(f"no images found under {root}")
    first = cv2.imread(str(images[0]), cv2.IMREAD_COLOR)
    if first is None:
        raise SystemExit(f"could not read {images[0]}")
    image_size = (int(first.shape[0]), int(first.shape[1]))

    patches = select_annotation_patches(
        n_images=len(images), count=count, crop_px=crop_px,
        image_size=image_size, seed=seed,
    )

    tiles: list[np.ndarray] = []
    resolved: list[dict] = []
    for patch in patches:
        path = images[patch["image_index"]]
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise SystemExit(f"could not read {path}")
        top, left, side = patch["top"], patch["left"], patch["crop_px"]
        if top + side > image.shape[0] or left + side > image.shape[1]:
            raise ValueError(f"selected patch exceeds image bounds: {path}")
        tile = image[top : top + side, left : left + side].copy()
        cv2.putText(
            tile, f"{patch['patch_id']}  {path.name[:16]}", (6, 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
        )
        cv2.putText(
            tile, f"native {side}px  y{top} x{left}", (6, side - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA,
        )
        tiles.append(tile)
        resolved.append({**patch, "source_image": str(path.relative_to(root))})

    if not tiles:
        raise SystemExit("no tiles could be built")

    columns = max(1, min(int(columns), len(tiles)))
    rows = int(np.ceil(len(tiles) / columns))
    header = 26 if caption else 0
    sheet = np.full(
        (header + rows * crop_px, columns * crop_px, 3), 32, dtype=np.uint8
    )
    for position, tile in enumerate(tiles):
        row, column = divmod(position, columns)
        top = header + row * crop_px
        left = column * crop_px
        sheet[top : top + tile.shape[0], left : left + tile.shape[1]] = tile

    if caption:
        strip = np.full((26, sheet.shape[1], 3), 0, dtype=np.uint8)
        cv2.putText(
            strip, caption[:170], (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (255, 255, 255), 1, cv2.LINE_AA,
        )
        sheet[:26] = strip

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out_path), sheet):
        raise SystemExit(f"failed to write annotation patches to {out_path}")
    return {
        # ``out_path`` matches write_contact_sheet: the same file previously used
        # two different keys for the same thing, which broke a caller that assumed
        # one of them.
        "out_path": str(out_path),
        "sheet_shape_hwc": [int(sheet.shape[0]), int(sheet.shape[1]), int(sheet.shape[2])],
        "tiles": len(tiles),
        "crop_px": int(crop_px),
        "resized": False,
        "model_overlay": False,
        "patches": resolved,
        "caption": caption,
    }


def write_contact_sheet(
    root: Path,
    out_path: Path,
    count: int = 20,
    columns: int = 5,
    tile_px: int = 256,
    scale_mm_per_px: float | None = None,
    caption: str | None = None,
) -> dict:
    """Write a native-resolution contact sheet for the Gate 0 human review.

    Final plan section 5.1 requires a contact sheet, and section 5.1 step 2
    requires that two people judge chip/gap visibility **at native resolution**.
    So tiles are centre-crops of the original pixels, never resized: a resized
    sheet would hide exactly the detail the review is about.

    Images are sampled evenly across the sorted file list rather than taken from
    the front, so the sheet is not biased to one end of the set.
    """
    if int(columns) < 1 or int(tile_px) < 1:
        raise ValueError("columns and tile_px must be >= 1")
    images = _iter_images(root)
    if not images:
        raise SystemExit(f"no images found under {root}")
    count = max(1, min(int(count), len(images)))
    indices = np.unique(np.linspace(0, len(images) - 1, count).astype(int))

    tiles: list[np.ndarray] = []
    sampled_files: list[str] = []
    for index in indices:
        path = images[int(index)]
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            continue
        height, width = image.shape[:2]
        side = min(int(tile_px), height, width)
        top = (height - side) // 2
        left = (width - side) // 2
        tile = image[top : top + side, left : left + side].copy()
        if tile.shape[0] != tile_px or tile.shape[1] != tile_px:
            tile = cv2.copyMakeBorder(
                tile, 0, tile_px - tile.shape[0], 0, tile_px - tile.shape[1],
                cv2.BORDER_CONSTANT, value=(32, 32, 32),
            )
        cv2.putText(
            tile, path.stem[:18], (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (0, 255, 0), 1, cv2.LINE_AA,
        )
        if scale_mm_per_px and scale_mm_per_px > 0:
            # The bar is labelled in PIXELS ONLY. Labelling it in millimetres would
            # assert a physical scale on a review artifact, which is exactly the
            # claim Gate 0 has not yet verified. Any such claim belongs in the
            # caption, where it can be marked unverified.
            bar_px = int(round(10.0 / float(scale_mm_per_px)))
            if 1 <= bar_px <= tile.shape[1] - 12:
                y = tile.shape[0] - 12
                cv2.line(tile, (6, y), (6 + bar_px, y), (0, 255, 255), 2)
                cv2.putText(
                    tile, f"{bar_px} px", (6, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA,
                )
        tiles.append(tile)
        sampled_files.append(str(path.relative_to(root)))

    if not tiles:
        raise SystemExit("no tiles could be built")
    rows: list[np.ndarray] = []
    for start in range(0, len(tiles), int(columns)):
        row_tiles = tiles[start : start + int(columns)]
        while len(row_tiles) < int(columns):
            row_tiles.append(np.zeros_like(tiles[0]))
        rows.append(np.hstack(row_tiles))
    sheet = np.vstack(rows) if rows else np.zeros((tile_px, tile_px, 3), dtype=np.uint8)

    if caption:
        strip = np.full((30, sheet.shape[1], 3), 24, dtype=np.uint8)
        cv2.putText(
            strip, caption[:150], (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (255, 255, 255), 1, cv2.LINE_AA,
        )
        sheet = np.vstack([strip, sheet])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out_path), sheet):
        raise SystemExit(f"failed to write contact sheet to {out_path}")
    return {
        "out_path": str(out_path),
        "tiles": len(tiles),
        "tile_px": int(tile_px),
        "columns": int(columns),
        # Explicitly (height, width) so it matches write_annotation_patches; the
        # same file previously reported this one as (width, height), and two
        # orders for one key is how a downstream consumer silently transposes an
        # image.
        "sheet_shape_hwc": [int(sheet.shape[0]), int(sheet.shape[1]), int(sheet.shape[2])],
        "claimed_mm_per_px": scale_mm_per_px,
        "scale_verified": False,
        "scale_note": "The bar is drawn in pixels only; mm_per_px is the publisher's claim and is NOT verified for these files.",
        "caption": caption,
        "tiles_are_native_crops_not_resized": True,
        "sampled_files": sampled_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Dataset admission audit (final plan 6.1)")
    parser.add_argument("--path", required=True, type=Path, help="dataset root directory")
    parser.add_argument("--name", required=True, help="dataset/version identifier")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--max-hamming", type=int, default=6, help="near-duplicate threshold")
    parser.add_argument("--contact-sheet", type=Path, default=None, help="write a native-resolution contact sheet PNG")
    parser.add_argument("--contact-count", type=int, default=20, help="tiles in the contact sheet")
    parser.add_argument("--contact-columns", type=int, default=5, help="contact sheet columns")
    parser.add_argument("--contact-tile", type=int, default=256, help="native-crop tile size in pixels")
    parser.add_argument("--scale-mm-per-px", type=float, default=None, help="draw a 10 mm-equivalent scale bar, labelled in pixels only")
    parser.add_argument("--caption", default=None, help="caption strip drawn above the contact sheet grid")
    parser.add_argument(
        "--annotation-patches", type=Path, default=None,
        help="write the numbered unaided-review patch sheet PNG",
    )
    parser.add_argument("--patch-count", type=int, default=10, help="patches on the review sheet")
    parser.add_argument("--patch-crop", type=int, default=256, help="native crop size in pixels")
    parser.add_argument("--patch-seed", type=int, default=0, help="patch placement seed")
    parser.add_argument("--skip-audit", action="store_true", help="only write the contact sheet")
    args = parser.parse_args()

    if not args.skip_audit:
        report = audit(args.path, args.name, max_hamming=args.max_hamming)
        if args.contact_sheet:
            report["contact_sheet"] = write_contact_sheet(
                args.path, args.contact_sheet, count=args.contact_count,
                columns=args.contact_columns, tile_px=args.contact_tile,
                scale_mm_per_px=args.scale_mm_per_px, caption=args.caption,
            )
        if args.annotation_patches:
            report["annotation_patches"] = write_annotation_patches(
                args.path, args.annotation_patches, count=args.patch_count,
                crop_px=args.patch_crop, seed=args.patch_seed, caption=args.caption,
            )
        text = json.dumps(report, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
    elif args.contact_sheet or args.annotation_patches:
        meta: dict = {}
        if args.contact_sheet:
            meta["contact_sheet"] = write_contact_sheet(
                args.path, args.contact_sheet, count=args.contact_count,
                columns=args.contact_columns, tile_px=args.contact_tile,
                scale_mm_per_px=args.scale_mm_per_px, caption=args.caption,
            )
        if args.annotation_patches:
            meta["annotation_patches"] = write_annotation_patches(
                args.path, args.annotation_patches, count=args.patch_count,
                crop_px=args.patch_crop, seed=args.patch_seed, caption=args.caption,
            )
        print(json.dumps(meta, indent=2))
    else:
        parser.error("--skip-audit requires --contact-sheet or --annotation-patches")


if __name__ == "__main__":
    main()
