"""Tests for tiled measurement, canonical records, and the distress path.

Covers the three items closed after the ML modules landed:

1. **Tiled measurement** — real frames are larger than one watershed tile;
   instances straddling tile boundaries must still be counted exactly once
   (verified against the generator's ground-truth count);
2. **Canonical sample record** — every persisted sample that was actually
   measured carries the final-plan §11.5 record (provenance, geometry, feature
   list, honest unknowns);
3. **Distress path** — crack-mask measurements translate into contract fields
   and the canonical feature list; unscaled imagery stays ``None``.
"""

import os

# Deterministic worker behaviour for the API-level test.
os.environ.setdefault("GHOST_RIDER_INLINE_WORKER", "false")

import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import analysis
from backend.api.server import app
from backend.distress.features import distress_metrics
from backend.geometry.scale import PlanarScale, ScaleSource
from backend.schemas import QualityStatus
from backend.worker import process_job_by_id


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _synthetic(seed: int = 0, width: int = 512, height: int = 512, n_particles: int = 60):
    from eval.aggregate_eval import make_synthetic_case

    return make_synthetic_case(seed=seed, width=width, height=height, n_particles=n_particles)


# --------------------------------------------------------------------------- #
# 1. Tiled measurement
# --------------------------------------------------------------------------- #

def test_measure_frame_counts_boundary_spanning_instances_once():
    """A frame larger than one tile: instances straddling tile seams count once."""
    case = _synthetic(seed=1, width=1024, height=768, n_particles=120)
    outcome = analysis.measure_frame(case["image"])

    assert outcome["quality"] is not None
    assert outcome["quality"].status in (QualityStatus.ACCEPTED, QualityStatus.LIMITED)
    metrics = outcome["metrics"]
    assert metrics is not None
    # Ground truth from the generator; tiling must merge straddling fragments
    # rather than double-counting them.
    assert metrics.chip_count == case["n_gt"]
    assert metrics.aggregate_coverage is not None
    # Unscaled: metric units stay null.
    assert metrics.chip_density_per_m2 is None
    assert metrics.gap_median_mm is None


def test_measure_frame_small_frame_unchanged():
    """Frames at/below tile size degenerate to one tile (regression guard)."""
    case = _synthetic(seed=0)
    outcome = analysis.measure_frame(case["image"])
    assert outcome["metrics"].chip_count == case["n_gt"]


# --------------------------------------------------------------------------- #
# 2. Canonical sample record
# --------------------------------------------------------------------------- #

def _upload_real_image(client, name: str, image: np.ndarray) -> str:
    """Allocate + upload a real (decodable) JPEG; return the job id."""
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    slot = client.post(
        "/v1/uploads",
        json={"filename": name, "content_type": "image/jpeg", "expected_size": int(encoded.size)},
    ).json()
    upload_id = slot["upload_id"]
    put = client.put(
        f"/v1/uploads/{upload_id}/local",
        content=encoded.tobytes(),
        headers={"Content-Type": "image/jpeg"},
    )
    assert put.status_code == 200, put.text
    fin = client.post(
        f"/v1/uploads/{upload_id}/finalize",
        json={
            "metadata": {
                "gps": {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 4.0, "simulated": False},
                "captured_at": "2026-10-16T09:15:00+00:00",
                "source_mode": "upload",
            },
            "source_mode": "upload",
        },
    )
    assert fin.status_code == 200, fin.text
    return fin.json()["job_id"]


