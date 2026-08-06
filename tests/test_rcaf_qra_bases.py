from app.bases import AIRCRAFT_SPEED_KT, BASES, recommend_base


RCAF_ICAOS = {"CYOD", "CYBG", "CYEV", "CYZF", "CYFB", "CYRT"}


def test_all_rcaf_qra_locations_are_present_and_enabled():
    rcaf = {base["icao"]: base for base in BASES if base["icao"] in RCAF_ICAOS}
    assert set(rcaf) == RCAF_ICAOS
    assert all(base["scramble_enabled"] for base in rcaf.values())
    assert all("F18H" in base["aircraft"] for base in rcaf.values())


def test_cf35_is_only_at_primary_rcaf_qra_bases():
    rcaf = {base["icao"]: base for base in BASES if base["icao"] in RCAF_ICAOS}
    assert "F35" in rcaf["CYOD"]["aircraft"]
    assert "F35" in rcaf["CYBG"]["aircraft"]
    assert all("F35" not in rcaf[icao]["aircraft"] for icao in RCAF_ICAOS - {"CYOD", "CYBG"})
    assert rcaf["CYOD"]["qra_role"] == "PRIMARY"
    assert rcaf["CYBG"]["qra_role"] == "PRIMARY"
    assert all(rcaf[icao]["qra_role"] == "FOL" for icao in RCAF_ICAOS - {"CYOD", "CYBG"})


def test_f18h_intercept_speed_and_nearest_canadian_base():
    assert AIRCRAFT_SPEED_KT["F18H"] == 780
    recommendation = recommend_base(63.76, -68.56, 270, 430, 35000)
    assert recommendation is not None
    assert recommendation["icao"] == "CYFB"
    assert recommendation["aircraft"] == ["F18H"]
