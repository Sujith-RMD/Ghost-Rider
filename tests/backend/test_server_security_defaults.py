from backend.app.config import Settings
from backend.api import server


def test_default_cors_is_limited_to_local_desktop_origins(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    settings = Settings(_env_file=None)

    assert "*" not in settings.cors_origin_list
    assert "http://127.0.0.1:5173" in settings.cors_origin_list
    assert "http://localhost:4173" in settings.cors_origin_list


def test_explicit_cors_origins_override_local_defaults():
    settings = Settings(_env_file=None, CORS_ORIGINS="https://roadsight.example")

    assert settings.cors_origin_list == ["https://roadsight.example"]


def test_local_media_is_public_for_local_development_by_default():
    settings = Settings(_env_file=None)

    assert settings.LOCAL_UPLOADS_PUBLIC is True


def test_local_static_upload_mount_can_be_disabled(monkeypatch):
    monkeypatch.setattr(server.settings, "LOCAL_UPLOADS_PUBLIC", False)

    app = server.create_app()

    assert not any(getattr(route, "path", None) == "/uploads" for route in app.routes)
