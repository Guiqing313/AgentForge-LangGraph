"""C1：Docker 配置静态检查（不依赖 Docker）。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_api_dockerfile_hardened():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER app" in text
    assert "HEALTHCHECK" in text
    assert "requirements-lock.txt" in text


def test_frontend_dockerfile_hardened():
    text = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "USER app" in text
    assert "HEALTHCHECK" in text
    assert "_stcore/health" in text


def test_compose_uses_host_services_and_healthchecks():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "host.docker.internal" in text
    assert "service_healthy" in text
    assert "healthcheck" in text
    assert "restart: unless-stopped" in text


def test_dockerignore_excludes_secrets_and_data():
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for item in (".env", "venv", "data", "models"):
        assert item in text
