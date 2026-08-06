from app.sua import parse_canadian_openair


def test_canadian_openair_restricted_area_parses():
    sample = '''
AC R
AN CYR999 TEST RANGE
AL SFC
AH FL180
DP 45:00:00.0N 075:00:00.0W
DP 45:10:00.0N 075:00:00.0W
DP 45:10:00.0N 074:50:00.0W
DP 45:00:00.0N 075:00:00.0W
'''
    areas = parse_canadian_openair(sample, 'https://example.test/canada.txt')
    assert len(areas) == 1
    assert areas[0]['designation'] == 'CYR999'
    assert areas[0]['floor_ft'] == 0
    assert areas[0]['ceiling_ft'] == 18000
    assert areas[0]['country'] == 'CANADA'
    assert areas[0]['geometry']['type'] == 'Polygon'
