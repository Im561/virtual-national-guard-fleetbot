# Railway deployment — v1.4.2

## Repository layout

Deploy the contents of this archive directly at repository root. `Dockerfile`, `railway.json`, `requirements.txt`, `app/`, and `tests/` must not be nested inside another folder.

## Persistent workflow state

1. Create a Railway volume.
2. Mount it at `/app/data`.
3. Set `STATE_DB_PATH=/app/data/vng_adoc_state.sqlite3`.
4. Redeploy and confirm `/api/version` reports `persistent_workflow: true`.

The application remains usable without a volume, but shared workflow state will reset when Railway replaces the container.

## Optimization variables

```env
ENABLE_LIVE_DELTAS=true
DELTA_FULL_SNAPSHOT_INTERVAL=30
SPATIAL_GRID_DEGREES=5
STATE_DB_PATH=/app/data/vng_adoc_state.sqlite3
STATE_PERSIST_DEBOUNCE_SECONDS=0.35
COMMUNICATIONS_CLEAR_MATCH_SNAPSHOTS=2
COMMUNICATIONS_FREQUENCY_CHANGE_GRACE_SECONDS=25
COMMUNICATIONS_HANDOFF_COOLDOWN_SECONDS=120
TEMPORARY_EXEMPTION_DEFAULT_MINUTES=15
TEMPORARY_EXEMPTION_MAX_MINUTES=120
```

## Verification

- Footer: `BUILD v1.4.2`
- `/api/version`: `live_deltas`, `persistent_workflow`, `spatial_index`, `alert_evidence`, `alert_timeline`, `temporary_exemptions`, and `handoff_visualization` are `true`
- Browser Network panel: first WebSocket state is `type: live`; subsequent efficient updates may be `type: delta`
- `/health`: includes `processing_breakdown`

---

# Railway deployment — v1.3.31

Deploy the complete contents of this folder to the production branch connected to Railway.

## Required rollout steps

1. Replace the older repository contents with v1.3.31.
2. Confirm Railway builds and `/health` returns HTTP 200.
3. Perform a browser hard refresh: `Ctrl + Shift + R`.
4. Press **TEST SCRAMBLE ALARM** once to authorize browser audio.
5. Select an airborne aircraft and open **DETECTOR DIAGNOSTICS**.
6. Verify the map and operations rail fit at desktop width and on a phone-sized window.
7. Select a track reporting `121.500` or `122.800` and confirm the radio is labeled `NOT ATC CONTACT`; the wrong-frequency timer must continue unless a separate live ATC frequency matches.
8. Locate or temporarily simulate remarks containing `vUSCG` or `vRCAF`; confirm the matched marker appears as a VSOA track identifier without generating an intercept alert by itself.
9. Open **INTERCEPT CONTROL**, assign one live aircraft to another, and verify separation, closure/opening rate, ETA, course, heading, speed, altitude, and assignment status update on every fresh feed.
10. Open **ACTIVE INTERCEPT** and verify the response-status buttons update both connected consoles.
11. Open **ATC QUICK**, save a console label, load a callsign, and verify communications-gate details and quick actions.
12. With split positions online, confirm multiple automatic frequency-mismatch tracks show one **PRIMARY AUDIBLE INCIDENT** and the remaining cards show **GROUPED TRACK · NO ADDITIONAL ALARM**.
13. Verify a low/slow aircraft matching a published CTAF within 50 NM is exempt, while a high-altitude en-route aircraft near the same airport is not automatically exempt.
14. Open the same site in a second browser console and confirm assignments, response status, cancellation, and shared phase changes appear on both consoles.

## Recommended variables

