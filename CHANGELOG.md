# Changelog

## v1.4.8 — Deep reliability audit and pre-scramble denial

- Serialized live WebSocket broadcasts and protected the shared revision baseline.
- Ensured new consoles receive a complete baseline before deltas or presence updates.
- Preserved server ordering in keyed pilot, alert, operation, intercept, exemption, and controller updates.
- Hardened modal focus handling and Leaflet resource integrity.
- Added a compact shared pre-scramble review strip during the final 30 seconds before automatic communications escalation.
- Added a case-scoped **DENY AUTO ALERT** action that keeps the communications watch active while preventing that case from automatically generating a scramble alert.
- Emergency squawks and manual NORDO designations bypass the denial and remain immediate.
- Persisted shared denial metadata and added expiration cleanup.
- Expanded regression coverage to 213 passing tests.

## v1.4.7 — Compact docked map menu and final overlay removal

- Replaced the long floating map toolbar with a compact docked control strip.
- Grouped secondary controls into Layers, Region, and Tools panels.
- Secondary panels expand in the layout instead of floating over the map.
- Permanently removed the ATC Scope range/center HUD from markup and JavaScript.
- Added Escape and map-click behavior to close open option groups.
- Preserved ARTCC focus, DCA helicopter routes, intercept controls, and all existing map layers.

## v1.4.7 — USCG BLACKJACK and DCA helicopter route reference overlay

- Conservatively recognizes likely USCG NCRAD BLACKJACK helicopter tracks from a BLACKJACK/BJK callsign or explicit USCG + BLACKJACK remarks, helicopter type, and proximity to KDCA.
- Adds a click-controlled DCA/NCR helicopter reference overlay with Washington Routes 1 and 5, the Broad Creek Transition, and the permanently closed Route 4 segment.
- Links directly to the FAA Baltimore–Washington Helicopter Route Chart effective July 9, 2026.
- Labels all route geometry as reference-only; the current FAA chart and live ATC instructions remain controlling.
- Surfaces BLACKJACK identity and mission-role hints in aircraft popups and prioritizes BLACKJACK in the live VSOA roster.

## v1.4.7 — Permanent overlay removal and restored aircraft details

- Removed the legacy selected-track/NORDO overlay renderer, hover listeners, toggle, and saved hover preference.
- Added CSS-level protection so old overlay identifiers cannot display after deployment.
- Added styled native VSOA and target aircraft selectors to ATC Coordination.
- Restored reported and expected frequencies, current and assigned squawks, squawk comparison, route, and detector diagnostics.
- Added a structured click popup with the same essential communications and transponder information.
- Preserved direct VSOA self-dispatch to a selected intercept target.

## v1.4.7 — VSOA self-identification and direct ATC dispatch

- Added a persistent MY VSOA AIRCRAFT selector to the ATC Coordination toolbar.
- The previously blank selected-aircraft area now lists all live airborne VSOA-tagged flights.
- Automatically selects the sole live VSOA aircraft when only one is visible.
- Added one-click assignment or reassignment of the selected operator aircraft to a chosen live target.
- The ATC tactical map shows the operator aircraft and a pending route to the selected target before assignment.
- Existing shared intercept APIs, recalculation, persistence, and mission controls remain in use.

## v1.4.3 — Independent mass-alert verification and ATC dismissal

- Keeps simultaneous possible-NORDO tracks visible while independently re-verifying each one.
- Pauses only automatic scramble/intercept escalation during the verification hold.
- Emergency squawks and manual NORDO bypass the guard.
- Adds ATC-panel automatic-flag dismissal with a required reason and audit event.
- Persists dismissal metadata across connected consoles and restarts.

## v1.4.3 — Evidence, timeline, stability, exemptions, and ATC layout

- Added alert evidence and event timeline panels.
- Added frequency-change grace and post-handoff cooldown logic.
- Added shared expiring communications exemptions.
- Added ARTCC handoff map visualization.
- Hardened the ATC Coordination layout against overlap and clipping.

# Changelog

## v1.4.1 — Click-only map details and optional delayed hover cards

