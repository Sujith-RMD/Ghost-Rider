"""Config-file tests — task H6.

Owned by the ML role (`docs/ML_ROLE.md` section 1, ``configs/{camera,features,
scoring}/`` are ML-writable).

Task H6 records that ``configs/camera/``, ``configs/features/`` and
``configs/scoring/`` were all empty while the measurement config existed only as
Python dataclasses. These tests do two things:

1. **Lock the ``features`` JSON to the code.** ``configs/features/aggregate.json``
   is round-tripped into the real ``MeasurementConfig`` / ``WatershedConfig``
   dataclasses and compared field-by-field, so the externalised file cannot
   silently drift from the code defaults it mirrors.
2. **Keep the ``scoring`` and ``camera`` configs honest.** Both describe work that
   is *not yet implemented or calibrated*. These tests assert the honesty flags
   stay in place: scoring thresholds are ``null`` (no invented 70/40 bands, task
   F8) and the camera quality policy carries ``thresholds_calibrated = false``
   (task C11). If someone fills in a fabricated number, a test fails.

These are structural checks on configuration files. They establish nothing about
any real camera, score or road.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.aggregate.measurement import MeasurementConfig
from backend.aggregate.segmentation import WatershedConfig
from backend.quality.validity import QualityPolicy

ROOT = Path(__file__).resolve().parents[2]
FEATURES_CFG = ROOT / "configs" / "features" / "aggregate.json"
SCORING_CFG = ROOT / "configs" / "scoring" / "scoring.json"
CAMERA_CFG = ROOT / "configs" / "camera" / "rig_template.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------- features


def test_features_config_exists():
    assert FEATURES_CFG.exists()


def test_features_measurement_matches_code_dataclass():
    cfg = _load(FEATURES_CFG)["measurement"]
    code = MeasurementConfig()
    assert cfg["config_version"] == code.config_version
    assert cfg["min_diameter_px"] == code.min_diameter_px
    assert cfg["min_gap_px"] == code.min_gap_px
    assert cfg["roi_margin_px"] == code.roi_margin_px


def test_features_watershed_matches_code_dataclass():
    cfg = _load(FEATURES_CFG)["watershed"]
    code = WatershedConfig()
    for field in (
        "config_version",
        "polarity",
        "flatten_sigma_fraction",
        "flatten_sigma_min",
        "norm_lo_percentile",
        "norm_hi_percentile",
        "noise_kernel_px",
        "hole_fill_max_area_px",
        "marker_method",
        "marker_h_max_fraction",
        "marker_min_distance_px",
        "min_marker_radius_px",
        "min_instance_area_px",
    ):
        assert cfg[field] == getattr(code, field), f"watershed field {field} drifted"


def test_features_config_rebuilds_a_live_config():
    # The JSON must construct a real MeasurementConfig identical to the default.
    cfg = _load(FEATURES_CFG)
    rebuilt = MeasurementConfig(
        config_version=cfg["measurement"]["config_version"],
        min_diameter_px=cfg["measurement"]["min_diameter_px"],
        min_gap_px=cfg["measurement"]["min_gap_px"],
        roi_margin_px=cfg["measurement"]["roi_margin_px"],
        watershed=WatershedConfig(
            **{k: v for k, v in cfg["watershed"].items() if not k.startswith("_")}
        ),
    )
    assert rebuilt == MeasurementConfig()


def test_texture_config_matches_code_defaults():
    cfg = _load(FEATURES_CFG)["texture"]
    assert cfg["config_version"] == "texture-proxy-v1"
    assert tuple(cfg["distances_mm"]) == (1.0, 2.0, 5.0)
    assert cfg["lbp_radius_mm"] == 3.0



# --------------------------------------------------------------- scoring


def test_scoring_config_exists():
    assert SCORING_CFG.exists()


def test_scoring_is_explicitly_not_implemented():
    cfg = _load(SCORING_CFG)
    assert cfg["implemented"] is False
    assert cfg["calibrated"] is False


def test_scoring_thresholds_are_null_not_invented():
    # Task F8: never copy the 70/40 bands or invent weights. Until thresholds are
    # derived from grouped development tradeoffs they must be null, not a number.
    cfg = _load(SCORING_CFG)
    assert cfg["thresholds"]["good_bad"] is None
    assert cfg["components"]["texture_deviation_T"]["weight"] is None
    assert cfg["components"]["distress_burden_D"]["weight"] is None


def test_scoring_sqi_disabled_until_calibrated():
    # Task F7: SQI = 100*(1 - P_bad) only if probability calibration is supported.
    cfg = _load(SCORING_CFG)
    assert cfg["sqi"]["enabled"] is False


def test_scoring_null_policy_is_null_score():
    # Task F9: missing mandatory evidence yields score = null.
    cfg = _load(SCORING_CFG)
    assert cfg["null_policy"]["missing_mandatory_evidence"] == "score=null"


# ----------------------------------------------------------------- camera


def test_camera_config_exists():
    assert CAMERA_CFG.exists()


def test_camera_quality_policy_matches_code_and_stays_uncalibrated():
    # Task C11: thresholds must not be presented as calibrated until a per-rig
    # calibration exists (blocked on camera access, task C8). The mirror of
    # QualityPolicy must match the code AND keep the calibration flag false.
    cfg = _load(CAMERA_CFG)["quality_policy"]
    code = QualityPolicy()
    assert cfg["policy_version"] == code.policy_version
    assert cfg["min_source_px"] == code.min_source_px
    assert cfg["min_laplacian_variance"] == code.min_laplacian_variance
    assert cfg["min_dynamic_range"] == code.min_dynamic_range
    assert cfg["clip_fraction_reject"] == code.clip_fraction_reject
    assert list(cfg["supported_channels"]) == list(code.supported_channels)
    # The honesty flag stays false and agrees with the code default.
    assert cfg["thresholds_calibrated"] is False
    assert code.thresholds_calibrated is False


def test_camera_rig_fields_are_unset_not_fabricated():
    # No camera exists yet (task C8). The rig identity/calibration fields must be
    # null, not placeholder numbers that could be mistaken for a calibration.
    rig = _load(CAMERA_CFG)["rig"]
    assert rig["device_id"] is None
    assert rig["intrinsics"] is None
    assert rig["distortion"] is None
    assert rig["calibrated_at"] is None
    assert _load(CAMERA_CFG)["scale"]["scale_source"] == "unscaled"
