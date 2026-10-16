"""Public session monitoring and reports must use stored evidence."""
from fastapi.testclient import TestClient
from backend.api.server import app
from backend.api import v1
from backend.schemas import SegmentResult


def test_session_can_be_monitored_and_finished_frames_are_refused():
    with TestClient(app) as client:
        session = client.post('/v1/sessions', json={'mode': 'live'}).json()
        path = '/v1/sessions/' + session['session_id']
        result = client.get(path)
        assert result.status_code == 200
        assert result.json()['status'] == 'live'
        assert result.json()['latest_sample_id'] is None
        assert client.post(path + '/finish').json()['status'] == 'finished'
        assert client.post(path + '/frames', files={'frame': ('frame.jpg', b'bytes', 'image/jpeg')}).status_code == 409
        assert client.get('/v1/sessions/missing-session').status_code == 404


def test_reports_reject_unknown_assessments():
    with TestClient(app) as client:
        response = client.post('/v1/reports', json={'assessment_id': 'unknown-sample', 'score_value': 99})
        assert response.status_code == 404


def test_report_is_retrievable_and_uses_stored_facts(monkeypatch):
    sample = SegmentResult(sample_id='stored-report-sample', segment_id=1, geometry_valid=False)
    monkeypatch.setattr(v1, '_get_sample', lambda sample_id: sample if sample_id == sample.sample_id else None)
    with TestClient(app) as client:
        response = client.post('/v1/reports', json={'assessment_id': sample.sample_id, 'score_value': 99})
        assert response.status_code == 200
        report = response.json()
        assert '99' not in report['content']['summary']
        assert 'quality_not_measured' in report['content']['summary']
        assert any('Distress measurements are unavailable' in item for item in report['content']['limitations'])
        assert client.get('/v1/reports/' + report['report_id']).json() == report
        assert client.get('/v1/reports/missing-report').status_code == 404