- Aircraft detail cards no longer appear merely by moving the pointer across the situation map.
- Clicking an aircraft opens its compact popup and selects the track.
- Added a persistent `HOVER DETAILS OFF/ON` map control; the default is OFF.
- When enabled, the full hover card waits 650 ms before opening to prevent flicker while crossing dense traffic.
- Disabling hover details immediately closes and removes any existing aircraft hover cards.

## v1.4.0 — Runtime optimization, deltas, spatial indexing, and persistence

- Render only the active workspace and defer hidden-tab updates.
- Cache ARTCC polygon membership and unchanged intercept solutions.
- Add conservative spatial candidate indexing before exact ATC coverage checks.
- Add compact WebSocket snapshots, keyed delta updates, periodic recovery snapshots, and track detail on demand.
- Add SQLite operational-state persistence and Railway volume guidance.
- Split optimization concerns into dedicated backend and frontend modules.
- Replace blanket static `no-store` caching with build-versioned immutable assets.
- Add stage-level processing metrics and optimization regression coverage.


## v1.3.37 — Staffed downstream Center handoff suppression

- Adds an 80 NM outbound ARTCC-boundary handoff window.
- Whitelists a temporary mismatch only when the reported radio matches the online downstream Center the projected track is entering.
- Resets any existing mismatch timer when the verified handoff condition becomes active.
- Displays the verified downstream Center in ATC/operator communications status.

## v1.3.36 — Deployment-safe ARTCC/fixed-layout release

- Packages repository files directly at the ZIP root to prevent deploying the wrong nested folder.
- Adds no-store/no-cache headers to the HTML, JavaScript, CSS, and static assets.
- Adds visible BUILD v1.3.36 identification in the footer and client/server mismatch detection.
- Adds `/api/version` and version/build fields to `/health` for deployment verification.
- Retains single-ARTCC focus and permanently excludes the legacy Track / Intercept Data overlay.

## v1.3.36 — Combined operator/ATC release and fixed layout

- Combined the v1.3.34 backend patch, enhanced operator/ATC interface, single-ARTCC focus, and intercept reliability work.
- Removed the legacy floating Selected Track / NORDO Workflow rail and its direct event binding.
- Moved all detailed aircraft, NORDO, coordination, and intercept actions into dedicated workspaces.
- Added a fixed non-overlapping situation-map rail for metrics and alerts/watches only.
- Corrected closed GeoJSON ring handling that could classify all tracks as inside a focused ARTCC.
- Restored missing ATC tactical-map coordinate helpers.
- Added live intercept-map feed/solution status and backward-compatible recalculation results.
- Added fixed-layout, ARTCC-boundary, ATC-map, and merged-workflow regression coverage.

## v1.3.34 — Single-ARTCC dashboard focus

- Added a persistent ARTCC/FIR selector to the situation-map toolbar.
- Focus mode includes aircraft inside the boundary, inbound to an airport inside it, and related intercept aircraft.
- Dashboard metrics, alert queues, NORDO watches, ATC cases, intercept missions, controllers, and map overlays now follow the selected ARTCC.
- The focused ARTCC outline is isolated and emphasized; CLEAR ARTCC restores the national view.


- Expanded the ATC Quick tab into an ATC Coordination Desk with live summary metrics, controller candidates, shared target/coordination/command controls, coordination notes, and a dedicated tactical map.
- Added one-click best-VSOA assignment and a select-three-closest workflow for faster multi-interceptor setup.
- Added ATC map rendering for the selected aircraft, nearby online controllers, related interceptors, routes, and anticipated intercept points.
- Added direct case-to-intercept navigation and clearer next-action guidance for communications checks and NORDO workflow.

## v1.3.32 — Live multi-interceptor map and shared recalculation

- Added a dedicated Intercepts tactical map with target, interceptor, route, and anticipated intercept-point overlays.
- Added simultaneous visualization and assignment of multiple live interceptors against one target.
- Added live connection and last-recalculation indicators in the Intercepts workspace.
- Added shared server-side force recalculation and broadcast through `POST /api/intercepts/recalculate`.
- Added **FIT ALL INTERCEPTS** and **RECALCULATE NOW** controls.
- Expanded interceptor cards with anticipated-point coordinates and per-solution update time.
- Added busy-state protection and visible action feedback across assignment, target-response, ATC coordination, command, note, cancel, and release controls.
- Added backend, static-wiring, and browser-interaction regression coverage for multi-interceptor recalculation.

