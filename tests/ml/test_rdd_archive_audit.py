"""In-memory archives keep test runs from writing dataset bytes to disk."""
import io
import json
from types import SimpleNamespace
import tarfile
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from eval.rdd_archive_audit import audit_archive


def run_audit(entries, budget=75):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, value in entries:
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    buffer.seek(0)
    real_open = tarfile.open
    with patch('eval.rdd_archive_audit.Path.stat', return_value=SimpleNamespace(st_size=len(buffer.getvalue()), st_mtime_ns=1)), patch('eval.rdd_archive_audit.tarfile.open', side_effect=lambda *a: real_open(fileobj=buffer, mode='r|*')):
        return audit_archive('memory.tar', budget)


def image():
    return cv2.imencode('.png', np.zeros((8, 10, 3), np.uint8))[1].tobytes()


def ann(objects=None, width=10):
    return {'size': {'width': width, 'height': 8}, 'objects': objects or []}


def documents():
    return [('LICENSE.md', b'Exact mirror terms\n'), ('README.md', b'Mirror README'), ('meta.json', {'classes': [{'title': 'pothole', 'shape': 'rectangle'}]})]


def box(title='pothole', points=None):
    return {'classTitle': title, 'geometryType': 'rectangle', 'points': {'exterior': points if points is not None else [[1, 1], [5, 6]]}}


def test_inventory_decode_pairing_and_unannotated_test():
    report = run_audit(documents() + [('train/img/India_1.png', image()), ('train/ann/India_1.png.json', ann([box()])), ('test/img/India_2.png', image()), ('test/ann/India_2.png.json', ann()), ('train/img/Japan_1.png', b'ignored'), ('train/meta/India_1.png.json', {})])
    assert report['archive']['stream_completed']
    assert report['splits']['train']['decoded'] == 1
    assert report['splits']['train']['empty_metadata_sidecars'] == 1
    assert report['splits']['train']['valid_boxes'] == 1
    assert report['splits']['test']['empty_annotation_files'] == 1
    assert report['inventory'][0]['annotation']['label_interpretation'] == 'unannotated_test_not_negative'
    assert len(report['exact_image_duplicate_groups']) == 1
    assert report['documents']['LICENSE.md']['text'] == 'Exact mirror terms\n'
    assert report['admission']['training_ready'] is False
    assert report['issues'] == {}


def test_bad_labels_missing_pairs_and_decode_failure():
    report = run_audit(documents() + [('train/ann/India_a.png.json', ann([box(points=[[0, 0], [10, 8]]), box(points=[[2, 2], [1, 1]]), box('unknown')], width=10)), ('train/img/India_b.png', b'broken'), ('test/ann/India_c.png.json', b'{bad'), ('test/ann/India_d.png.json', {'objects': 'bad'})])
    for issue in ('out_of_range_box', 'malformed_box', 'undeclared_class_objects', 'decode_failure', 'missing_image', 'missing_annotation', 'malformed_annotation', 'invalid_annotation_dimensions'):
        assert report['issues'][issue] > 0


def test_budget_zero_exact_coverage_and_dimension_mismatch():
    entries = documents() + [('train/img/India_a.png', image()), ('train/ann/India_a.png.json', ann(width=9))]
    report = run_audit(entries, budget=0)
    assert report['splits']['train']['not_attempted_budget'] == 1
    assert 'decoded' not in report['splits']['train']
    assert run_audit(entries)['issues']['dimension_mismatch'] == 1


def test_duplicate_member_and_cross_split_names():
    report = run_audit(documents() + [('train/img/India_a.png', image()), ('train/img/India_a.png', image()), ('test/img/India_a.png', image())])
    assert report['issues']['duplicate_member_path'] == 1
    assert report['issues']['duplicate_pair_member'] == 1
    assert len(report['cross_split_image_name_groups']) == 1


@pytest.mark.parametrize('budget', [-1, float('nan'), float('inf')])
def test_invalid_budget(budget):
    with pytest.raises(ValueError):
        audit_archive('unused.tar', budget)