def test_canonical_record_persisted_for_measured_upload(client):
    case = _synthetic(seed=2, width=512, height=512, n_particles=60)
    job_id = _upload_real_image(client, f"canonical-{uuid.uuid4()}.jpg", case["image"])

    # Run the durable job (inline worker disabled in tests).
    assert process_job_by_id(job_id) is not None

    job = client.get(f"/v1/jobs/{job_id}").json()
    # Partial (not succeeded) is the truthful terminal state while the ML
    # scoring module is undelivered: measurements exist, SQI does not.
    assert job["status"] in ("succeeded", "partial"), job
    assert job["error_reason"] is None
    sample_id = job["result_sample_id"]

    sample = client.get(f"/v1/samples/{sample_id}").json()
    canonical = sample["canonical"]
    assert canonical is not None, "measured samples must carry the canonical record"

    # Provenance: real hash + original URI, same identity as the stored row.
    assert canonical["provenance"]["file_sha256"] and len(canonical["provenance"]["file_sha256"]) == 64
    assert canonical["provenance"]["original_uri"]
    assert canonical["identity"]["sample_id"] == sample_id
    assert canonical["identity"]["session_id"] == job_id

    # Time: capture time preserved from telemetry; received/processed recorded.
    assert canonical["time"]["captured_at_utc"] == "2026-10-16T09:15:00+00:00"
    assert canonical["time"]["received_at"]
    assert canonical["time"]["processed_at"]

    # Camera: real frame dimensions.
    assert canonical["camera"]["width_px"] == 512
    assert canonical["camera"]["height_px"] == 512

    # Geometry: unscaled, no error bound invented.
    assert canonical["geometry"]["scale_source"] == "unscaled"
    assert canonical["geometry"]["sx_sy_or_h"] is None
    assert canonical["geometry"]["error_bound_pct"] is None

    # Feature list: real counts as free-form rows with explicit units.
    feature_names = {f["name"] for f in canonical["features"]}
    assert "chip_count" in feature_names
    chip = next(f for f in canonical["features"] if f["name"] == "chip_count")
    assert chip["value"] == case["n_gt"]
    assert chip["unit"] == "count"

    # Scoring module not delivered: assessment is explicitly unknown.
    assert canonical["assessment"]["value"] is None
    assert canonical["assessment"]["status"] == "unknown"
    assert canonical["coverage"]["coverage_method"] == "conservative_spacing"
    assert canonical["coverage"]["frame_interval_m"] is None


def test_canonical_record_absent_without_measurement(client):
    """Unreadable uploads fail the job truthfully — no sample, no canonical."""
    slot = client.post(
        "/v1/uploads",
        json={"filename": f"blank-{uuid.uuid4()}.jpg", "content_type": "image/jpeg", "expected_size": 68},
    ).json()
    put = client.put(
        f"/v1/uploads/{slot['upload_id']}/local",
        content=b"\xff\xd8\xff\xe0" + b"\x00" * 64,
        headers={"Content-Type": "image/jpeg"},
    )
    assert put.status_code == 200
    fin = client.post(
        f"/v1/uploads/{slot['upload_id']}/finalize",
        json={"metadata": {"source_mode": "upload"}, "source_mode": "upload"},
    )
    job_id = fin.json()["job_id"]
    # The merged worker fails the job when no measurement could be produced
    # (truthful partial results): no sample row, hence no canonical record.
    assert process_job_by_id(job_id) is None
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error_reason"] == "inference_returned_no_result"
    assert job["result_sample_id"] is None


# --------------------------------------------------------------------------- #
# 3. Distress path
# --------------------------------------------------------------------------- #

def _crack_image() -> tuple[np.ndarray, np.ndarray]:
    """Image with a horizontal crack: (image, crack_mask)."""
    image = np.full((256, 256, 3), 127, dtype=np.uint8)
    crack = np.zeros((256, 256), dtype=bool)
    crack[120:124, 20:240] = True  # 4 px tall, 220 px long horizontal crack
    image[120:124, 20:240] = 20
    return image, crack


def test_distress_metrics_wired_unscaled_stays_null():
    image, crack = _crack_image()
    outcome = analysis.measure_frame(image, crack_mask=crack)

    metrics = outcome["metrics"]
    assert metrics is not None
    # Honest unknowns for an unscaled frame — never a fabricated zero length.
    assert metrics.crack_skeleton_length_m is None
    assert metrics.crack_total_area_m2 is None
    # The raw distress record is retained for the canonical feature list.
    assert outcome["distress_record"] is not None
    assert outcome["distress_record"].skeleton_pixels > 0


def test_distress_metrics_scaled_translate_to_real_values():
    """With a real scale the distress record yields metric values, and the
    canonical feature list carries every measured distress row."""
    image, crack = _crack_image()
    scale = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "test-1mm-per-px")
    valid = np.ones(image.shape[:2], dtype=bool)
    record = distress_metrics(crack, scale, valid)

    # ~220 px at 1 mm/px ≈ 0.22 m skeleton length.
    assert record.skeleton_length_m is not None
    assert 0.20 <= record.skeleton_length_m <= 0.24
    assert record.defect_area_m2 is not None and record.defect_area_m2 > 0
    assert record.extent_fraction is not None

    features = analysis._feature_list(metrics=None, distress=record, estimator_version="distress-v1")
    names = {f.name for f in features}
    assert "crack_skeleton_length" in names
    assert "crack_density" in names
    assert "crack_extent" in names
    crack_len = next(f for f in features if f.name == "crack_skeleton_length")
    assert crack_len.unit == "m"
    assert crack_len.value is not None