## v1.3.31 — Focused intercept operations and communications verification

- Added top-level Situation Map, Active Intercept, and ATC Quick workspace tabs.
- Added a dedicated live intercept view with predictive ETA, separation, closure/opening rate, bearing, recommended course, required turn, altitude delta, and both aircraft motion states.
- Added shared target-response states: Unknown, Responding, Not Responding, and Comms Restored.
- Ranked airborne VSOA-tagged aircraft first in manual interceptor recommendations, ordered by distance to the selected target; all live aircraft remain selectable.
- Added an ATC Quick workspace for communications review, manual NORDO confirmation, active-case response controls, and intercept assignment shortcuts.
- Added explicit high-confidence ARTCC gating for automatic 122.800 NORDO monitoring.
- Whitelisted any aircraft radio matching any valid active ARTCC frequency covering that aircraft.
- Added a bundled published CTAF/UNICOM/ATF index and a 50-NM advisory-frequency whitelist for plausible terminal-profile traffic.
- Added projected early-UNICOM handoff suppression when an aircraft is leaving the current ARTCC and the downstream ARTCC is not staffed.
- Preserved the three-minute ATC activation settling window and separate five-minute/eight-minute automatic scramble safeguards.
- Constrained ATC labels, Leaflet popups/tooltips, and map controls to prevent edge clipping at desktop, tablet, and mobile widths.
- Retained the bright solid online-ATC boundary, halo, tint, and controller ONLINE label.
- Grouped simultaneous split-ARTCC automatic alerts into one persistent audible incident so one Center login does not produce repeated alarm playback.

Automatic NORDO remains an inference from public VATSIM telemetry and is not represented as proof of voice-radio failure.

## v1.3.26 — Manual intercept control and live geometry

- Added a shared manual interceptor-to-target assignment API and operator console.
- Added live predictive ETA, separation, signed closure/opening rate, bearing, course, turn requirement, altitude delta, and both aircraft motion states.
- Manual assignments override only the selected interceptor's automatic pairing.
- Added target/interceptor quick actions, assignment focus, update, cancel, and five-minute lost-track retention.
- Expanded intercept labels so manual assignments are not incorrectly presented as squawk 7777.
- Simplified the shared response workflow with phase progress, one prominent next action, and an expandable full checklist.

## v1.3.25 — Live viewer counter

- Added a discreet bottom-right viewer indicator.
- Counts unique connected browser consoles using the existing WebSocket link.
- Multiple tabs sharing the same browser console identity count once.
- Viewer totals update immediately when consoles connect, disconnect, or stale sockets are removed.

## v1.3.24 — ATC activation alert-storm protection

- Added a 180-second settling window before newly staffed ATC coverage can create a communications-mismatch or 122.800 NORDO watch case.
- Required high-confidence live transceiver coverage for new mismatch cases; 122.800 no longer bypasses that confidence gate.
- Preserved already-running communications cases through ordinary controller handoffs and newly opened split positions.
- Added explicit `ATC_ACTIVATION_GRACE` diagnostics and client-visible settling status.

## v1.3.23 — Expanded VSOA remarks recognition

- Detects the standalone `VSOA` marker, full VATSIM/Virtual Special Operations Association wording, and configured organization tags in flight-plan remarks.
- Added explicit recognition for markers including `vUSCG`, `vRCAF`, `vUSAF`, `vUSN`, `vUSMC`, `vANG`, `vDHS`, `vNG`, `vNATO`, `vRAF`, `vRNLAF`, `vGAF`, `vIAF`, `vAGRS`, `BVASO`, `FAAv`, `FABv`, and `vAirMed`.
- Displays the matched organization marker in ATC Scope datablocks, Tactical labels, hover cards, popups, and selected-track details.
- Applies the existing VSOA navigation-detector exemption to recognized organization markers while preserving emergency-squawk, communications, and manual-NORDO monitoring.
- Added boundary and false-positive tests so embedded strings, ordinary `VFR`/`VATSIM` remarks, and unprefixed agency references are not misclassified.

## v1.3.22 — Radar-only ATC scope symbols

