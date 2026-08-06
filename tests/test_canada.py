from app.config import settings
from app.geometry import is_enabled_region


def test_canada_enabled_by_default():
    assert settings.monitor_canada is True
    assert is_enabled_region(43.68, -79.63, settings.monitor_canada) is True


def test_us_still_enabled_with_canada():
    assert is_enabled_region(38.90, -77.04, settings.monitor_canada) is True
