from app.sua import parse_altitude_ft


def test_sua_altitude_parser():
    assert parse_altitude_ft(None, None, "SFC", None, upper=False) == 0
    assert parse_altitude_ft("180", None, "FL180", None, upper=True) == 18000
    assert parse_altitude_ft("10000", "FT", None, None, upper=True) == 10000
    assert parse_altitude_ft(None, None, "UNLTD", None, upper=True) == 999999