- Removed aircraft silhouette icons from ATC Scope tracks.
- Preserved the standard radar target, beacon ring, heading vector, leader line, datablock, VSOA orbit, and alert highlighting.
- Kept aircraft-category silhouettes available in Tactical icon mode.
- Added a regression test preventing scope silhouettes from being reintroduced.

## v1.3.21 — Full-site reliability, performance, and fail-safe audit

- Classified `121.500` Guard and `122.800` advisory/UNICOM as monitor-only frequencies that can never establish ATC contact or clear a wrong-frequency timer.
- Added explicit pilot-radio role labels and a separate list of reported ATC-capable frequencies in hover and detail panels.
- Fixed a startup JavaScript error that could prevent all aircraft from rendering.
- Changed communications timers to advance only on fresh observed feed snapshots.
- Reset timer, manual designation, acknowledgment, and dismissal state when a callsign is reused by a new network session.
- Added stale-feed warning and critical states; critical stale data pauses new automatic alarm playback.
- Added same-country QRA selection by default and evaluation of every aircraft assigned to each base.
- Added inbound-console presence heartbeats and automatic expiration of abandoned console responses.
- Prevented responder heartbeats from rewinding a later intercept phase.
- Added request timeouts, live-fetch overlap prevention, and one controlled SUA refresh scheduler.
- Added a graceful map-engine failure screen when Leaflet cannot load.
- Added expandable detector diagnostics to every selected aircraft.
- Fixed mobile/tablet width containment and tightened the responsive header, toolbar, metrics, and legend.
- Added security response headers and cross-site mutation blocking pending OAuth.
- Added an accurate `/health` status for initializing, stale, and degraded feed states.

## v1.3.19 — Accurate U.S./Canada Center outlines and departure-turn suppression

- Updated U.S. Center matching for the current VATSpy `KZxx` FIR identifiers.
- Added all published parent U.S. and Canadian FIR/ARTCC outlines as a persistent map reference layer, whether staffed or unstaffed.
- Removed broad circular fallback display for Center positions; exact Center polygons are used or the active Center overlay is omitted.
- Merged multi-part FIR features so split geographic pieces display as one complete outline.
- Reworked orbit detection to require sustained same-direction turning rather than accumulated normal vectoring.
- Suppressed SID turns, departure vectors, procedure turns, and initial-climb reversals near the filed departure airport.


## v1.3.18 — Persistent NORDO cases, shared intercept acceptance, and resizable UI

- Fixed the UAL15 failure mode where a wrong-frequency timer could restart or disappear during Denver split-sector changes, handoffs, overlaps, and short transceiver gaps.
- Communications cases are now keyed to the aircraft callsign rather than one controller/scope identifier.
- Added a 60-second grace period for brief coverage or radio-data gaps.
- Requires two consecutive valid frequency matches before clearing an active communications case.
- Changed the strict eight-minute automatic timer from reset-on-ineligible to pause-and-resume.
- Added visible case state and sector/scope-change count to hover and detail panels.
- Added shared **ACCEPT INTERCEPT · MARK INBOUND** and release controls.
- Added live inbound-console counts and responder chips to alert cards and case details.
- Added a shared 12-step intercept checklist with console attribution and Zulu timestamps.
- Added horizontal right-rail resizing and vertical panel resizing with saved browser preferences and **RESET LAYOUT**.
- Reduced low-zoom icon churn, avoided redundant marker moves and intercept-overlay redraws, and removed expensive backdrop blur.

## v1.3.17 — Shared manual NORDO designation

- Added **MARK AIRCRAFT NORDO** to the selected-track panel.
- Manual designation immediately creates a shared red, acknowledgment-required intercept alert and response-base recommendation.
- Added **CLEAR MANUAL NORDO** to remove the shared designation.
- Manual NORDO bypasses automatic ATC ownership, frequency, altitude, and timer gates, while remaining clearly labeled as an operator action.
- Manual designations are retained in server memory until cleared or the service restarts.

## v1.3.16 — Coverage-set NORDO detection fix

