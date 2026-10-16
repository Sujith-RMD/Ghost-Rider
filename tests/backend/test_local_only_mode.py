from unittest.mock import patch

from backend import bedrock_service, s3_service
from backend.app.config import Settings
from backend.reports import bedrock as report_bedrock
from backend.reports.generator import generate_report_for_assessment
from backend.reports.template import build_factual_template


def test_local_only_disables_s3_before_default_profile_lookup(monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None,
        GHOST_RIDER_LOCAL_ONLY=True,
        AWS_ACCESS_KEY_ID="configured-key",
        AWS_SECRET_ACCESS_KEY="configured-secret",
    )
    monkeypatch.setattr(s3_service, "get_settings_safely", lambda: settings)
    monkeypatch.setattr(
        s3_service,
        "_resolve_default_credentials",
        lambda: (_ for _ in ()).throw(AssertionError("AWS profile lookup must not run")),
    )
    monkeypatch.setattr(s3_service, "UPLOADS_DIR", tmp_path)
    source = tmp_path / "road.jpg"
    source.write_bytes(b"local image bytes")

    with patch.object(s3_service.boto3, "client") as create_client:
        assert not settings.s3_configured
        assert not s3_service.is_s3_enabled()
        assert s3_service.get_s3_client() is None
        assert s3_service.upload_file_to_s3(str(source), "road.jpg") == "/uploads/road.jpg"
        create_client.assert_not_called()


def test_local_only_reports_use_template_without_bedrock_client(monkeypatch):
    settings = Settings(
        _env_file=None,
        GHOST_RIDER_LOCAL_ONLY=True,
        AWS_ACCESS_KEY_ID="configured-key",
        AWS_SECRET_ACCESS_KEY="configured-secret",
    )
    monkeypatch.setattr(report_bedrock, "get_settings_safely", lambda: settings)
    monkeypatch.setattr(bedrock_service, "get_settings_safely", lambda: settings)
    facts = {"quality_status": "limited", "score_status": "unknown"}

    with patch("boto3.client") as create_client, patch("boto3.Session") as create_session:
        content, model_id = report_bedrock.generate_bedrock_narrative(
            "sample-local", facts, "local-hash"
        )
        report = generate_report_for_assessment("sample-local", facts, include_narrative=True)
        assert report_bedrock.get_bedrock_client() is None
        assert not report_bedrock.is_bedrock_configured()
        assert not bedrock_service.is_bedrock_enabled()
        create_client.assert_not_called()
        create_session.assert_not_called()

    assert model_id is None
    assert content.model_dump() == build_factual_template("sample-local", facts).model_dump()
    assert report.bedrock_model_id is None
    assert report.content.narrative_status.value == "fallback"
    assert report.content.factual_template_used


def test_cloud_integrations_remain_enabled_by_default(monkeypatch):
    settings = Settings(
        _env_file=None,
        BEDROCK_ENABLED=True,
        AWS_ACCESS_KEY_ID="configured-key",
        AWS_SECRET_ACCESS_KEY="configured-secret",
    )
    monkeypatch.setattr(s3_service, "get_settings_safely", lambda: settings)
    monkeypatch.setattr(bedrock_service, "get_settings_safely", lambda: settings)
    monkeypatch.setattr(s3_service, "_resolve_default_credentials", lambda: None)

    assert not settings.GHOST_RIDER_LOCAL_ONLY
    assert s3_service.is_s3_enabled()
    assert bedrock_service.is_bedrock_enabled()
