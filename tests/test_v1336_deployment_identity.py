from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_release_exposes_build_identity_and_artcc_control():
    assert 'data-build="1.4.8"' in HTML
    assert 'id="build-version">v1.4.8' in HTML
    assert 'id="artcc-focus-select"' in HTML
    assert "TRACK / INTERCEPT DATA" not in HTML
    assert "const CLIENT_BUILD" in JS
    assert "function updateDeploymentIdentity" in JS


def test_frontend_and_version_endpoints_are_versioned_and_identifiable():
    assert 'APP_VERSION = "1.4.8"' in MAIN
    assert 'UI_BUILD_ID = "v1.4.8-deep-audit-reliability"' in MAIN
    assert '@app.get("/api/version")' in MAIN
    assert 'request.url.path.startswith("/static/")' in MAIN
    assert '"Cache-Control"] = "public, max-age=31536000, immutable"' in MAIN
    assert '"Cache-Control": "no-cache, max-age=0, must-revalidate"' in MAIN
    assert '"legacy_track_overlay": False' in MAIN