- Fixed a blocker where split Center positions or overlapping ATC positions could prevent a 122.800 aircraft from starting any timer.
- The detector now compares the pilot's reported radios against the complete set of valid live ATC frequencies covering the aircraft.
- If none of those frequencies matches, the visible wrong-frequency timer starts even when the exact sector owner is uncertain.
- Split Center positions that match the parent ARTCC boundary can create an observation/watch case when the aircraft is also inside conservative live transceiver reach.
- Overlapping positions no longer suppress the watch when the aircraft matches none of them; the UI displays every possible live owner and every valid ATC frequency.
- Matching any one valid overlapping frequency still immediately clears and resets the timer.
- A stable facility-level scope key lets a timer continue through split-sector handoffs inside the same ARTCC instead of resetting solely because the controller callsign changes.
- The red automatic scramble flag remains protected: every possible same-priority owner must have been online for at least five minutes, and every possible owner must meet the high-confidence coverage requirement.
- Added explicit `NO MATCH TO ANY LIVE ATC FREQ` and `SPLIT-SECTOR WRONG FREQ` status text in hover/details panels.

## v1.3.14 — Generic Center NORDO detection fix

- Generic Center positions such as `DEN_CTR` are now treated as high-confidence owners when the aircraft is inside the exact ARTCC polygon and conservative live AFV transceiver reach.
- Split Center positions that only match a whole-facility fallback remain display-only and cannot start automatic timers.
- A second reported radio no longer suppresses NORDO detection unless that radio actually matches the controlling ATC frequency.
- The 55 NM terminal exemption is now altitude/speed aware so high-altitude arrivals and departures are not silently excluded.
- Aircraft details now show coverage method and the active NORDO timer.

## v1.3.13 — Cache-proof uploaded scramble alarm

- Removed the previous alarm and fallback files from the build.
- Bundled the exact uploaded recording under a new unique filename.
- Test Alarm forcibly reloads the custom recording before playback.
- Added explicit custom-alarm load and playback status messages.

## v1.3.13 — Uploaded scramble-alarm audio

- Replaced the primary scramble alarm with the audio extracted from the operator-provided screen recording.
- Trimmed trailing silence, normalized playback level, and added short edge fades to avoid clicks when looping.
- Preserved the alert-volume control, browser audio-unlock behavior, ten-second test button, continuous alarm loop, and acknowledgment stop behavior.
- Retained the previous bundled alarm as an automatic fallback if the primary asset cannot load.

## v1.3.13 — Mission-aware orbit detection and icon-classification fix

- Added repeated-orbit/no-progress detection using 10–15 minutes of server-side position and heading history.
- Ordinary aircraft with a sustained verified ATC-frequency mismatch plus a repeated orbit can generate a high-priority alert.
- Added detector-specific exemptions for exact `VSOA`, `SAR`, `SEARCH AND RESCUE`, `LAW ENFORCEMENT`, `PATROL`, `ORBIT`, `TRAINING`, and `FORMATION` mission markers.
- Automatically exempts recognized helicopters from orbit, loitering, broad route-deviation, missed-descent, and destination-overshoot scoring.
- Exemptions do not suppress emergency squawks, NORDO Watch, automatic ATC-frequency mismatch, protected-airspace alerts, or manual ATC confirmation.
- Fixed ICAO aircraft-type parsing when VATSIM aircraft strings contain wake-category or equipment prefixes/suffixes.
- Backend now publishes normalized `aircraft_type` and `aircraft_category` fields.
- Added aircraft-category silhouettes to the default ATC Scope icon mode as well as Tactical mode.
- Added aircraft class, orbit state, and mission-exemption details to hover and track panels.

## v1.3.9 — Automatic ATC mismatch flag and corrected header logo

- Added a high-priority **AUTO SCRAMBLE FLAG** after eight continuous minutes in verified live ATC coverage without any reported pilot radio matching the controlling frequency.
- The eight-minute mismatch timer does not begin until the selected ATC position has been continuously online for at least five minutes.
- A position change resets the mismatch timer; time accumulated under one Center/sector cannot carry into another.
- Any valid frequency match among overlapping live ATC candidates suppresses and resets the flag.
- Kept the existing conservative protections: exact/unambiguous transceiver coverage, high-confidence sector ownership, IFR/en-route criteria, terminal exclusion, declared radio-limit exclusions, and required pilot radio data.
- Added controller uptime, frequency-match state, and mismatch elapsed time to hover and track-detail panels.
- Replaced the previously generated header emblem with the exact logo supplied by the user, resized without redesigning it.
- Moved the logo from the upper-right to the upper-left beside the ADOC title.
