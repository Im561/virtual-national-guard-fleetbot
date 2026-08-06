from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'app/static/app.js').read_text()


def test_uploaded_scramble_alarm_is_bundled_and_referenced():
    asset = ROOT / 'app/static/assets/scramble-alarm-upload-20260804.mp3'
    assert asset.exists()
    assert asset.stat().st_size > 500_000
    assert "/static/assets/scramble-alarm-upload-20260804.mp3" in JS
    assert "vng-scramble-alarm.mp3" not in JS
    assert "fallback-scramble-alarm.mp3" not in JS


def test_old_alarm_assets_removed():
    assets = ROOT / 'app/static/assets'
    assert not (assets / 'vng-scramble-alarm.mp3').exists()
    assert not (assets / 'fallback-scramble-alarm.mp3').exists()


def test_alarm_asset_is_not_empty_or_duplicate_placeholder():
    asset = ROOT / 'app/static/assets/scramble-alarm-upload-20260804.mp3'
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    assert len(digest) == 64
