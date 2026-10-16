import numpy as np
import sqlite3
import torch

from backend import database, schemas
from backend.api.v1 import _get_sample
from backend.queues import ensure_v1_tables
from backend.distress import inference
from backend.worker import _SAMPLE_INSERT, _sample_row_values


def test_missing_checkpoint_is_explicit_and_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setattr(inference, "_weights_path", lambda: tmp_path / "missing.pt")
    result = inference.detect_distress(np.zeros((80, 120, 3), dtype=np.uint8))

    assert result.status == "unavailable"
    assert result.reason == "weights_not_found"
    assert result.image_width == 120
    assert result.image_height == 80
    assert result.detections == []


def test_detection_preserves_class_confidence_and_original_image_box(monkeypatch, tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"verified fixture checkpoint")

    class Boxes:
        xyxy = torch.tensor([[12.5, 15.0, 40.0, 52.5]])
        cls = torch.tensor([2.0])
        conf = torch.tensor([0.875])

    class Prediction:
        boxes = Boxes()

    class Model:
        names = {2: "longitudinal crack"}

        def predict(self, source, **kwargs):
            assert source.shape == (80, 120, 3)
            assert kwargs["device"] == "cpu"
            return [Prediction()]

    monkeypatch.setattr(inference, "_weights_path", lambda: weights)
    monkeypatch.setattr(inference, "_load_model", lambda _path: (Model(), "a" * 64))
    monkeypatch.setattr(inference, "_device", lambda: "cpu")
    result = inference.detect_distress(np.zeros((80, 120, 3), dtype=np.uint8))

    assert result.status == "success"
    assert result.model_sha256
    assert len(result.detections) == 1
    assert result.detections[0].class_id == 2
    assert result.detections[0].class_name == "longitudinal crack"
    assert result.detections[0].confidence == 0.875
    assert result.detections[0].bbox_xyxy == [12.5, 15.0, 40.0, 52.5]


def test_no_detections_are_an_explicit_success(monkeypatch, tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"checkpoint")

    class Prediction:
        boxes = None

    class Model:
        names = {0: "alligator crack"}

        def predict(self, source, **_kwargs):
            assert source.shape == (80, 120, 3)
            return [Prediction()]

    monkeypatch.setattr(inference, "_weights_path", lambda: weights)
    monkeypatch.setattr(inference, "_load_model", lambda _path: (Model(), "b" * 64))
    monkeypatch.setattr(inference, "_device", lambda: "cpu")
    result = inference.detect_distress(np.zeros((80, 120, 3), dtype=np.uint8))

    assert result.status == "success"
    assert result.detections == []


def test_segment_result_accepts_detection_evidence():
    result = schemas.SegmentResult(
        segment_id=1,
        distress_detection={
            "status": "success",
            "image_width": 120,
            "image_height": 80,
            "detections": [],
        },
    )

    assert result.distress_detection.status == "success"
    assert result.score is None


def test_existing_sample_table_gets_additive_detection_column(monkeypatch, tmp_path):
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE samples (sample_id TEXT PRIMARY KEY, segment_id INTEGER NOT NULL)"
        )
    monkeypatch.setattr(database, "get_db_path", lambda: database_path)

    ensure_v1_tables()

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(samples)")}
    assert "detection_json" in columns


def test_detection_evidence_survives_sample_persistence_and_reload(monkeypatch, tmp_path):
    database_path = tmp_path / "samples.db"
    monkeypatch.setattr(database, "get_db_path", lambda: database_path)
    ensure_v1_tables()
    evidence = schemas.DistressDetectionEvidence(
        status="success",
        model_version="rdd2022-india-yolov8n",
        model_sha256="a" * 64,
        image_width=120,
        image_height=80,
        detections=[{
            "class_id": 2,
            "class_name": "longitudinal crack",
            "confidence": 0.875,
            "bbox_xyxy": [12.5, 15, 40, 52.5],
        }],
    )
    result = schemas.SegmentResult(
        segment_id=1,
        created_at="2026-10-16T00:00:00+00:00",
        distress_detection=evidence,
    )
    with database.get_connection() as connection:
        connection.execute(_SAMPLE_INSERT, _sample_row_values("sample-detector", result))

    restored = _get_sample("sample-detector")

    assert restored is not None
    assert restored.distress_detection.detections[0].class_name == "longitudinal crack"
    assert restored.distress_detection.detections[0].bbox_xyxy == [12.5, 15, 40, 52.5]
    assert restored.score is None
