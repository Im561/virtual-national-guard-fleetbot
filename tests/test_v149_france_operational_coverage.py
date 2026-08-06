from app.bases import AIRCRAFT_SPEED_KT, BASES, recommend_base
from app.config import settings
from app.geometry import is_enabled_region, is_france_region

FRENCH_QRA = {"LFSI", "LFSN", "LFSX", "LFBM", "LFMO", "LFKJ"}
FRENCH_SUPPORT = {"LFOE", "LFPV", "LFOJ", "LFOA", "LFDN", "LFBD", "LFBC", "LFMI", "LFMY"}


def test_france_enabled_and_region_includes_mainland_and_corsica():
    assert settings.monitor_france is True
    assert is_france_region(48.85, 2.35)
    assert is_france_region(41.92, 9.40)
    assert is_enabled_region(48.85, 2.35, settings.monitor_canada, settings.monitor_france)
    assert not is_france_region(51.50, -0.12)


def test_requested_french_base_network_is_present():
    french = {b["icao"]: b for b in BASES if b.get("country") == "FRANCE"}
    assert set(french) == FRENCH_QRA | FRENCH_SUPPORT
    assert all(french[icao]["scramble_enabled"] for icao in FRENCH_QRA)
    assert all(not french[icao]["scramble_enabled"] for icao in FRENCH_SUPPORT)
    assert all(french[icao]["display_enabled"] for icao in french)


def test_french_qra_recommendations_stay_in_france():
    paris = recommend_base(48.86, 2.35, 90, 430, 35000, target_region="FRANCE")
    corsica = recommend_base(42.0, 9.0, 180, 320, 18000, target_region="FRANCE")
    assert paris is not None and paris["country"] == "FRANCE" and paris["icao"] in FRENCH_QRA
    assert corsica is not None and corsica["icao"] == "LFKJ"
    assert paris["icao"] not in FRENCH_SUPPORT


def test_french_interceptor_profiles_are_available():
    assert AIRCRAFT_SPEED_KT["RAFALE"] == 800
    assert AIRCRAFT_SPEED_KT["M2K"] == 760


def test_frontend_exposes_france_only_without_eu_rollout():
    html = open("app/static/index.html", encoding="utf-8").read()
    js = open("app/static/app.js", encoding="utf-8").read()
    assert 'data-region="france"' in html
    assert 'data-region-filter="france"' in html
    assert "FRANCE ONLY" in html
    assert "france: { bounds:" in js
    assert "FRANCE QRA" in html
    assert "EUROPE" not in html.upper()
    assert "NATO" not in html.upper()


def test_french_advisory_frequency_safeguards_and_base_fallbacks():
    import json
    from app.airports import FALLBACK_AIRPORTS
    payload = json.load(open("app/data/advisory_frequencies.json", encoding="utf-8"))
    french = [item for item in payload["airports"] if item.get("c") == "FR"]
    assert "FR" in payload["countries"]
    assert len(french) >= 80
    assert any(freq["t"] in {"AFIS", "A/A", "CTAF", "INFO"} for item in french for freq in item.get("f", []))
    assert all(icao in FALLBACK_AIRPORTS for icao in FRENCH_QRA | FRENCH_SUPPORT)


def test_version_api_declares_france_capability():
    main = open("app/main.py", encoding="utf-8").read()
    assert '"france_operational_coverage": settings.monitor_france' in main
    assert '"monitor_france": settings.monitor_france' in main
