"""Read-only, single-pass audit of a DatasetNinja RDD tar; never extracts files."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import time
import tarfile

import cv2
import numpy as np


def _dimensions(value):
    if not isinstance(value, dict):
        return None
    w, h = value.get('width'), value.get('height')
    if any(type(x) is not int or x <= 0 for x in (w, h)):
        return None
    return [w, h]


def audit_archive(path, decode_budget_seconds=75.0):
    """Inventory all India_ image/annotation pairs, with a bounded decode budget.

    Budget is cumulative decoder time (not wall time); skipped images still get
    byte hashes. No road/session identity is inferred from filename numbers.
    """
    if not math.isfinite(decode_budget_seconds) or decode_budget_seconds < 0:
        raise ValueError('decode budget must be finite and nonnegative')
    path = Path(path)
    before = path.stat()
    started = time.monotonic()
    documents, records = {}, {}
    issues = Counter()
    examples = defaultdict(list)
    member_names = set()
    members = 0
    decode_time = 0.0
    archive_error = None

    def issue(kind, name):
        issues[kind] += 1
        if len(examples[kind]) < 20:
            examples[kind].append(name)

    try:
        with tarfile.open(path, 'r|*') as archive:
            for member in archive:
                members += 1
                # tarfile otherwise retains all TarInfo objects even in stream mode.
                archive.members.clear()
                name = member.name
                if name in member_names:
                    issue('duplicate_member_path', name)
                member_names.add(name)
                parts = PurePosixPath(name).parts
                if '..' in parts or PurePosixPath(name).is_absolute():
                    issue('unsafe_member_path', name)
                if name in ('LICENSE.md', 'README.md', 'meta.json'):
                    if not member.isfile() or member.size > 1024 * 1024:
                        issue('invalid_document', name)
                        continue
                    raw = archive.extractfile(member).read()
                    documents[name] = {'text': raw.decode('utf-8', errors='replace'),
                                       'sha256': hashlib.sha256(raw).hexdigest()}
                    continue
                if len(parts) != 3 or parts[0] not in ('train', 'test') or not parts[2].startswith('India_'):
                    continue
                split, folder, filename = parts
                if folder == 'ann' and filename.endswith('.json'):
                    image_name = filename[:-5]
                    kind = 'annotation'
                elif folder == 'meta' and filename.endswith('.json'):
                    image_name, kind = filename[:-5], 'metadata'
                elif folder == 'img' and filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_name, kind = filename, 'image'
                else:
                    issue('unexpected_india_member', name)
                    continue
                record = records.setdefault((split, image_name), {'split': split, 'image_name': image_name})
                if not member.isfile() or member.size > 64 * 1024 * 1024:
                    issue('invalid_india_member', name)
                    continue
                raw = archive.extractfile(member).read()
                if kind in record:
                    issue('duplicate_pair_member', name)
                    continue
                entry = {'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                record[kind] = entry
                if kind == 'metadata':
                    try:
                        entry['content'] = json.loads(raw)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        issue('malformed_image_metadata', name)
                    continue
                if kind == 'image':
                    entry['decode_status'] = 'not_attempted_budget'
                    if decode_time < decode_budget_seconds:
                        tick = time.monotonic()
                        try:
                            image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
                            if image is None:
                                raise ValueError('decoder returned None')
                            entry['dimensions'] = [int(image.shape[1]), int(image.shape[0])]
                            entry['decode_status'] = 'decoded'
                        except (ValueError, cv2.error) as exc:
                            entry['decode_status'] = 'failed'
                            entry['error'] = str(exc)
                            issue('decode_failure', name)
                        decode_time += time.monotonic() - tick
                    continue
                try:
                    ann = json.loads(raw)
                    if not isinstance(ann, dict):
                        raise ValueError('annotation must be an object')
                    entry['dimensions'] = _dimensions(ann.get('size'))
                    if entry['dimensions'] is None:
                        issue('invalid_annotation_dimensions', name)
                    objects = ann.get('objects')
                    if not isinstance(objects, list):
                        raise ValueError('objects must be a list')
                    entry['objects'] = len(objects)
                    entry['classes'] = dict(Counter(o.get('classTitle', '<missing>') if isinstance(o, dict) and isinstance(o.get('classTitle', '<missing>'), str) else '<malformed>' for o in objects))
                    entry['valid_boxes'] = 0
                    for obj in objects:
                        try:
                            if not isinstance(obj, dict) or obj.get('geometryType') != 'rectangle':
                                raise ValueError()
                            points = obj['points']['exterior']
                            if len(points) != 2 or any(len(p) != 2 for p in points):
                                raise ValueError()
                            x1, y1 = points[0]
                            x2, y2 = points[1]
                            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (x1, y1, x2, y2)) or x2 <= x1 or y2 <= y1:
                                raise ValueError()
                        except (KeyError, TypeError, ValueError):
                            issue('malformed_box', name)
                            continue
                        dims = entry['dimensions']
                        # Coordinates at width/height are flagged under a pixel-index convention.
                        if dims and not (0 <= x1 < x2 < dims[0] and 0 <= y1 < y2 < dims[1]):
                            issue('out_of_range_box', name)
                        else:
                            entry['valid_boxes'] += 1
                    entry['status'] = 'parsed'
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    entry['status'] = 'malformed'
                    entry['error'] = str(exc)
                    issue('malformed_annotation', name)
    except (tarfile.TarError, OSError, EOFError) as exc:
        archive_error = str(exc)

    try:
        meta = json.loads(documents.get('meta.json', {}).get('text', '{}'))
        classes = meta['classes']
        declared = {c['title'] for c in classes}
    except (ValueError, KeyError, TypeError):
        classes, declared = [], set()
        issue('invalid_meta', 'meta.json')
    for document in ('LICENSE.md', 'README.md', 'meta.json'):
        if document not in documents:
            issue('missing_document', document)
    summaries = {}
    hashes = defaultdict(list)
    names = defaultdict(list)
    for split in ('train', 'test'):
        summary = Counter()
        dimensions, class_counts = Counter(), Counter()
        for (s, filename), record in sorted(records.items()):
            if s != split:
                continue
            image, ann = record.get('image'), record.get('annotation')
            summary['images'] += int(image is not None)
            summary['annotations'] += int(ann is not None)
            if 'metadata' in record:
                summary['metadata_sidecars'] += 1
                summary['empty_metadata_sidecars'] += int(record['metadata'].get('content') == {})
            summary['paired'] += int(image is not None and ann is not None)
            if not image or not ann:
                issue('missing_image' if not image else 'missing_annotation', f'{split}/{filename}')
            if image:
                summary[image['decode_status']] += 1
                hashes[image['sha256']].append(image['path'])
                names[filename].append(image['path'])
                if image.get('dimensions'):
                    dimensions['x'.join(map(str, image['dimensions']))] += 1
            if ann and ann.get('status') == 'parsed':
                summary['objects'] += ann['objects']
                summary['valid_boxes'] += ann['valid_boxes']
                if ann['objects'] == 0:
                    summary['empty_annotation_files'] += 1
                    ann['label_interpretation'] = 'unannotated_test_not_negative' if split == 'test' else 'empty_train_requires_human_negative_review'
                class_counts.update(ann['classes'])
                for title, count in ann['classes'].items():
                    if title not in declared:
                        issues['undeclared_class_objects'] += count
                        if len(examples['undeclared_class_objects']) < 20:
                            examples['undeclared_class_objects'].append(ann['path'])
                if image and image.get('dimensions') and image['dimensions'] != ann['dimensions']:
                    issue('dimension_mismatch', image['path'])
        summaries[split] = {**dict(summary), 'decoded_dimensions_width_height': dict(dimensions), 'class_object_counts': dict(class_counts)}
    after = path.stat()
    return {
        'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'archive': {'path': path.as_posix(), 'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns,
                    'unchanged_during_audit': (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                    'members': members, 'stream_completed': archive_error is None, 'error': archive_error,
                    'sha256': None, 'checksum_status': 'not_computed_no_second_14GB_read'},
        'method': {'tar_mode': 'r|*', 'extracted_files': 0, 'india_selection': 'train|test / img|ann / India_* filename',
                   'decode_budget_seconds': decode_budget_seconds, 'decode_seconds': decode_time,
                   'decode_order': 'archive order until cumulative decoder time budget exhausted',
                   'elapsed_seconds': time.monotonic() - started, 'decoder': 'OpenCV ' + cv2.__version__,
                   'box_bounds': '0 <= x1 < x2 < width and 0 <= y1 < y2 < height; no clipping'},
        'documents': documents, 'declared_classes': classes, 'splits': summaries,
        'issues': dict(issues), 'issue_examples_first_20': dict(examples),
        'exact_image_duplicate_groups': [v for v in hashes.values() if len(v) > 1],
        'cross_split_image_name_groups': [v for v in names.values() if len(v) > 1],
        'inventory': [records[k] for k in sorted(records)],
        'admission': {'acquisition': 'mirror_archive_obtained_not_original_release_verified',
                      'rights_status': 'mirror_terms_recorded_original_permission_unverified',
                      'license_interpretation': 'Exact mirror LICENSE.md is evidence of a mirror claim, not independent verification of original reuse permission.',
                      'training_ready': False, 'precise_masks_available': False,
                      'metric_scale': 'unverified', 'parent_road_session_sequence': 'unknown; filename integer is not a verified parent or adjacent-frame group',
                      'negative_policy': 'Empty test JSON is unannotated, never an intact negative; empty train JSON needs human review.',
                      'remaining_gates': ['Original-release identity and reuse rights verification', 'Human review of at least 50 varied image/overlay pairs', 'Near-duplicate and original-source ancestry checks including RDD2020', 'Road/session/adjacent-frame grouping and frozen independent Indian evaluation split', 'Human-reviewed masks for precise extent; boxes are localization only', 'Reviewed intact negatives and surface-domain coverage'],
                      'prohibited_inferences': ['masks or precise area from boxes', 'physical units without scale', 'model performance or India/live validation']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--decode-budget-seconds', type=float, default=75.0)
    args = parser.parse_args()
    if Path(args.archive).resolve() == Path(args.output).resolve():
        parser.error('output must not overwrite the archive')
    report = audit_archive(args.archive, args.decode_budget_seconds)
    report['command'] = ['python', '-B', '-m', 'eval.rdd_archive_audit', '--archive', args.archive, '--output', args.output, '--decode-budget-seconds', str(args.decode_budget_seconds)]
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'archive': report['archive'], 'splits': report['splits'], 'issues': report['issues'], 'elapsed_seconds': report['method']['elapsed_seconds']}))


if __name__ == '__main__':
    main()
