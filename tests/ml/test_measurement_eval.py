"""Arithmetic regression checks; these are not road measurement results."""
from copy import deepcopy

import pytest

from eval.measurement_eval import evaluate_measurements, main


def fixture():
    return {"evidence_type": "synthetic", "metric": "count", "unit": "count", "samples": [
        {"sample_id": "a", "group_id": "site1", "truth": 10, "prediction": 12},
        {"sample_id": "b", "group_id": "site1", "truth": 10, "prediction": 8},
        {"sample_id": "c", "group_id": "site2", "truth": 0, "prediction": 3},
        {"sample_id": "d", "group_id": "site3", "truth": 10, "prediction": None, "null_reason": "quality_rejected"},
    ]}


def test_signed_errors_cannot_hide_absolute_count_errors():
    report = evaluate_measurements(fixture())
    summary = report["summary"]
    assert summary["mae"] == pytest.approx(7 / 3)
    assert summary["bias"] == 1
    assert summary["median_absolute_relative_error"] == .2
    assert summary["n_zero_truth_scored"] == 1
    assert summary["n_relative_scored"] == 2
    assert summary["suppressed_fraction"] == .25
    assert report["suppression_reasons"] == {"quality_rejected": 1}
    assert report["groups"]["site1"]["bias"] == 0
    assert report["groups"]["site1"]["mae"] == 2
    assert report["group_bootstrap"]["intervals"]["mae"]["low"] is None


def test_all_suppressed_has_unknown_errors_not_zero():
    data = fixture()
    for row in data["samples"]:
        row.update(prediction=None, null_reason="unscaled")
    result = evaluate_measurements(data)["summary"]
    assert result["mae"] is None
    assert result["bias"] is None
    assert result["suppressed_fraction"] == 1


def test_cluster_intervals_resample_parents_and_are_reproducible():
    data = fixture()
    data["samples"] = [dict(sample_id=str(i), group_id=str(i // 2), truth=10,
                            prediction=10 + i // 2) for i in range(20)]
    result = evaluate_measurements(data, replicates=100)
    assert result == evaluate_measurements(deepcopy(data), replicates=100)
    interval = result["group_bootstrap"]["intervals"]["mae"]
    assert interval["reason"] is None
    assert interval["supporting_groups"] == 10
    assert interval["low"] <= result["summary"]["mae"] <= interval["high"]


@pytest.mark.parametrize("field,value", [("truth", -1), ("truth", float("nan")),
                                         ("prediction", float("inf")), ("prediction", True),
                                         ("truth", .5), ("group_id", "")])
def test_bad_rows_fail(field, value):
    data = fixture()
    data["samples"][0][field] = value
    with pytest.raises(ValueError):
        evaluate_measurements(data)


@pytest.mark.parametrize("change", ["duplicate", "empty", "no_prediction", "no_reason", "bad_evidence", "bad_unit"])
def test_incomplete_or_misleading_inputs_fail(change):
    data = fixture()
    if change == "duplicate":
        data["samples"][1]["sample_id"] = "a"
    elif change == "empty":
        data["samples"] = []
    elif change == "no_prediction":
        del data["samples"][0]["prediction"]
    elif change == "no_reason":
        del data["samples"][3]["null_reason"]
    elif change == "bad_evidence":
        data["evidence_type"] = "unknown"
    else:
        data.update(metric="gap", unit="count")
    with pytest.raises(ValueError):
        evaluate_measurements(data)


def test_source_agreement_is_distinct_from_physical_live_error():
    data = fixture()
    data.update(metric="gap", unit="px", evidence_type="annotation_source_scale")
    assert evaluate_measurements(data)["evidence_type"] == "annotation_source_scale"
    data["evidence_type"] = "physical_live"
    with pytest.raises(ValueError):
        evaluate_measurements(data)


def test_cli_writes_strict_json(tmp_path):
    import json
    source, out = tmp_path / "input.json", tmp_path / "nested" / "report.json"
    source.write_text(json.dumps(fixture()), encoding="utf-8")
    assert main([str(source), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["evidence_type"] == "synthetic"