```env
POLL_SECONDS=10
HTTP_FALLBACK_SECONDS=15
MONITOR_CANADA=true

FEED_STALE_WARNING_SECONDS=45
FEED_STALE_CRITICAL_SECONDS=90
MAX_OBSERVED_FEED_TICK_SECONDS=30
COMMUNICATIONS_CASE_GAP_SECONDS=60
MANUAL_NORDO_STALE_SECONDS=180
FREQUENCY_MATCH_TOLERANCE_HZ=1500
ADVISORY_FREQUENCY_WHITELIST_RADIUS_NM=50
ADVISORY_FREQUENCY_WHITELIST_MAX_ALTITUDE_FT=12000
ADVISORY_FREQUENCY_WHITELIST_MAX_GROUNDSPEED_KT=250
EARLY_UNICOM_HANDOFF_LOOKAHEAD_MINUTES=12
EARLY_UNICOM_HANDOFF_MAX_LOOKAHEAD_NM=90
SCRAMBLE_INCIDENT_RESET_SECONDS=300

FREQUENCY_MISMATCH_OBSERVE_SECONDS=30
FREQUENCY_MISMATCH_OBSERVE_MIN_ALTITUDE_FT=5000
FREQUENCY_MISMATCH_OBSERVE_MIN_GROUNDSPEED_KT=80
FREQUENCY_MISMATCH_OBSERVE_REQUIRE_IFR=true

NORDO_ADVISORY_SECONDS=120
NORDO_WARNING_SECONDS=300
NORDO_INVESTIGATE_AFTER_SWITCH_SECONDS=180
NORDO_INVESTIGATE_SECONDS=300
NORDO_PREVIOUS_MATCH_WINDOW_SECONDS=1800
NORDO_MIN_ALTITUDE_FT=5000
NORDO_MIN_GROUNDSPEED_KT=80
NORDO_TERMINAL_EXCLUSION_NM=55
NORDO_TERMINAL_EXCLUSION_MAX_ALTITUDE_FT=12000
NORDO_TERMINAL_EXCLUSION_MAX_GROUNDSPEED_KT=250
NORDO_REQUIRE_IFR=true
NORDO_REQUIRE_HIGH_CONFIDENCE_COVERAGE=true

AUTO_SCRAMBLE_FREQUENCY_MISMATCH_SECONDS=480
AUTO_SCRAMBLE_ATC_MIN_ONLINE_SECONDS=300
AUTO_SCRAMBLE_MIN_ALTITUDE_FT=10000
AUTO_SCRAMBLE_MIN_GROUNDSPEED_KT=150
AUTO_SCRAMBLE_REQUIRE_IFR=true
AUTO_SCRAMBLE_REQUIRE_REPORTED_RADIO=true
AUTO_SCRAMBLE_REQUIRE_HIGH_CONFIDENCE_COVERAGE=true

CONSOLE_PRESENCE_HEARTBEAT_SECONDS=30
CONSOLE_PRESENCE_TIMEOUT_SECONDS=105
ALLOW_CROSS_BORDER_QRA_RECOMMENDATIONS=false

ORBIT_DETECTION_WINDOW_SECONDS=900
ORBIT_DETECTION_MIN_DURATION_SECONDS=600
ORBIT_DETECTION_TURN_DEGREES=600
ORBIT_DETECTION_MAX_DISPLACEMENT_NM=18
ORBIT_DETECTION_MAX_RADIUS_NM=22
ORBIT_DETECTION_MIN_POINTS=20
ORBIT_DETECTION_MIN_ALTITUDE_FT=3000
ORBIT_DETECTION_MIN_GROUNDSPEED_KT=60
ORBIT_DEPARTURE_SUPPRESSION_NM=80
ORBIT_DEPARTURE_SUPPRESSION_SECONDS=1500
ORBIT_DEPARTURE_SUPPRESSION_MAX_ALTITUDE_FT=24000
ORBIT_TURN_DIRECTION_CONSISTENCY=0.72
ORBIT_DETECTION_MIN_NET_TURN_DEGREES=500
ORBIT_NORDO_CORROBORATION_SECONDS=300

ENABLE_ROUTE_DEVIATION_ALERTS=false
NAVIGATION_ANOMALIES_OBSERVATION_ONLY=true
ATC_REQUIRE_UNAMBIGUOUS_CONTROLLER=true
ATC_POLYGON_ONLY_ALERTS=false
ATC_SPLIT_FALLBACK_ALERTS=false
ENABLE_MISSING_RADIO_ALERT=false
WHITELISTED_SQUAWKS=1200,2000

USER_AGENT=VNG-ADOC/1.3.31 contact=your-email@example.com
```

## Operational verification

A developing mismatch should show:

```text
WRONG-FREQ TIMER
CASE STATE
AUTO-FLAG ELIGIBLE TIMER
LAST CASE RESET
ATC COVERAGE CANDIDATES
```

The visible timer may continue while the eligible red-alert timer is paused. That is expected when ATC stabilization, altitude, speed, IFR, radio-data, or coverage-confidence requirements are not currently satisfied.

## Important limitations

- Shared manual actions and intercept checklists remain in Railway process memory and reset on redeployment.
- VATSIM public data cannot prove whether a pilot heard or answered a controller.
- Same-origin protection is not user authentication. Keep the URL restricted until OAuth roles are implemented.
- Do not run multiple Uvicorn workers while operational state remains in memory; each worker would maintain separate timers and intercept workflows. The live viewer count is also process-local and therefore assumes the documented single-worker deployment.
