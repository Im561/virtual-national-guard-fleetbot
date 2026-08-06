from pathlib import Path


def test_alert_queue_click_centers_map():
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    assert 'function focusTrackOnMap(callsign)' in js
    assert 'map.flyTo([lat, lon], targetZoom' in js
    assert 'selectTrack(card.dataset.call, true, card.dataset.operationId || null)' in js
    assert 'record.marker.openPopup()' in js


def test_official_alarm_and_timeline_are_wired():
    js = Path('app/static/app.js').read_text(encoding='utf-8')
    assert 'scramble-alarm-upload-20260804.mp3' in js
    assert 'NORAD EVENT TIMELINE' in js
    assert 'ACCEPT INTERCEPT · MARK INBOUND' in js
    assert 'INTERCEPT PHASE CHECKLIST' in js
    assert 'operationResponseAction' in js
    assert 'toggleOperationPhase' in js
    assert 'renderInterceptOverlay()' in js
