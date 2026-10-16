"""Synthetic metadata only: no real dataset admission or freeze claims."""

import copy
import json

import pytest

from training.group_splits import EVALUATION_ROLES, build_manifest, main, write_manifest


def dataset(n=10):
    return {"samples": [{"sample_id": f"s{i}", "source_id": "synthetic",
                         "parent_id": f"p{i}"} for i in range(n)]}


@pytest.mark.parametrize("field", ["parent_id", "site_id", "road_id", "session_id", "sequence_id", "duplicate_group_id"])
def test_metadata_edges(field):
    data = dataset()
    data["samples"][0][field] = "shared"
    data["samples"][1][field] = "shared"
    result = build_manifest(data)
    assert any(g["sample_ids"] == ["s0", "s1"] for g in result["groups"])


def test_transitive_cross_source_links_and_scoped_ids():
    data = dataset()
    data["samples"][1].update(source_id="other", parent_id="p0")
    assert build_manifest(data)["stats"]["groups"] == 10
    data["samples"][2]["site_id"] = "shared"
    data["samples"][3]["site_id"] = "shared"
    data["near_duplicate_links"] = [["s0", "s1"], ["s1", "s2"]]
    result = build_manifest(data)
    assert any(g["sample_ids"] == ["s0", "s1", "s2", "s3"] for g in result["groups"])


def test_deterministic_order_independent_group_allocation():
    data = dataset()
    result = build_manifest(data, seed=17)
    data["samples"].reverse()
    assert build_manifest(data, seed=17) == result
    assert [result["stats"]["splits"][s]["groups"] for s in ("train", "development", "test")] == [6, 2, 2]
    assert build_manifest(data, seed=18)["assignments"] != result["assignments"]
    # Group counts, not sample counts: adding siblings cannot move allocations.
    data["samples"].extend({"sample_id": f"child{i}", "source_id": "synthetic", "parent_id": "p0"} for i in range(20))
    assert build_manifest(data)["stats"]["groups"] == 10


@pytest.mark.parametrize("n", range(3, 16))
def test_small_counts_have_all_splits(n):
    assert set(build_manifest(dataset(n))["assignments"].values()) == {"train", "development", "test"}


@pytest.mark.parametrize("n", [0, 1, 2])
def test_too_few_groups(n):
    with pytest.raises(ValueError, match="at least 3"):
        build_manifest(dataset(n))


def test_duplicate_ids_missing_evidence_and_invalid_links():
    data = dataset()
    data["samples"].append(dict(data["samples"][0]))
    with pytest.raises(ValueError, match="duplicate sample_id"):
        build_manifest(data)
    data = dataset()
    del data["samples"][0]["parent_id"]
    data["samples"][0]["filename"] = "independent.jpg"
    data["samples"][0]["correlation"] = 0.001
    with pytest.raises(ValueError, match="missing grouping evidence"):
        build_manifest(data)
    data["near_duplicate_links"] = [["s0", "s1"]]
    assert build_manifest(data)["stats"]["groups"] == 9
    for links in ([["s0", "absent"]], [["s0", "s0"]], [["s0"]]):
        data["near_duplicate_links"] = links
        with pytest.raises(ValueError):
            build_manifest(data)


def test_frozen_preserved_and_leak_rejected():
    data = dataset()
    original = build_manifest(data)
    frozen = original["assignments"]
    assert build_manifest(data, 999, frozen)["assignments"] == frozen
    left = next(s for s, split in frozen.items() if split == "train")
    right = next(s for s, split in frozen.items() if split == "test")
    data["near_duplicate_links"] = [[left, right]]
    with pytest.raises(ValueError, match="cross-split group leak"):
        build_manifest(data, frozen_assignments=frozen)


def test_partial_frozen_and_impossible_constraints():
    data = dataset(3)
    data["frozen_assignments"] = {"s0": "test"}
    assert build_manifest(data)["assignments"]["s0"] == "test"
    data["frozen_assignments"] = {"s0": "test", "s1": "test"}
    with pytest.raises(ValueError, match="nonempty"):
        build_manifest(data)
    for mapping in ({"absent": "test"}, {"s0": "validation"}):
        data["frozen_assignments"] = mapping
        with pytest.raises(ValueError):
            build_manifest(data)


@pytest.mark.parametrize("role", EVALUATION_ROLES)
def test_separate_evaluation_roles(role):
    data = dataset()
    data["samples"][0]["evaluation_role"] = role
    result = build_manifest(data)
    assert result["assignments"]["s0"] == "test"
    assert result["evaluation_manifests"][role] == ["s0"]
    assert all(not ids for name, ids in result["evaluation_manifests"].items() if name != role)
    data["samples"][0]["split"] = "train"
    with pytest.raises(ValueError, match="cross-split group leak"):
        build_manifest(data)


def test_roles_cannot_share_component():
    data = dataset()
    data["samples"][0]["evaluation_role"] = EVALUATION_ROLES[0]
    data["samples"][1]["evaluation_role"] = EVALUATION_ROLES[1]
    data["near_duplicate_links"] = [["s0", "s1"]]
    with pytest.raises(ValueError, match="separate evaluation roles"):
        build_manifest(data)
    data["samples"][0]["evaluation_role"] = "headline_foreign_india"
    with pytest.raises(ValueError, match="invalid evaluation role"):
        build_manifest(data)


def test_persistence_checksum_and_overwrite(tmp_path):
    manifest = build_manifest(dataset())
    out = tmp_path / "split.json"
    write_manifest(manifest, out)
    first = out.read_bytes()
    assert json.loads(first) == manifest
    with pytest.raises(FileExistsError):
        write_manifest(manifest, out)
    assert out.read_bytes() == first
    write_manifest(manifest, out, overwrite=True)
    assert out.read_bytes() == first
    altered = copy.deepcopy(manifest)
    altered["seed"] += 1
    with pytest.raises(ValueError, match="checksum"):
        write_manifest(altered, out, overwrite=True)
    assert out.read_bytes() == first


def test_cli_and_frozen_manifest(tmp_path, capsys):
    source, out, second = (tmp_path / name for name in ("input.json", "output.json", "second.json"))
    source.write_text(json.dumps(dataset()), encoding="utf-8")
    assert main([str(source), str(out)]) == 0
    assert main([str(source), str(second), "--seed", "99", "--frozen-manifest", str(out)]) == 0
    assert json.loads(out.read_text())["assignments"] == json.loads(second.read_text())["assignments"]
    with pytest.raises(SystemExit) as exc:
        main([str(source), str(out)])
    assert exc.value.code == 2
    assert main([str(source), str(out), "--overwrite"]) == 0
    corrupt = json.loads(out.read_text())
    corrupt["seed"] = -1
    out.write_text(json.dumps(corrupt), encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(source), str(second), "--frozen-manifest", str(out), "--overwrite"])
    assert "checksum mismatch" in capsys.readouterr().err
