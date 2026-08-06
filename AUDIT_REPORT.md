# v1.4.9 France operational coverage

- Adds metropolitan France and Corsica as an enabled operational region.
- Adds French QRA and support base networking from the supplied reference.
- No broader EU or NATO regions are enabled.

# VNG ADOC v1.4.8 Deep Audit

## Confirmed defects repaired

1. Concurrent broadcasts could overlap on the same WebSocket and deliver revisions out of order.
2. A newly connected console could interfere with the shared delta baseline.
3. Keyed deltas did not communicate collection ordering changes, leaving cards or tracks in stale display order.
4. Modal focus handling and CDN integrity metadata needed hardening.
5. Automatic communications escalation lacked a final operator denial window.

## Pre-scramble review behavior

- Appears only during the final configured 30 seconds before an automatic frequency-mismatch scramble flag.
- Displays the callsign, controller/coverage label, and synchronized countdown.
- The shared denial applies only to the current communications case.
- Monitoring and the possible-NORDO watch remain visible.
- Manual NORDO, 7500, 7600, 7700, and other independent emergency reasons are never suppressed.
- Denial records are synchronized, persisted, and expire automatically.

## Validation

- 213 automated tests passed.
- Python compilation passed.
- JavaScript syntax checks passed.
- Runtime smoke checks passed for the root page, health endpoint, version endpoint, safety headers, and deny endpoint error handling.
- Live external VATSIM data could not be exercised in the isolated runtime because public DNS was unavailable; the application correctly entered degraded mode.

---

# VNG ADOC v1.4.2 Validation Audit

## Results

- 185 automated tests passed.
- Python compilation passed for all application modules.
- JavaScript syntax passed for the main application and frontend modules.
- Chromium layout smoke test passed without console or page errors.
- ATC Coordination had no horizontal overflow, clipped controls, or escaped buttons at 1440, 1100, 760, and 390 CSS pixels.
- Evidence, timeline, exemption, and active handoff panels rendered at every tested width.
- Temporary exemptions are shared through full snapshots and keyed WebSocket deltas.

## v1.4.2 scope

1. Rule-by-rule alert evidence.
2. Persistent operation timeline events.
3. Frequency-change grace, clear confirmation, and handoff cooldown.
4. Shared expiring temporary exemptions.
5. Projected ARTCC handoff visualization.
6. Responsive ATC Coordination layout repair.

---

# VNG ADOC v1.4.1 Optimization Audit

## Results

- 178 automated tests passed.
- Python compilation passed for all application modules.
- JavaScript syntax passed for the main application and all optimization modules.
- Chromium smoke test passed with no console/page errors.
- Browser delta test advanced an open intercept workspace from feed revision 10 to 11 without a full reload.
- ARTCC focus retained the expected inside, inbound, and intercept-linked tracks.
- Situation Map and the fixed right rail remained non-overlapping.
- `/api/version`, `/health`, root revalidation headers, and immutable static caching were verified against a running server.
- SQLite operational-state save/load and shutdown flush were verified.

## Implemented optimization layers

1. Active-workspace rendering and dirty-tab scheduling.
2. Existing Leaflet marker reuse retained.
3. Per-revision ARTCC membership cache.
4. Conservative ATC coverage spatial grid with exact checks preserved.
5. Track-signature intercept solution cache with force-recalculate bypass.
6. Compact WebSocket pilot snapshots and keyed deltas.
7. Full track detail on demand.
8. SQLite shared-workflow persistence.
9. Build-versioned immutable static caching.
10. Stage-level processing metrics.

## Synthetic payload measurement

A 500-track synthetic state containing intentionally verbose diagnostics measured:

- Full live JSON: 837,129 bytes
- Compact WebSocket snapshot: 56,154 bytes (93.3% smaller)
- One-track delta: 238 bytes (99.6% smaller than the compact snapshot)

This is a controlled stress measurement, not a guarantee of the exact reduction on live VATSIM traffic. Actual savings depend on how many tracks and operational fields change per feed.

---

# VNG ADOC v1.3.31 validation report

Audit date: 2026-08-05 UTC

## Scope

- Focused Active Intercept and ATC Quick workspaces
- VSOA-first interceptor recommendations
- Shared target-response states
- Manual and automatic intercept geometry
- Online ATC boundary and label visibility
- Map-menu, popup, tooltip, and label edge containment
- High-confidence NORDO qualification and false-positive suppressions
- Existing alert, workflow, presence, VSOA, stale-feed, QRA, and deployment regressions

## Intercept interface

- Added top-level **Situation Map**, **Active Intercept**, and **ATC Quick** tabs.
- The Active Intercept workspace displays live separation, closure/opening rate, predictive ETA, bearing, recommended course, turn requirement, altitude delta, and both aircraft headings, speeds, and altitudes.
- Operators can share **Status Unknown**, **Responding**, **Not Responding**, or **Comms Restored** across connected consoles.
- Airborne VSOA-tagged aircraft are recommended first and ranked by distance to the selected target. Candidates already assigned elsewhere are visibly marked; non-VSOA aircraft remain available.
- Manual assignments remain shared, override only the selected interceptor's automatic pairing, and retain lost tracks for five minutes.
- The ATC Quick workspace exposes radio evidence, manual NORDO controls, active cases, response status, and intercept shortcuts without using the side rail.

