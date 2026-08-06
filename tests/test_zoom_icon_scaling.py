from pathlib import Path


def test_aircraft_icons_scale_with_map_zoom():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'app/static/app.js').read_text(encoding='utf-8')
    css = (root / 'app/static/styles.css').read_text(encoding='utf-8')

    assert "function densityForZoom(zoom)" in js
    assert "if (zoom <= 4) return 'micro';" in js
    assert "if (zoom === 5) return 'compact';" in js
    assert "if (zoom === 6) return 'reduced';" in js
    assert "return 'full';" in js
    assert "state.iconDensity" in js
    assert "scopeIcon(pilot, state.iconDensity)" in js
    assert "tacticalIcon(pilot, state.iconDensity)" in js

    for selector in (
        '.scope-track.micro',
        '.scope-track.compact',
        '.scope-track.reduced',
        '.tactical-track.micro',
        '.tactical-track.compact',
        '.tactical-track.reduced',
    ):
        assert selector in css


def test_critical_tracks_are_promoted_one_density_level():
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    assert 'function promotedIconDensity(density, pilot)' in js
    assert "pilot?.severity === 'red'" in js
    assert 'pilot?.active_intercept' in js