## Communications and NORDO safeguards

Automatic 122.800 monitoring now requires all of the following before a new case can advance:

1. Live Center coverage at the aircraft position.
2. High-confidence boundary plus AFV transceiver evidence.
3. Controller presence stable for the three-minute activation settling window.
4. No reported aircraft radio matching any valid active ARTCC frequency in the coverage set.
5. No declared radio limitation or applicable terminal exclusion.
6. No verified nearby published CTAF/UNICOM/ATF match for plausible terminal-profile traffic.
7. No projected early release to 122.800 while exiting toward an unstaffed downstream ARTCC.
8. IFR, altitude, speed, persistence, and fresh-snapshot timer requirements.

The CTAF/UNICOM/ATF index is bundled with the application. The default radius is 50 NM, with a default plausible profile of at or below 12,000 feet and 250 knots, or on the ground. This prevents a common 122.800 airport frequency from hiding unrelated high-altitude Center traffic.

The early-handoff check projects up to 12 minutes, capped at 90 NM, and requires the current parent ARTCC geometry. A staffed downstream ARTCC prevents the exemption.

Public VATSIM telemetry cannot prove whether a pilot actually hears or answers a controller. Automatic output therefore remains **high-confidence possible NORDO**, not 100% confirmation. Manual operator designation remains available.

## Visibility and clipping

- Live ATC uses a solid bright boundary, wider halo, stronger tint, and an internal callsign/frequency/ONLINE label.
- Published FIR/ARTCC outlines remain dimmer and dashed.
- Edge-aware ATC labels shift inward near map boundaries.
- Leaflet popups and tooltips use bounded widths and keep-in-view auto-panning.
- The map toolbar wraps within the map panel and becomes vertically scrollable instead of clipping.
- Static browser layout checks at 1440×900, 1024×768, and 390×844 showed no horizontal page overflow in the map, Active Intercept, or ATC Quick workspaces.

## Automated validation

- `147` Python tests passed.
- Python bytecode compilation passed.
- JavaScript syntax validation passed.
- Tests cover active-ARTCC frequency matching, nearby CTAF suppression, high-altitude CTAF rejection, early 122.800 handoff suppression, ATC activation grace, persistent handoffs, shared intercept response status, VSOA recommendations, grouped Center alarms, and workspace wiring.

## Deployment smoke test

- Uvicorn started successfully.
- `/` returned the v1.3.31 interface.
- `/api/bootstrap` reported version `1.3.31`.
- `/health` returned HTTP 200 and correctly reported degraded/paused automatic alerts when external DNS was unavailable.
- Local static layout rendering confirmed the new tabs and width containment.

## Operational limitations

- Predictive ETA assumes current reported motion continues and is not a guaranteed intercept time.
- Manual assignments, workflow state, and response status remain in process memory and reset on service restart or redeploy.
- Same-origin mutation protection is not authentication. Restrict the deployment URL until account roles are implemented.
- Use one Uvicorn worker while shared operational state remains process-local.

## Not verified in this environment

The audit environment could not resolve public VATSIM and supporting data hosts, so a current live network snapshot and production Railway browser session were not exercised. Perform the post-deployment checks in `DEPLOY_RAILWAY.md` after deployment.

## v1.4.3 verification

- Added cross-ARTCC simultaneous automatic communications-flag detection.
- Pending burst tracks remain visible as POSSIBLE NORDO — VERIFYING.
- Only automatic scramble/intercept escalation is held.
- Independent verification requires three fresh stable snapshots and a 45-second minimum hold by default.
- Single automatic flags are not delayed.
- Emergency squawks and manual NORDO bypass the guard.
- ATC Coordination can dismiss automatic flags with a required reason.
- Dismissal metadata is shared and persisted; the underlying communications watch remains visible.
- Python compilation and JavaScript syntax checks passed.
- 191 automated tests passed.

## v1.4.9 validation

- 220 automated tests passed.
- Python compilation passed for application and tests.
- JavaScript syntax validation passed.
- Runtime smoke checks passed for `/`, `/health`, `/api/version`, `/api/bootstrap`, and `/api/bases`.
- Bootstrap exposes 15 French bases: 6 QRA launch bases and 9 support/display bases.
- France QRA recommendations remain inside the French national network unless cross-border recommendations are explicitly enabled.
- Metropolitan France, Corsica, French FIR identifiers, and France-only client filtering are covered.
- French AFIS/A-A/INFO/CTAF advisory-frequency safeguards were generated from current OurAirports CSV data.
- External VATSIM DNS was unavailable in the local runtime smoke environment; the service reported degraded feed state rather than presenting stale data as live.
